"""Python 内部服务鉴权、会话隔离与同会话并发保护。"""
import pytest
from fastapi.testclient import TestClient

import server
from core import assistant_graph
import core.memory as memory


TOKEN = "test-internal-token"
HEADERS = {"X-Internal-Token": TOKEN}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "AI_INTERNAL_TOKEN", TOKEN)
    monkeypatch.setenv("SESSION_BACKEND", "memory")
    memory.reset_sessions()
    with TestClient(server.app) as test_client:
        yield test_client
    memory.reset_sessions()


def test_health_is_public_but_business_endpoints_require_internal_token(client):
    assert client.get("/api/ai/health").status_code == 200

    requests = [
        ("GET", "/api/ai/history?session_id=s&user_id=1", None),
        ("DELETE", "/api/ai/session?session_id=s&user_id=1", None),
        ("GET", "/api/ai/hazard-create/requests/req-1?user_id=1", None),
        ("POST", "/api/ai/chat", {"message": "hi", "session_id": "s", "user_id": 1}),
        ("POST", "/api/ai/assistant/stream", {"message": "hi", "session_id": "s", "user_id": 1}),
    ]
    for method, url, body in requests:
        for headers in ({}, {"X-Internal-Token": "wrong-token"}):
            response = client.request(method, url, headers=headers, json=body)
            assert response.status_code == 401, (method, url, headers)


def test_history_and_delete_are_namespaced_by_user(client):
    memory.get_session(101, "shared").add_user("用户101的消息")

    own = client.get(
        "/api/ai/history",
        params={"session_id": "shared", "user_id": 101},
        headers=HEADERS,
    )
    other = client.get(
        "/api/ai/history",
        params={"session_id": "shared", "user_id": 202},
        headers=HEADERS,
    )
    assert [m["content"] for m in own.json()["messages"]] == ["用户101的消息"]
    assert other.json()["messages"] == []

    cleared = client.delete(
        "/api/ai/session",
        params={"session_id": "shared", "user_id": 202},
        headers=HEADERS,
    )
    assert cleared.status_code == 200
    remaining = client.get(
        "/api/ai/history",
        params={"session_id": "shared", "user_id": 101},
        headers=HEADERS,
    )
    assert [m["content"] for m in remaining.json()["messages"]] == ["用户101的消息"]


def test_session_access_requires_user_id_not_only_session_id(client):
    response = client.get(
        "/api/ai/history",
        params={"session_id": "shared"},
        headers=HEADERS,
    )
    assert response.status_code == 422


def test_same_user_same_session_turn_is_rejected(client):
    lease = memory.acquire_session_turn(1, "busy-session")
    try:
        with pytest.raises(memory.SessionTurnBusy):
            memory.acquire_session_turn(1, "busy-session")

        response = client.post(
            "/api/ai/assistant/stream",
            headers=HEADERS,
            json={"message": "hi", "session_id": "busy-session", "user_id": 1},
        )
        assert response.status_code == 409

        other_user = memory.acquire_session_turn(2, "busy-session")
        other_user.release()
    finally:
        lease.release()

    recovered = memory.acquire_session_turn(1, "busy-session")
    recovered.release()


def test_redis_turn_lock_is_preferred_when_backend_is_redis(monkeypatch):
    class FakeLockRedis:
        def __init__(self):
            self.values = {}
            self.expirations = {}

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.values:
                return None
            self.values[key] = value
            self.expirations[key] = ex
            return True

        def eval(self, _script, _numkeys, key, token):
            if self.values.get(key) != token:
                return 0
            del self.values[key]
            self.expirations.pop(key, None)
            return 1

    fake = FakeLockRedis()
    monkeypatch.setenv("SESSION_BACKEND", "redis")
    monkeypatch.setattr(memory, "_session_redis", lambda: fake)

    lease = memory.acquire_session_turn(1, "redis-session")
    assert fake.values
    assert set(fake.expirations.values()) == {300}
    with pytest.raises(memory.SessionTurnBusy):
        memory.acquire_session_turn(1, "redis-session")
    lease.release()
    assert fake.values == {}


def test_langgraph_thread_id_contains_user_and_session():
    assert assistant_graph._thread_id(7, "session-a") == "7:session-a"
