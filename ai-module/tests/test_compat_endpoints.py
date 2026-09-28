"""兼容入口：老 URL 仍在，但内部跑同一张助手图。"""
import json

from fastapi.testclient import TestClient

import server


def _fake_graph(events):
    async def _run(**_kwargs):
        for kind, text in events:
            yield (kind, text)
    return _run


def test_the_four_compat_routes_still_exist():
    paths = {route.path for route in server.app.routes}
    for path in ("/api/ai/analyze", "/api/ai/analyze/stream",
                 "/api/ai/chat", "/api/ai/chat/stream"):
        assert path in paths, path


def test_sse_payload_shape():
    raw = server._sse("report", "abc")
    assert raw.startswith("data: ") and raw.endswith(chr(10) * 2)
    assert json.loads(raw[6:].strip()) == {"type": "report", "content": "abc"}


def test_find_vision_summary():
    history = [{"role": "user", "content": "hi"},
               {"role": "system", "content": "[视觉分析] {}"}]
    assert server._find_vision_summary(history) == "[视觉分析] {}"
    assert server._find_vision_summary([]) == ""


def test_compat_vision_without_a_file_is_a_noop():
    assert server._compat_vision(None) == (None, [])


def test_analyze_keeps_the_old_response_shape(monkeypatch):
    monkeypatch.setattr(server, "assistant_graph_stream", _fake_graph([
        ("status", "x"), ("chunk", "报告"), ("chunk", "正文"),
        ("taxonomy", {"issues": []}), ("done", ""),
    ]))
    resp = TestClient(server.app).post(
        "/api/ai/analyze", data={"text": "消防通道被堵", "session_id": "compat-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "compat-1"
    assert body["report"] == "报告正文"
    assert body["vision"] is None
    assert "reply" not in body


def test_analyze_stream_maps_chunk_to_report(monkeypatch):
    monkeypatch.setattr(server, "assistant_graph_stream", _fake_graph([
        ("status", "thinking"), ("chunk", "A"), ("taxonomy", {}), ("done", ""),
    ]))
    resp = TestClient(server.app).post(
        "/api/ai/analyze/stream", data={"text": "x", "session_id": "compat-2"})
    types = [json.loads(line[6:])["type"]
             for line in resp.text.splitlines() if line.startswith("data: ")]
    assert "status" in types and "report" in types and "done" in types
    assert "taxonomy" not in types


def test_chat_returns_reply(monkeypatch):
    monkeypatch.setattr(server, "assistant_graph_stream", _fake_graph([("chunk", "回话")]))
    resp = TestClient(server.app).post(
        "/api/ai/chat", data={"message": "然后呢", "session_id": "compat-3"})
    assert resp.json() == {"session_id": "compat-3", "reply": "回话"}


def test_chat_stream_passes_events_through(monkeypatch):
    monkeypatch.setattr(server, "assistant_graph_stream", _fake_graph([("chunk", "B")]))
    resp = TestClient(server.app).post(
        "/api/ai/chat/stream", data={"message": "嗯", "session_id": "compat-4"})
    assert "data: " in resp.text and '"chunk"' in resp.text
