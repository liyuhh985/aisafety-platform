# -*- coding: utf-8 -*-
"""Checkpointer 后端选择测试（CHECKPOINT_BACKEND=memory|redis）。

重点验证"选对后端"和"选不到就降级"，不连真实 Redis：
  - memory：InMemorySaver，单进程（原行为）
  - redis ：用 langgraph-checkpoint-redis 的 RedisSaver（多 worker 共享 interrupt 状态）
  - redis 不可用（没装包 / 连不上 / Redis 缺 RediSearch 模块）-> 降级 InMemorySaver + 记原因
"""
import sys
import types

import pytest
from langgraph.checkpoint.memory import InMemorySaver

import core.assistant_graph as ag


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """每个用例前把后端缓存清空，避免用例之间互相污染。"""
    monkeypatch.setenv("CHECKPOINT_BACKEND", "memory")
    ag.reset_checkpointer()
    yield
    ag.reset_checkpointer()


class _StubClient:
    """假 Redis 客户端：只关心 ping 通不通。"""

    def __init__(self, ping_ok=True):
        self.ping_ok = ping_ok
        self.pinged = False

    def ping(self):
        self.pinged = True
        if not self.ping_ok:
            raise ConnectionError("connection refused")
        return True


def _stub_langgraph_redis(monkeypatch, saver_cls):
    """把 langgraph.checkpoint.redis 换成一个只提供 RedisSaver 的假模块。"""
    module = types.ModuleType("langgraph.checkpoint.redis")
    module.RedisSaver = saver_cls
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.redis", module)


def test_memory_backend_returns_in_memory_saver(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_BACKEND", "memory")
    assert isinstance(ag.get_checkpointer(), InMemorySaver)
    assert ag.checkpoint_backend_status() == {
        "configured": "memory", "effective": "memory", "error": None,
    }


def test_memory_backend_does_not_touch_redis(monkeypatch):
    """memory 后端下不许尝试构造 RedisSaver（否则本地没装包会平白多一条日志）。"""
    monkeypatch.setenv("CHECKPOINT_BACKEND", "memory")

    def boom():
        raise AssertionError("memory 后端不应该去连 Redis")

    monkeypatch.setattr(ag, "_build_redis_checkpointer", boom)
    assert isinstance(ag.get_checkpointer(), InMemorySaver)


def test_redis_backend_uses_redis_saver_when_available(monkeypatch):
    """redis 后端：用 RedisSaver，并且只构造一次（缓存）。"""
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis")
    saver = InMemorySaver()  # 只当哨兵用：断言拿到的就是它
    calls = []

    def fake_build():
        calls.append(1)
        return saver, None

    monkeypatch.setattr(ag, "_build_redis_checkpointer", fake_build)

    assert ag.get_checkpointer() is saver
    assert ag.get_checkpointer() is saver
    assert len(calls) == 1
    assert ag.checkpoint_backend_status()["effective"] == "redis"


def test_redis_backend_degrades_when_package_missing(monkeypatch):
    """没装 langgraph-checkpoint-redis：降级 InMemorySaver，不抛异常。"""
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis")
    monkeypatch.setitem(sys.modules, "langgraph.checkpoint.redis", None)

    saver = ag.get_checkpointer()
    assert isinstance(saver, InMemorySaver)
    status = ag.checkpoint_backend_status()
    assert status["configured"] == "redis"
    assert status["effective"] == "memory"
    assert "langgraph-checkpoint-redis" in status["error"]


def test_redis_backend_degrades_when_redis_unreachable(monkeypatch):
    """Redis 连不上：降级 InMemorySaver，原因里带上地址，方便排障。"""

    class StubSaver:
        def __init__(self, redis_client=None, **kwargs):
            self.redis_client = redis_client

    _stub_langgraph_redis(monkeypatch, StubSaver)
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis")
    monkeypatch.setattr("redis.Redis", lambda **kwargs: _StubClient(ping_ok=False))

    saver = ag.get_checkpointer()
    assert isinstance(saver, InMemorySaver)
    assert "连不上" in ag.checkpoint_backend_status()["error"]


def test_redis_backend_degrades_when_setup_fails(monkeypatch):
    """Redis 没有 RediSearch/RedisJSON（自建 redis:7-alpine）：setup() 失败 -> 降级。"""

    class StubSaver:
        def __init__(self, redis_client=None, **kwargs):
            self.redis_client = redis_client
            self.setup_called = False

        def setup(self):
            self.setup_called = True
            raise Exception("unknown command 'FT.INFO'")

    _stub_langgraph_redis(monkeypatch, StubSaver)
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis")
    monkeypatch.setattr("redis.Redis", lambda **kwargs: _StubClient(ping_ok=True))

    saver = ag.get_checkpointer()
    assert isinstance(saver, InMemorySaver)
    error = ag.checkpoint_backend_status()["error"]
    assert "setup()" in error


def test_get_app_compiles_with_selected_checkpointer(monkeypatch):
    """get_app() 真的把选中的 checkpointer 编进图里（不是只返回了个对象）。"""
    monkeypatch.setenv("CHECKPOINT_BACKEND", "memory")
    app = ag.get_app()
    assert isinstance(app.checkpointer, InMemorySaver)

    sentinel = InMemorySaver()
    monkeypatch.setattr(ag, "_build_redis_checkpointer", lambda: (sentinel, None))
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis")
    ag.reset_checkpointer()

    app = ag.get_app()
    assert app.checkpointer is sentinel


def test_build_graph_accepts_explicit_checkpointer():
    """build_graph(checkpointer=...) 直接生效（测试和将来换后端都靠这个口子）。"""
    saver = InMemorySaver()
    assert ag.build_graph(checkpointer=saver).checkpointer is saver
    assert isinstance(ag.build_graph().checkpointer, InMemorySaver)


def test_reset_checkpointer_clears_app_and_saver_cache(monkeypatch):
    monkeypatch.setenv("CHECKPOINT_BACKEND", "memory")
    first = ag.get_checkpointer()
    assert ag.get_app().checkpointer is first

    ag.reset_checkpointer()
    assert ag._APP is None
    assert ag.get_checkpointer() is not first


def test_invalid_checkpoint_backend_falls_back_to_memory(monkeypatch):
    """脏配置（比如手改了环境变量）不能把服务带崩，按 memory 处理。"""
    monkeypatch.setenv("CHECKPOINT_BACKEND", "redis-cluster")
    assert isinstance(ag.get_checkpointer(), InMemorySaver)
    assert ag.checkpoint_backend_status()["configured"] == "memory"
