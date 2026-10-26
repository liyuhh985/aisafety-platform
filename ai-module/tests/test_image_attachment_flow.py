import inspect

from core import assistant_graph as ag
from server import assistant_stream


def test_turn_input_preserves_uploaded_file_identity():
    state = ag.build_turn_input(
        "sid-1",
        "请处置这张图片",
        "[视觉分析] ok",
        "",
        image_url="/api/files/88",
        image_file_id=88,
    )

    assert state["image_url"] == "/api/files/88"
    assert state["image_file_id"] == 88


def test_submit_task_forwards_image_identity_to_outbox(monkeypatch):
    captured = {}

    def fake_submit(user_id, history, latest, **kwargs):
        captured.update(user_id=user_id, latest=latest, **kwargs)
        return {"action": "accepted", "requestId": "req-image"}

    monkeypatch.setattr("tools.hazard_submit.submit_from_history", fake_submit)
    monkeypatch.setattr(ag, "_emit_chunk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ag, "_emit_event", lambda *_args, **_kwargs: None)

    ag.submit_task({
        "user_id": 7,
        "session_id": "sid-1",
        "messages": [],
        "address_text": "某小区消防通道",
        "image_url": "/api/files/88",
        "image_file_id": 88,
    })

    assert captured["image_url"] == "/api/files/88"
    assert captured["image_file_id"] == 88


def test_assistant_stream_accepts_image_identity_fields():
    params = inspect.signature(assistant_stream).parameters

    assert "image_url" in params
    assert "image_file_id" in params

def test_turn_without_new_upload_does_not_overwrite_previous_file_identity():
    state = ag.build_turn_input("sid-1", "确认建单", "", "")

    assert "image_url" not in state
    assert "image_file_id" not in state


def test_accepted_task_clears_image_identity_after_use(monkeypatch):
    def fake_submit(user_id, history, latest, **kwargs):
        return {"action": "accepted", "requestId": "req-image"}

    monkeypatch.setattr("tools.hazard_submit.submit_from_history", fake_submit)
    monkeypatch.setattr(ag, "_emit_chunk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ag, "_emit_event", lambda *_args, **_kwargs: None)

    command = ag.submit_task({
        "user_id": 7,
        "session_id": "sid-1",
        "messages": [],
        "address_text": "某小区消防通道",
        "image_url": "/api/files/88",
        "image_file_id": 88,
    })

    assert command.update["image_file_id"] is None
    assert command.update["image_url"] == ""

def test_failed_submit_keeps_image_for_retry(monkeypatch):
    def fake_submit(user_id, history, latest, **kwargs):
        return {"action": "no_category", "message": "重新选择类别"}

    monkeypatch.setattr("tools.hazard_submit.submit_from_history", fake_submit)
    monkeypatch.setattr(ag, "_emit_chunk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ag, "_emit_event", lambda *_args, **_kwargs: None)

    command = ag.submit_task({
        "user_id": 7,
        "session_id": "sid-1",
        "messages": [],
        "address_text": "某小区消防通道",
        "image_url": "/api/files/88",
        "image_file_id": 88,
    })

    assert "image_file_id" not in command.update


def test_declined_task_clears_image_for_next_hazard():
    result = ag.close_task({})

    assert result["image_file_id"] is None
    assert result["image_url"] == ""
