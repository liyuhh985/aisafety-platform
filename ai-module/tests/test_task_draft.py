# -*- coding: utf-8 -*-
"""报告阶段并行建单草稿：生成、兜底、确认清洗与旧路径兼容。"""
import json
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from core.assistant_graph import close_task, submit_task, task_gate
from core.langgraph_state import append_messages


class _DraftState(TypedDict, total=False):
    messages: Annotated[list, append_messages]
    user_id: int
    session_id: str
    locked_majors: list[str]
    categories: list[str]
    task_phase: str
    task_offered: bool
    task_draft: dict
    address_text: str
    request_id: str
    picked_longitude: float
    picked_latitude: float
    reentered: bool


def _submit_graph():
    graph = StateGraph(_DraftState)
    graph.add_node("task_gate", task_gate)
    graph.add_node("submit_task", submit_task)
    graph.add_node("close_task", close_task)
    graph.add_node("understand", lambda s: {"reentered": True})
    graph.add_edge(START, "task_gate")
    graph.add_edge("submit_task", END)
    graph.add_edge("close_task", END)
    graph.add_edge("understand", END)
    return graph.compile(checkpointer=InMemorySaver())


def _interrupt_payload(events):
    for mode, item in events:
        if mode == "updates" and isinstance(item, dict) and "__interrupt__" in item:
            return item["__interrupt__"][0].value
    return None


def _custom_chunks(events):
    return [item["chunk"] for mode, item in events
            if mode == "custom" and isinstance(item, dict) and "chunk" in item]


def _draft(**overrides):
    value = {
        "categoryList": ["traffic/road_occupancy"],
        "address": "三明市梅列区江滨路 1 号",
        "district": "梅列区",
        "description": "占道",
        "severity": 1,
        "longitude": None,
        "latitude": None,
        "image_file_id": None,
    }
    value.update(overrides)
    return value


def test_build_task_draft_uses_state_and_model_only_adds_description_severity(monkeypatch):
    from tools import hazard_submit

    cancellation = object()
    calls = []

    def fake_llm(messages, cancellation=None):
        calls.append((messages, cancellation))
        return {"content": json.dumps({
            "description": "摊贩长期占用盲道",
            "severity": 2,
            "address": "模型不应覆盖地址",
            "categoryList": ["fire/fire_equipment_fault"],
        }, ensure_ascii=False)}

    monkeypatch.setattr(hazard_submit._extractor, "_call_llm", fake_llm)
    state = {
        "categories": [
            "traffic/road_occupancy", "municipal/manhole_damage",
            "fire/fire_equipment_fault", "utility/exposed_wire",
        ],
        "address_text": "三明市梅列区江滨路 1 号",
        "district": "梅列区",
        "category_slots": {"traffic/road_occupancy": {"behavior": "摆摊"}},
        "messages": [HumanMessage(content="最近一句：盲道被摊贩堵死")],
        "picked_longitude": 117.6,
        "picked_latitude": 26.2,
        "image_file_id": 9,
    }

    draft = hazard_submit.build_task_draft(state, cancellation)

    assert len(calls) == 1
    assert calls[0][1] is cancellation
    prompt = calls[0][0][0]["content"]
    assert "盲道被摊贩堵死" in prompt
    assert "elevator_special" not in prompt
    assert draft["categoryList"] == state["categories"][:3]
    assert draft["address"] == state["address_text"]
    assert draft["district"] == "梅列区"
    assert draft["description"] == "摊贩长期占用盲道"
    assert draft["severity"] == 2
    assert draft["longitude"] == 117.6
    assert draft["latitude"] == 26.2
    assert draft["image_file_id"] == 9


def test_build_task_draft_returns_fallback_on_exception_and_bad_json(monkeypatch):
    from tools import hazard_submit

    state = {
        "categories": ["traffic/road_occupancy"],
        "address_text": "三明市梅列区江滨路 1 号",
        "district": "梅列区",
        "messages": [HumanMessage(content="占道")],
    }

    def raise_error(*args, **kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(hazard_submit._extractor, "_call_llm", raise_error)
    draft = hazard_submit.build_task_draft(state, None)
    assert draft["categoryList"] == ["traffic/road_occupancy"]
    assert draft["address"] == "三明市梅列区江滨路 1 号"
    assert draft["description"] == ""
    assert draft["severity"] == 1

    monkeypatch.setattr(
        hazard_submit._extractor, "_call_llm",
        lambda *a, **k: {"content": "这不是 JSON"},
    )
    draft = hazard_submit.build_task_draft(state, None)
    assert draft["description"] == ""
    assert draft["severity"] == 1


def test_structured_confirm_submits_cleaned_draft_without_extract(monkeypatch):
    from tools import hazard_submit

    submitted = {}
    extract_calls = []

    def fake_submit(user_id, history, latest, **kwargs):
        submitted.update(kwargs)
        return {"action": "accepted", "requestId": "req-draft"}

    monkeypatch.setattr(hazard_submit, "submit_from_history", fake_submit)
    monkeypatch.setattr(
        hazard_submit, "_extract",
        lambda *a, **k: extract_calls.append(1) or {},
    )

    app = _submit_graph()
    config = {"configurable": {"thread_id": "draft-clean"}}
    list(app.stream({
        "task_phase": "confirm", "request_id": "req-draft",
        "locked_majors": ["traffic"], "address_text": "旧地址",
        "task_draft": _draft(address="旧地址"),
    }, config))
    list(app.stream(Command(resume={
        "decision": "confirm", "request_id": "req-draft",
        "draft": _draft(
            address="  梅列区东新四路万达广场  ",
            description="描" * 600,
            severity=2,
            longitude="bad",
            latitude=True,
        ),
    }), config))

    assert extract_calls == []
    draft = submitted["draft"]
    assert draft["categoryList"] == ["traffic/road_occupancy"]
    assert draft["address"] == "梅列区东新四路万达广场"
    assert draft["description"] == "描" * 500
    assert draft["severity"] == 2
    assert draft["longitude"] is None
    assert draft["latitude"] is None
    assert app.get_state(config).values["task_draft"] == draft


def test_cross_locked_major_draft_is_rejected_with_warning(monkeypatch):
    from tools import hazard_submit

    submitted = []
    monkeypatch.setattr(
        hazard_submit, "submit_from_history",
        lambda *a, **k: submitted.append(1) or {"action": "accepted", "requestId": "x"},
    )
    app = _submit_graph()
    config = {"configurable": {"thread_id": "draft-reject"}}
    list(app.stream({
        "task_phase": "confirm", "request_id": "req-reject",
        "locked_majors": ["traffic"], "task_draft": _draft(),
    }, config))
    events = list(app.stream(Command(resume={
        "decision": "confirm", "request_id": "req-reject",
        "draft": _draft(categoryList=["fire/fire_equipment_fault"]),
    }), config, stream_mode=["updates", "custom"]))

    assert submitted == []
    assert app.get_state(config).next == ()
    assert any("暂不创建任务" in str(text) for text in _custom_chunks(events))


def test_mixed_cross_locked_major_categories_are_filtered(monkeypatch):
    from tools import hazard_submit

    submitted = {}

    def fake_submit(user_id, history, latest, **kwargs):
        submitted.update(kwargs)
        return {"action": "accepted", "requestId": "req-mixed"}

    monkeypatch.setattr(hazard_submit, "submit_from_history", fake_submit)
    app = _submit_graph()
    config = {"configurable": {"thread_id": "draft-mixed"}}
    list(app.stream({
        "task_phase": "confirm", "request_id": "req-mixed",
        "locked_majors": ["traffic"], "task_draft": _draft(),
    }, config))
    list(app.stream(Command(resume={
        "decision": "confirm", "request_id": "req-mixed",
        "draft": _draft(categoryList=[
            "fire/fire_equipment_fault", "traffic/road_occupancy",
        ]),
    }), config))

    assert submitted["draft"]["categoryList"] == ["traffic/road_occupancy"]


def test_empty_draft_address_returns_to_ask_address(monkeypatch):
    from tools import hazard_submit

    submitted = []
    monkeypatch.setattr(
        hazard_submit, "submit_from_history",
        lambda *a, **k: submitted.append(1) or {"action": "accepted", "requestId": "x"},
    )
    app = _submit_graph()
    config = {"configurable": {"thread_id": "draft-empty-address"}}
    list(app.stream({
        "task_phase": "confirm", "request_id": "req-empty",
        "locked_majors": ["traffic"], "address_text": "旧地址",
        "task_draft": _draft(address="旧地址"),
    }, config))
    events = list(app.stream(Command(resume={
        "decision": "confirm", "request_id": "req-empty",
        "draft": _draft(address=""),
    }), config, stream_mode=["updates", "custom"]))

    payload = _interrupt_payload(events)
    assert payload["type"] == "ask_address"
    assert app.get_state(config).values["task_phase"] == "address"
    assert app.get_state(config).next == ("task_gate",)
    assert submitted == []


def test_interrupt_payload_carries_report_draft():
    app = _submit_graph()
    config = {"configurable": {"thread_id": "draft-payload"}}
    events = list(app.stream({
        "task_phase": "confirm", "task_draft": _draft(),
    }, config, stream_mode=["updates", "custom"]))
    assert _interrupt_payload(events)["draft"]["description"] == "占道"


def test_plain_text_reply_still_uses_extract(monkeypatch):
    from tools import hazard_submit

    extract_calls = []
    payloads = []
    monkeypatch.setattr(
        hazard_submit, "_extract",
        lambda *a, **k: extract_calls.append(1) or {
            "category": "traffic/road_occupancy",
            "categoryList": ["traffic/road_occupancy"],
            "address": "三明市梅列区江滨路 1 号",
            "district": "梅列区",
            "description": "旧抽取描述",
            "severity": 1,
        },
    )
    monkeypatch.setattr(
        hazard_submit, "geocode",
        lambda address: {"longitude": 117.6, "latitude": 26.2, "district": "梅列区"},
    )

    def fake_enqueue(user_id, session_id, payload, **kwargs):
        payloads.append(payload)
        return {"ok": True, "requestId": "req-text", "status": "PENDING"}

    monkeypatch.setattr(hazard_submit, "enqueue_hazard_create", fake_enqueue)
    app = _submit_graph()
    config = {"configurable": {"thread_id": "draft-text-path"}}
    list(app.stream({
        "task_phase": "confirm", "request_id": "req-text",
        "address_text": "三明市梅列区江滨路 1 号",
        "task_draft": _draft(description="报告草稿", severity=2),
    }, config))
    list(app.stream(Command(resume="好的"), config))

    assert extract_calls == [1]
    assert payloads[0]["description"] == "旧抽取描述"
    assert payloads[0]["severity"] == 1
