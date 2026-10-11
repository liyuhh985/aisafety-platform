# -*- coding: utf-8 -*-
"""有界 MySQL 连接池单测（不连真实 MySQL：monkeypatch pymysql.connect）。

覆盖三条硬约束：
  1. 并发上限不会被突破——超限是**阻塞等待**，不是无限新建连接；
  2. 归还的连接能被复用（rollback 后回到空闲位）；
  3. 归还前 rollback 仍然生效；坏连接/取消路径会释放槽位，不会把池卡死。
"""
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import db_pool


class FakeConn:
    """最小假连接：只实现池会用到的 ping / rollback / close / open。"""

    def __init__(self, alive=True):
        self.alive = alive
        self.open = True
        self.rollbacks = 0
        self.pings = 0
        self.closed = False

    def ping(self, reconnect=False):
        self.pings += 1
        if not self.alive:
            raise RuntimeError("fake connection lost")

    def rollback(self):
        if self.closed:
            raise RuntimeError("fake connection already closed")
        self.rollbacks += 1

    def close(self):
        self.closed = True
        self.open = False

    def cursor(self):        # 池不该执行 SQL
        raise AssertionError("pool must not run SQL in unit tests")


@pytest.fixture
def created(monkeypatch):
    """把 pymysql.connect 换成假实现，记录每条被创建的连接。"""
    made = []

    def fake_connect(**kwargs):
        conn = FakeConn()
        conn.kwargs = kwargs
        made.append(conn)
        return conn

    monkeypatch.setattr(db_pool.pymysql, "connect", fake_connect)
    return made


def test_pool_never_exceeds_max_connections(created):
    pool = db_pool.DBPool({}, max_idle=4, max_connections=2, acquire_timeout=5)

    first = pool.acquire()
    second = pool.acquire()
    assert first is not second
    assert len(created) == 2
    assert pool.stats()["checked_out"] == 2

    held = []
    acquired = threading.Event()

    def worker():
        held.append(pool.acquire())
        acquired.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    # 给足时间：如果是"无限新建连接"，这里早就出现第 3 条了
    assert acquired.wait(0.5) is False
    assert len(created) == 2, "超过并发上限时不应新建连接（必须阻塞等待）"

    pool.release(first)
    assert acquired.wait(5) is True
    assert len(created) == 2, "归还的连接应被复用，而不是新建"
    assert held[0] is first
    assert pool.stats()["checked_out"] == 2
    pool.release(second)
    pool.release(held[0])


def test_exhausted_pool_blocks_then_wakes_up(created):
    pool = db_pool.DBPool({}, max_connections=1, acquire_timeout=5)
    only = pool.acquire()

    start = threading.Event()
    got = []

    def worker():
        start.set()
        got.append(pool.acquire())

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    assert start.wait(1) is True
    thread.join(timeout=0.5)
    assert thread.is_alive(), "池满时 acquire 必须是阻塞等待"

    pool.release(only)
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert got and got[0] is only


def test_release_rolls_back_and_connection_is_reused(created):
    pool = db_pool.DBPool({}, max_connections=1, acquire_timeout=2)

    conn = pool.acquire()
    pool.release(conn)
    assert conn.rollbacks == 1, "归还前必须 rollback"

    again = pool.acquire()
    assert again is conn, "归还的连接应被复用"
    assert len(created) == 1
    pool.release(conn)


def test_acquire_timeout_raises_clear_error(created):
    pool = db_pool.DBPool({}, max_connections=1, acquire_timeout=0.2)
    pool.acquire()

    with pytest.raises(db_pool.DBPoolTimeoutError):
        pool.acquire()


def test_dead_idle_connection_is_replaced_and_slot_freed(created):
    pool = db_pool.DBPool({}, max_connections=1, acquire_timeout=2)

    conn = pool.acquire()
    conn.alive = False
    pool.release(conn)

    fresh = pool.acquire()          # 复用时 ping 失败 → 丢弃重建；槽位若泄漏这里会超时
    assert fresh is not conn
    assert conn.closed is True
    assert len(created) == 2
    pool.release(fresh)


def test_discard_frees_slot(created):
    pool = db_pool.DBPool({}, max_connections=1, acquire_timeout=0.2)

    conn = pool.acquire()
    pool.discard(conn)
    assert conn.closed is True
    assert pool.stats() == {"max_connections": 1, "max_idle": 1, "idle": 0, "checked_out": 0}

    fresh = pool.acquire()          # 不能超时
    assert fresh is not conn
    pool.release(fresh)


def test_rollback_failure_drops_connection_without_leaking_slot(created):
    pool = db_pool.DBPool({}, max_connections=1, acquire_timeout=2)

    conn = pool.acquire()
    conn.close()                    # rollback 会抛异常
    pool.release(conn)
    assert pool.stats()["checked_out"] == 0

    fresh = pool.acquire()
    assert fresh is not conn
    pool.release(fresh)


def test_untracked_connection_is_closed_not_pooled(created):
    """单测/历史用法：注入的假连接 release/discard 时直接关，语义不变。"""
    pool = db_pool.DBPool({}, max_connections=2, acquire_timeout=2)

    foreign = FakeConn()
    pool.release(foreign)
    assert foreign.closed is True
    assert foreign.rollbacks == 0, "非本池连接不参与 rollback/入池"
    assert pool.stats()["checked_out"] == 0

    pool.discard(foreign)           # 幂等：再还一次也不抛
    assert pool.acquire() is not None
    assert len(created) == 1


def test_double_release_does_not_duplicate_or_corrupt_pool(created):
    pool = db_pool.DBPool({}, max_connections=2, acquire_timeout=2)

    conn = pool.acquire()
    pool.release(conn)
    pool.release(conn)              # 重复归还：忽略，不重复入池、不重复释放槽位

    assert pool.stats() == {"max_connections": 2, "max_idle": 2, "idle": 1, "checked_out": 0}
    assert len(created) == 1
    assert pool.acquire() is conn


def test_idle_cache_is_capped_at_max_idle(created):
    pool = db_pool.DBPool({}, max_idle=1, max_connections=3, acquire_timeout=2)

    a, b = pool.acquire(), pool.acquire()
    pool.release(a)
    pool.release(b)                 # 空闲位只有 1 个 → b 被关掉并释放槽位
    assert pool.stats()["idle"] == 1
    assert (a.closed, b.closed) != (True, True)

    c, d = pool.acquire(), pool.acquire()   # 槽位已归还，仍能取到两条
    assert len(created) == 3


def test_module_level_pools_keep_entrypoints_and_are_bounded():
    assert db_pool.pool() is db_pool.pool()
    assert db_pool.retrieval_pool() is db_pool.retrieval_pool()
    assert db_pool.retrieval_pool() is not db_pool.pool()

    for instance in (db_pool.pool(), db_pool.retrieval_pool()):
        assert isinstance(instance, db_pool.DBPool)
        assert instance.max_connections >= 1
        assert instance.max_idle <= instance.max_connections

    # 检索池的 socket 超时参数保持原样（调用语义不变）
    assert db_pool.retrieval_pool()._kwargs["read_timeout"] > 0
    assert db_pool.pool()._kwargs["connect_timeout"] == 5

def test_concurrent_acquire_release_never_exceeds_limit(created):
    """9 个线程抢 3 条连接：峰值并发使用数 <= 3，实际创建的连接 <= 3。"""
    pool = db_pool.DBPool({}, max_connections=3, max_idle=3, acquire_timeout=10)
    guard = threading.Lock()
    in_use = []
    peak = []

    def worker():
        for _ in range(20):
            conn = pool.acquire()
            try:
                with guard:
                    in_use.append(conn)
                    peak.append(len(in_use))
                time.sleep(0.001)
            finally:
                with guard:
                    in_use.remove(conn)
                pool.release(conn)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(9)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(not thread.is_alive() for thread in threads)
    assert max(peak) <= 3, "实际并发使用数突破了上限"
    assert len(created) <= 3, "创建的连接数突破了上限"
    assert pool.stats() == {"max_connections": 3, "max_idle": 3, "idle": 3, "checked_out": 0}
    pool.close_all()


def test_pool_reclaims_connection_closed_by_caller(created):
    """调用方绕过 release() 直接 conn.close() 时，池不会永久少一个名额（自愈）。"""
    pool = db_pool.DBPool({}, max_connections=1, acquire_timeout=2)

    leaked = pool.acquire()
    leaked.close()                 # 等价于 core/tests 里 conn.close() 的用法

    fresh = pool.acquire()         # 不能超时：应识别僵尸连接并腾出名额
    assert fresh is not leaked
    assert len(created) == 2
    assert pool.stats()["checked_out"] == 1
    pool.release(fresh)
