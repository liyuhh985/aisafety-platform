"""会话记忆（SESSION_BACKEND）与历史记忆（按 user_id 隔离）测试。

历史记忆部分写真实 MySQL/Redis（测试后清理）；
会话后端部分用 FakeRedis，不依赖真实 Redis。
"""
import pytest

import core.memory as memory
from core.memory import (
    _mysql_connection,
    _mysql_release,
    _redis,
    _redis_key,
    archive_working_to_historical,
    get_historical_context,
)

TEST_USER_A = 990001
TEST_USER_B = 990002


@pytest.fixture(autouse=True)
def cleanup_test_rows():
    yield
    conn = _mysql_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM ai_historical_analysis WHERE user_id IN (%s, %s)",
                (TEST_USER_A, TEST_USER_B),
            )
        conn.commit()
    finally:
        _mysql_release(conn)
    try:
        _redis().delete(_redis_key(TEST_USER_A), _redis_key(TEST_USER_B))
    except Exception:
        pass


def test_archive_and_context_for_same_user():
    vision = {
        "hazard_category": "消防安全",
        "severity": "高",
        "description": "测试描述-电气线路老化",
    }
    archive_working_to_historical(
        TEST_USER_A, "sess-a", "报告A", vision=vision, dialogue="[用户]: 问题"
    )

    ctx = get_historical_context(TEST_USER_A)

    assert "消防安全" in ctx
    assert "测试描述-电气线路老化" in ctx
    assert "用户关注隐患类别" in ctx


def test_users_are_isolated():
    vision = {"hazard_category": "建筑施工", "severity": "中", "description": "A用户案例"}
    archive_working_to_historical(TEST_USER_A, "sess-a", "报告A", vision=vision)

    ctx_a = get_historical_context(TEST_USER_A)
    ctx_b = get_historical_context(TEST_USER_B)

    assert "建筑施工" in ctx_a
    assert ctx_b == ""


def test_archive_without_user_id_does_nothing():
    archive_working_to_historical(None, "sess-null", "报告")
    # 不应抛异常，也不影响任何用户上下文
    assert get_historical_context(TEST_USER_B) == ""


# ====== 会话后端：SESSION_BACKEND=redis（跨 worker 共享）======

class _FakePipeline:
    """只实现会话存储用到的 RPUSH/LTRIM/EXPIRE/DELETE 批处理语义。"""

    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def rpush(self, key, *values):
        self.ops.append(("rpush", key, values))

    def ltrim(self, key, start, end):
        self.ops.append(("ltrim", key, start, end))

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))

    def delete(self, *keys):
        self.ops.append(("delete", keys))

    def execute(self):
        self.redis._check()
        for op in self.ops:
            if op[0] == "rpush":
                self.redis.store.setdefault(op[1], []).extend(op[2])
            elif op[0] == "ltrim":
                _, key, start, end = op
                values = self.redis.store.get(key, [])
                # Redis 的负下标会 clamp 到 0（LTRIM -4 -1 = 保留最后 4 条），
                # 和 Python 的 values[-4:] 不同，所以要自己算。
                keep_from = max(0, len(values) + start) if start < 0 else start
                keep_to = len(values) if end == -1 else end + 1
                self.redis.store[key] = values[keep_from:keep_to]
            elif op[0] == "expire":
                self.redis.expires[op[1]] = op[2]
            elif op[0] == "delete":
                for k in op[1]:
                    self.redis.store.pop(k, None)
        self.ops = []


class FakeRedis:
    """最小假 Redis（list + pipeline），多个实例共享 store 就等价于"同一个 Redis"。"""

    def __init__(self, store=None):
        self.store = store if store is not None else {}
        self.expires = {}
        self.fail = False

    def _check(self):
        if self.fail:
            raise ConnectionError("redis is down")

    def lrange(self, key, start, end):
        self._check()
        values = list(self.store.get(key, []))
        if start == 0 and end == -1:
            return values
        return values[start:] if end == -1 else values[start:end + 1]

    def delete(self, *keys):
        self._check()
        return sum(1 for k in keys if self.store.pop(k, None) is not None)

    def pipeline(self):
        self._check()
        return _FakePipeline(self)


@pytest.fixture
def redis_session_backend(monkeypatch):
    """把会话后端切到 redis，并注入一台假 Redis（store 可跨"实例"共享）。"""
    fake = FakeRedis()
    monkeypatch.setenv("SESSION_BACKEND", "redis")
    monkeypatch.setattr(memory, "_session_redis", lambda: fake)
    memory.reset_sessions()
    yield fake
    memory.reset_sessions()


def _new_worker(fake):
    """模拟"另一个 worker 进程"：同一台 Redis，全新的进程内会话对象。"""
    memory._redis_sessions.clear()
    return memory.get_session("s1")


def test_redis_session_survives_new_store_instance(redis_session_backend):
    """同一 session_id 在两个实例间读到同一 messages（多 worker 的核心诉求）。"""
    first = memory.get_session("s1")
    first.add_user("消防通道被车占了")
    first.add_assistant("已记录")

    second = memory.RedisWorkingMemory("s1", redis_session_backend)
    assert second.get_history() == [
        {"role": "user", "content": "消防通道被车占了"},
        {"role": "assistant", "content": "已记录"},
    ]


def test_redis_session_visible_across_worker_objects(redis_session_backend):
    """get_session 换一个进程内缓存（等价于换 worker）后仍能看到同一份历史。"""
    a = memory.get_session("s1")
    a.add_user("第一条")
    b = _new_worker(redis_session_backend)

    assert b is not a
    assert b.get_history() == [{"role": "user", "content": "第一条"}]

    # 反向：b 写的，a（老实例）也要看得到——messages 每次都回 Redis 读，不做进程内缓存
    b.add_user("第二条")
    assert [m["content"] for m in a.get_history()] == ["第一条", "第二条"]


def test_redis_session_isolates_different_sessions(redis_session_backend):
    """不同 session_id 必须互不可见。"""
    memory.get_session("s1").add_user("s1 的内容")
    memory.get_session("s2").add_user("s2 的内容")

    assert [m["content"] for m in memory.get_session("s1").get_history()] == ["s1 的内容"]
    assert [m["content"] for m in memory.get_session("s2").get_history()] == ["s2 的内容"]


def test_redis_session_keeps_last_n_and_ttl(redis_session_backend):
    """超过 max_turns*2 条要截断（LTRIM），并且每次追加都续期 TTL。"""
    mem = memory.RedisWorkingMemory("s1", redis_session_backend, ttl_seconds=123, max_turns=2)
    for i in range(7):
        mem.add_user(f"m{i}")

    assert [m["content"] for m in mem.get_history()] == ["m3", "m4", "m5", "m6"]
    assert redis_session_backend.expires["ai:sess:s1"] == 123


def test_redis_session_add_report_and_system_are_system_messages(redis_session_backend):
    mem = memory.get_session("s1")
    mem.add_report("报告正文")
    mem.add_system("[视觉分析] {...}")

    roles = [(m["role"], m["content"]) for m in mem.get_history()]
    assert roles[0][0] == "system" and "报告正文" in roles[0][1]
    assert roles[1] == ("system", "[视觉分析] {...}")
    assert "报告正文" in mem.get_compressed_dialogue()


def test_redis_session_clear_removes_history(redis_session_backend):
    mem = memory.get_session("s1")
    mem.add_user("要清掉")
    mem.clear()
    assert mem.get_history() == []


def test_redis_session_degrades_to_local_when_redis_down(monkeypatch, caplog):
    """degrade（默认）：Redis 挂了不炸服务，退回进程内记忆。"""
    fake = FakeRedis()
    monkeypatch.setenv("SESSION_BACKEND", "redis")
    monkeypatch.setenv("SESSION_REDIS_FALLBACK", "degrade")
    monkeypatch.setattr(memory, "_session_redis", lambda: fake)
    memory.reset_sessions()
    fake.fail = True

    mem = memory.get_session("s-down")
    mem.add_user("Redis 挂的时候写的")   # 不抛异常
    assert [m["content"] for m in mem.get_history()] == ["Redis 挂的时候写的"]
    assert mem._degraded is True
    assert memory.session_backend_status()["degraded_sessions"] == 1
    memory.reset_sessions()


def test_redis_session_strict_mode_raises(monkeypatch):
    """strict：Redis 挂了直接抛 SessionStoreUnavailable（宁可不服务也不静默丢历史）。"""
    fake = FakeRedis()
    fake.fail = True
    monkeypatch.setenv("SESSION_BACKEND", "redis")
    monkeypatch.setenv("SESSION_REDIS_FALLBACK", "strict")
    monkeypatch.setattr(memory, "_session_redis", lambda: fake)
    memory.reset_sessions()

    mem = memory.get_session("s-strict")
    with pytest.raises(memory.SessionStoreUnavailable):
        mem.add_user("写不进去")
    memory.reset_sessions()


def test_session_backend_memory_keeps_in_process_sessions(monkeypatch):
    """默认 memory 后端：行为和改造前一致（进程内 dict）。"""
    monkeypatch.setenv("SESSION_BACKEND", "memory")
    memory.reset_sessions()

    a = memory.get_session("local-1")
    a.add_user("本地记忆")
    assert type(a).__name__ == "WorkingMemory"
    assert memory.get_session("local-1") is a
    assert memory.session_backend_status()["configured"] == "memory"
    memory.reset_sessions()
