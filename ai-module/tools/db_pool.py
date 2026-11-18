# -*- coding: utf-8 -*-
"""共享 MySQL 连接池（P2，有并发上限）。

动机（实测）：`pymysql.connect()` 每次都要付一次 TCP + 认证握手，实测约 45ms；
而查询本身（主键等值查）是微秒级。这个**固定成本**每轮对话会被付好几次：
建单链路、检索关键词、历史记忆读写。

设计取舍：
- **有界**：池内活连接（空闲 + 借出 + 正在建）永远不超过 `max_connections`。
  连接全借出去之后，`acquire()` 是**阻塞等待归还**（Condition + notify），
  而不是无限新建连接——高并发时把压力挡在 MySQL 连接数之外，
  而不是把 MySQL 的连接数打满。
- 等待有兜底超时（`DB_POOL_ACQUIRE_TIMEOUT_SECONDS`，默认 30s）：
  万一连接泄漏，宁可报错也不让调用方永久挂起。
- 极简：list + Condition；取出时 `ping(reconnect=True)`，坏了就丢弃重建。
- **归还前必须 rollback**：否则上一个使用者没提交的 SELECT 事务会被下一个使用者
  继承，在 REPEATABLE READ 下变成"固定快照"读到旧数据（本项目已经踩过一次这个坑）。
- 取消/异常路径一律 `discard()`（直接关），因为连接可能停在半途的查询上，不能复用。
- 建连参数显式给超时：默认为 None 意味着**可以无限等**，一旦 MySQL 卡住会把调用方
  一起拖死。宁可超时报错，也不无限挂起。
- **不是本池取出的连接**（单测注入的假连接、外部自建连接）在 release/discard 时
  直接关闭，不进池、不占名额——与旧实现语义一致。

为什么不用 `DBUtils.PooledDB`：它的 `close()` 语义是“归还给池”，
本项目 `discard()`（取消路径）要的是“真的关掉这条半途的连接”，
用 PooledDB 反而得摸私有属性才能做到；自建有界池还能少一个运行时依赖。
"""
import logging
import os
import threading
import time

import pymysql

from config import RETRIEVAL_TIMEOUT_SECONDS
from db_config import DB_CONFIG

LOGGER = logging.getLogger("safety.ai.db_pool")


class DBPoolTimeoutError(TimeoutError):
    """池内连接已耗尽，等待归还超时。"""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


# 每个池允许同时存在的活连接上限（空闲 + 借出 + 正在建）。
DB_POOL_MAX_CONNECTIONS = max(1, _env_int("DB_POOL_MAX_CONNECTIONS", 8))
# 空闲缓存上限；不配就跟着并发上限走。
DB_POOL_MAX_IDLE = max(1, _env_int("DB_POOL_MAX_IDLE", DB_POOL_MAX_CONNECTIONS))
# 池满时的等待兜底；设为 0 或负数表示无限等待（不推荐）。
DB_POOL_ACQUIRE_TIMEOUT_SECONDS = _env_float("DB_POOL_ACQUIRE_TIMEOUT_SECONDS", 30.0)


def _close_quietly(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


class DBPool:
    """有并发上限的 MySQL 连接池。

    名额（容量）语义：`len(_tracked) + _creating <= max_connections`。
    连接只有被**关闭**时才腾出名额，放回空闲位不算（它还是活连接）——
    所以借满时等待者是靠 `notify()` 抢空闲位，而不是靠名额。
    """

    def __init__(self, connect_kwargs: dict | None = None, max_idle: int = 8,
                 max_connections: int | None = None, acquire_timeout: float | None = None):
        limit = DB_POOL_MAX_CONNECTIONS if max_connections is None else max(1, int(max_connections))
        self._max_connections = limit
        self._max_idle = max(1, min(int(max_idle), limit))
        if acquire_timeout is None:
            self._acquire_timeout = DB_POOL_ACQUIRE_TIMEOUT_SECONDS
        else:
            self._acquire_timeout = None if float(acquire_timeout) <= 0 else float(acquire_timeout)

        self._cond = threading.Condition()
        self._idle: list = []             # 空闲连接（LIFO）
        self._idle_ids: set = set()
        self._tracked: dict = {}          # 本池拥有的活连接（空闲 + 借出）
        self._creating: int = 0           # 已占名额、还没建好的连接数
        self._kwargs = dict(connect_kwargs or {})

    # ---- 只读信息（便于排查 / 测试断言） ----

    @property
    def max_connections(self) -> int:
        return self._max_connections

    @property
    def max_idle(self) -> int:
        return self._max_idle

    def stats(self) -> dict:
        with self._cond:
            idle = len(self._idle)
            return {
                "max_connections": self._max_connections,
                "max_idle": self._max_idle,
                "idle": idle,
                "checked_out": len(self._tracked) - idle,
            }

    # ---- 取 / 还 ----

    def acquire(self):
        """取连接：优先复用空闲连接，其次在名额内新建，名额用满则阻塞等待归还。

        超过 `acquire_timeout` 仍拿不到连接就抛 `DBPoolTimeoutError`。
        """
        deadline = (None if self._acquire_timeout is None
                    else time.monotonic() + self._acquire_timeout)
        while True:
            conn = None
            reserved = False
            victims = []
            with self._cond:
                if self._idle:
                    conn = self._idle.pop()
                    self._idle_ids.discard(id(conn))
                elif len(self._tracked) + self._creating < self._max_connections:
                    self._creating += 1
                    reserved = True
                else:
                    victims = self._reclaim_closed_locked()
                    if not victims:
                        remaining = None if deadline is None else deadline - time.monotonic()
                        if remaining is not None and remaining <= 0:
                            raise self._exhausted_error()
                        self._cond.wait(timeout=remaining)
                        continue

            if victims:                       # 有僵尸连接被摘掉：锁外关掉，回头再抢名额
                for dead in victims:
                    _close_quietly(dead)
                continue

            if conn is not None:
                if self._ping(conn):
                    return conn
                self._close_owned(conn)       # 坏连接：关掉并腾名额，回头再抢
                continue

            return self._create_reserved()

    def release(self, conn) -> None:
        """归还连接：先 rollback 清事务，再放回池子（空闲位满则关掉）。"""
        if conn is None:
            return
        with self._cond:
            owned = id(conn) in self._tracked
            already_idle = id(conn) in self._idle_ids
        if not owned:
            _close_quietly(conn)              # 不是本池取出的（测试注入的假连接）
            return
        if already_idle:                      # 重复归还：忽略，不重复入池
            return
        try:
            conn.rollback()
            still_open = bool(getattr(conn, "open", False))
        except Exception:
            still_open = False
        if not still_open:
            self._close_owned(conn)
            return
        with self._cond:
            if len(self._idle) < self._max_idle and id(conn) in self._tracked:
                self._idle.append(conn)
                self._idle_ids.add(id(conn))
                self._cond.notify()
                return
        self._close_owned(conn)

    def discard(self, conn) -> None:
        """不复用，直接关（取消 / 异常路径）；本池的连接同步腾出名额。"""
        if conn is None:
            return
        with self._cond:
            owned = id(conn) in self._tracked
            self._idle_ids.discard(id(conn))
            try:
                self._idle.remove(conn)
            except ValueError:
                pass
        if owned:
            self._close_owned(conn)
        else:
            _close_quietly(conn)

    def close_all(self) -> None:
        """关掉所有空闲连接（进程退出 / 测试收尾）。借出的连接不在此范围。"""
        while True:
            with self._cond:
                if not self._idle:
                    return
                conn = self._idle.pop()
                self._idle_ids.discard(id(conn))
            self._close_owned(conn)

    # ---- 内部 ----

    def _create_reserved(self):
        """名额已经占好（`_creating`），这里真正建连。"""
        try:
            kwargs = dict(DB_CONFIG)
            kwargs.update(self._kwargs)
            conn = pymysql.connect(autocommit=False, **kwargs)
        except BaseException:
            with self._cond:
                self._creating -= 1
                self._cond.notify()
            raise
        with self._cond:
            self._creating -= 1
            self._tracked[id(conn)] = conn
        LOGGER.debug("db pool created connection idle=%s live=%s",
                     len(self._idle), len(self._tracked))
        return conn

    def _reclaim_closed_locked(self) -> list:
        """池满时把"被调用方直接 close 掉"的僵尸连接摘出来，腾出名额。

        调用方绕过 release()/discard() 直接 conn.close() 时，池并不知道连接已经没了；
        不做这件事，名额会被永久占住，最终把池卡死。这里只做无 I/O 的 open 检查，
        真正的 close 由调用方在锁外执行（避免持锁做网络 I/O）。
        """
        victims = [conn for conn in self._tracked.values()
                   if not getattr(conn, "open", True)]
        for conn in victims:
            self._tracked.pop(id(conn), None)
            self._idle_ids.discard(id(conn))
            try:
                self._idle.remove(conn)
            except ValueError:
                pass
        if victims:
            self._cond.notify_all()
        return victims

    def _close_owned(self, conn) -> None:
        """关闭一条本池拥有的连接：先 close（还在计数内，避免超建），再腾名额唤醒等待者。"""
        _close_quietly(conn)
        with self._cond:
            self._tracked.pop(id(conn), None)
            self._idle_ids.discard(id(conn))
            self._cond.notify()

    def _exhausted_error(self) -> DBPoolTimeoutError:
        LOGGER.warning("db pool exhausted: max_connections=%s timeout=%ss",
                       self._max_connections, self._acquire_timeout)
        return DBPoolTimeoutError(
            "数据库连接池已满（max_connections=%s），等待 %ss 仍无连接归还"
            % (self._max_connections, self._acquire_timeout))

    @staticmethod
    def _ping(conn) -> bool:
        try:
            conn.ping(reconnect=True)
            return True
        except Exception:
            return False


# 默认池：给建单链路 + 历史记忆用
_POOL = DBPool({"connect_timeout": 5, "read_timeout": 10, "write_timeout": 10})

# 检索专用池：hybrid_search 原本给每个查询设 socket 级超时，
# 与默认池参数不同，混用会互相串味，所以单独一个池。
_RETRIEVAL_POOL = DBPool({
    "connect_timeout": max(0.001, float(RETRIEVAL_TIMEOUT_SECONDS)),
    "read_timeout": max(0.001, float(RETRIEVAL_TIMEOUT_SECONDS)),
    "write_timeout": max(0.001, float(RETRIEVAL_TIMEOUT_SECONDS)),
})


def pool() -> DBPool:
    return _POOL


def retrieval_pool() -> DBPool:
    return _RETRIEVAL_POOL