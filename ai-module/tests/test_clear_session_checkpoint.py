from core import assistant_graph as ag


def test_clear_thread_deletes_langgraph_checkpoint(monkeypatch):
    deleted = []

    class Saver:
        def delete_thread(self, thread_id):
            deleted.append(thread_id)

    monkeypatch.setattr(ag, "get_checkpointer", lambda: Saver())

    ag.clear_thread(7, "sid-1")

    assert deleted == ["7:sid-1"]

import pytest
from fastapi import HTTPException
from core.memory import SessionTurnBusy
import server


def test_clear_session_rejects_active_turn(monkeypatch):
    def busy(*_args, **_kwargs):
        raise SessionTurnBusy("busy")

    monkeypatch.setattr(server, "acquire_session_turn", busy)

    with pytest.raises(HTTPException) as raised:
        server.clear_session(session_id="sid-1", user_id=7)

    assert raised.value.status_code == 409


def test_clear_session_releases_turn_lease(monkeypatch):
    released = []
    cleared = []

    class Lease:
        def release(self):
            released.append(True)

    class Memory:
        def clear(self):
            cleared.append(True)

    monkeypatch.setattr(server, "acquire_session_turn", lambda *_args: Lease())
    monkeypatch.setattr(server, "get_session", lambda *_args: Memory())
    monkeypatch.setattr(server, "clear_thread", lambda user_id, session_id: cleared.append((user_id, session_id)))

    result = server.clear_session(session_id="sid-1", user_id=7)

    assert result["status"] == "cleared"
    assert cleared == [(7, "sid-1"), True]
    assert released == [True]
