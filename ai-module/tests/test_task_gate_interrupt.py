"""C3：建任务确认改用 interrupt + Command(resume=...)，替掉全局字典和子串匹配。"""
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from core.assistant_graph import (
    classify_task_reply,
    close_task,
    parse_interrupt_reply,
    submit_task,
    task_gate,
)
from core.langgraph_state import append_messages


def test_classify_task_reply_confirm_cases():
    for text in ("好的，帮我建", "要", "可以", "麻烦你建一条", "是的"):
        assert classify_task_reply(text) == "confirm", text


def test_classify_task_reply_decline_cases():
    for text in ("不用了", "先不用建", "取消", "不需要"):
        assert classify_task_reply(text) == "decline", text


def test_classify_task_reply_falls_back_to_other():
    assert classify_task_reply("那这个是隔壁楼的问题") == "other"
    assert classify_task_reply("") == "other"


def test_classify_task_reply_prefers_decline_over_confirm():
    assert classify_task_reply("不用了，谢谢") == "decline"


class _GateState(TypedDict, total=False):
    messages: Annotated[list, append_messages]
    task_phase: str
    task_offered: bool
    issues: list
    address_text: str
    task_draft: dict
    request_id: str
    submitted: dict
    reentered: bool


def _gate_graph():
    graph = StateGraph(_GateState)
    graph.add_node("task_gate", task_gate)
    graph.add_node("submit_task", lambda s: {"submitted": {"action": "created"}})
    graph.add_node("close_task", close_task)
    graph.add_node("understand", lambda s: {"reentered": True})
    graph.add_edge(START, "task_gate")
    graph.add_edge("submit_task", END)
    graph.add_edge("close_task", END)
    graph.add_edge("understand", END)
    return graph.compile(checkpointer=InMemorySaver())


def _interrupt_payload(events):
    for _mode, item in events:
        if isinstance(item, dict) and "__interrupt__" in item:
            return item["__interrupt__"][0].value
    return None


def test_task_gate_pauses_at_the_interrupt():
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-pause"}}
    events = list(app.stream({"task_phase": "confirm"}, config, stream_mode=["updates"]))
    assert app.get_state(config).next == ("task_gate",)
    payload = _interrupt_payload(events)
    assert payload is not None, "interrupt must surface in the updates stream"
    assert payload["type"] == "confirm_create_task"
    assert "建一条隐患任务" in payload["question"]


def test_task_gate_resume_confirm_reaches_submit():
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-confirm"}}
    for _ in app.stream({"task_phase": "confirm"}, config):
        pass
    for _ in app.stream(Command(resume={
            "decision": "confirm", "address": "三明市梅列区江滨路 1 号"}), config):
        pass
    values = app.get_state(config).values
    assert values["submitted"] == {"action": "created"}
    assert values["task_offered"] is True


def test_task_gate_decline_closes_without_submitting():
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-decline"}}
    for _ in app.stream({"task_phase": "confirm"}, config):
        pass
    for _ in app.stream(Command(resume={"decision": "decline"}), config):
        pass
    values = app.get_state(config).values
    assert "submitted" not in values
    assert values["task_offered"] is True


def test_task_gate_other_re_enters_understand():
    """答非所问：回到 understand 继续处理，而不是把状态塞进全局字典。"""
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-other"}}
    for _ in app.stream({"task_phase": "confirm"}, config):
        pass
    for _ in app.stream(Command(resume={"decision": "other"}), config):
        pass
    assert app.get_state(config).values["reentered"] is True


def test_task_gate_address_phase_captures_free_text():
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-address"}}
    events = list(app.stream({"task_phase": "address"}, config, stream_mode=["updates"]))
    payload = _interrupt_payload(events)
    assert payload["type"] == "ask_address"

    list(app.stream(Command(resume="三明市梅列区江滨路 1 号"), config,
                    stream_mode=["updates"]))
    values = app.get_state(config).values
    assert values["address_text"] == "三明市梅列区江滨路 1 号"
    assert values["submitted"] == {"action": "created"}


def test_gate_is_not_pending_after_submit():
    """建库成功后闸门不再挂起，所以下一轮不会重复创建任务。"""
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-done"}}
    for _ in app.stream({"task_phase": "confirm"}, config):
        pass
    for _ in app.stream(Command(resume={
            "decision": "confirm", "address": "三明市梅列区江滨路 1 号"}), config):
        pass
    assert app.get_state(config).next == ()


def test_stream_bridge_asks_then_creates_the_task(monkeypatch):
    """端到端：第一轮以 interrupt 收尾，第二轮 resume 后建库成功。"""
    import asyncio

    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "_APP", None)
    monkeypatch.setattr("tools.hazard_submit.extract_location",
                        lambda history, latest: "三明市梅列区东新四路万达广场")
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "road", "subcategory_code": "road_occupancy",
            "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"},
        }],
        "categories": ["road/road_occupancy"],
        "category_slots": {"road/road_occupancy": {
            "behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    monkeypatch.setattr(ag, "_run_tool", lambda name, kw, cancellation=None: f"[{name}] {kw}")
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "报告正文")]),
    )
    calls = []

    def fake_submit(user_id, history, latest, *, address_hint="", coords=None,
                    session_id="", request_id="", draft=None):
        calls.append((user_id, latest))
        return {"action": "accepted", "requestId": "req-42"}

    monkeypatch.setattr("tools.hazard_submit.submit_from_history", fake_submit)

    async def turn(message, history, session_id):
        return [event async for event in ag.run_stream_events(
            message=message, history=history, slots={}, vision_summary="",
            session_id=session_id, user_id=7)]

    first = asyncio.run(turn("长期摆摊占着盲道，完全堵死", [], "bridge-task-1"))
    interrupts = [text for kind, text in first if kind == "interrupt"]
    assert interrupts and interrupts[0]["type"] == "confirm_create_task"
    # 问句同时以 chunk 流出，兼容尚未改造的前端
    assert any(kind == "chunk" and "建一条隐患任务" in str(text) for kind, text in first)
    assert first[-1] == ("done", "")
    assert calls == []

    second = asyncio.run(turn(
        "好的",
        [{"role": "user", "content": "长期摆摊占着盲道，完全堵死"},
         {"role": "assistant", "content": "报告正文"}],
        "bridge-task-1",
    ))
    assert any(kind == "chunk" and "已受理，正在创建隐患任务" in str(text) for kind, text in second)
    assert any(kind == "task_accepted" and isinstance(content, dict) and content.get("request_id") == "req-42" for kind, content in second)
    chunk_texts = [str(text) for kind, text in second if kind == "chunk"]
    assert chunk_texts and all("42" not in c for c in chunk_texts)
    assert all("任务编号" not in c for c in chunk_texts)
    assert second[-1] == ("done", "")
    assert calls and calls[0][0] == 7


def test_stream_bridge_emits_task_accepted_with_request_id(monkeypatch):
    """MQ 模式：受理后必须发 task_accepted，且不再发 task_created。"""
    import asyncio

    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "_APP", None)
    monkeypatch.setattr("tools.hazard_submit.extract_location",
                        lambda history, latest: "三明市梅列区东新四路万达广场")
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "road", "subcategory_code": "road_occupancy",
            "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"},
        }],
        "categories": ["road/road_occupancy"],
        "category_slots": {"road/road_occupancy": {
            "behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    monkeypatch.setattr(ag, "_run_tool", lambda name, kw, cancellation=None: f"[{name}] {kw}")
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "报告正文")]),
    )
    monkeypatch.setattr(
        "tools.hazard_submit.submit_from_history",
        lambda *a, **k: {"action": "accepted", "requestId": "req-none"},
    )

    async def turn(message, history, session_id):
        return [event async for event in ag.run_stream_events(
            message=message, history=history, slots={}, vision_summary="",
            session_id=session_id, user_id=7)]

    first = asyncio.run(turn("长期摆摊占着盲道，完全堵死", [], "bridge-noid-1"))
    assert any(kind == "interrupt" for kind, _ in first)
    second = asyncio.run(turn(
        "好的",
        [{"role": "user", "content": "长期摆摊占着盲道，完全堵死"},
         {"role": "assistant", "content": "报告正文"}],
        "bridge-noid-1",
    ))
    assert any(kind == "chunk" and "已受理，正在创建隐患任务" in str(text)
               for kind, text in second)
    assert any(kind == "task_accepted" for kind, _ in second)
    assert not any(kind == "task_created" for kind, _ in second)
    assert second[-1] == ("done", "")


def test_stream_bridge_decline_does_not_submit(monkeypatch):
    import asyncio

    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "_APP", None)
    monkeypatch.setattr("tools.hazard_submit.extract_location",
                        lambda history, latest: "三明市梅列区东新四路万达广场")
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "road", "subcategory_code": "road_occupancy",
            "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"},
        }],
        "categories": ["road/road_occupancy"],
        "category_slots": {"road/road_occupancy": {
            "behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    monkeypatch.setattr(ag, "_run_tool", lambda name, kw, cancellation=None: f"[{name}] {kw}")
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "报告正文")]),
    )
    denied = []
    monkeypatch.setattr("tools.hazard_submit.submit_from_history",
                        lambda *a, **k: denied.append(1) or {"action": "accepted", "requestId": "req-denied"})

    async def turn(message, session_id):
        return [event async for event in ag.run_stream_events(
            message=message, history=[], slots={}, vision_summary="",
            session_id=session_id, user_id=7)]

    asyncio.run(turn("长期摆摊占着盲道，完全堵死", "bridge-decline-1"))
    out = asyncio.run(turn("不用了", "bridge-decline-1"))
    assert any(kind == "chunk" and "不建任务" in str(text) for kind, text in out)
    assert denied == []

class _GateSubmitState(TypedDict, total=False):
    messages: Annotated[list, append_messages]
    user_id: int
    task_phase: str
    task_offered: bool
    issues: list
    address_text: str
    task_draft: dict
    request_id: str
    picked_longitude: float
    picked_latitude: float
    reentered: bool


def _gate_submit_graph():
    """闸门 + 真实 submit_task：用来断言交给 submit_from_history 的参数。"""
    graph = StateGraph(_GateSubmitState)
    graph.add_node("task_gate", task_gate)
    graph.add_node("submit_task", submit_task)
    graph.add_node("close_task", close_task)
    graph.add_node("understand", lambda s: {"reentered": True})
    graph.add_edge(START, "task_gate")
    graph.add_edge("submit_task", END)
    graph.add_edge("close_task", END)
    graph.add_edge("understand", END)
    return graph.compile(checkpointer=InMemorySaver())


def test_after_report_prefills_address_before_confirm(monkeypatch):
    """after_report 在点确认之前把地址预抽进 address_text。"""
    from core import assistant_graph as ag

    monkeypatch.setattr(
        "tools.hazard_submit.extract_location",
        lambda history, latest: "三明市梅列区东新四路万达广场",
    )
    monkeypatch.setattr(ag, "new_request_id", lambda: "req-confirm-fixed")
    state = {
        "messages": [ag.HumanMessage(content="万达广场门口长期摆摊占道")],
        "issues": [{"subcategory_code": "road_occupancy"}],
        "missing": [],
        "report_mode": "full",
        "address_text": "",
    }
    assert ag.after_report(state) == {
        "address_text": "三明市梅列区东新四路万达广场",
        "request_id": "req-confirm-fixed",
    }


def test_after_report_skips_when_address_present_or_no_offer(monkeypatch):
    from core import assistant_graph as ag

    calls = []
    monkeypatch.setattr(
        "tools.hazard_submit.extract_location",
        lambda history, latest: calls.append(1) or "新地址",
    )
    monkeypatch.setattr(ag, "new_request_id", lambda: "req-confirm-fixed")
    assert ag.after_report({
        "issues": [{"subcategory_code": "road_occupancy"}],
        "missing": [], "address_text": "已有地址",
    }) == {"request_id": "req-confirm-fixed"}
    assert ag.after_report({
        "issues": [], "categories": [], "missing": [], "address_text": "",
    }) == {}
    assert calls == []


def test_task_gate_payload_includes_preextracted_address():
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-address-payload"}}
    events = list(app.stream(
        {"task_phase": "confirm", "address_text": "三明市梅列区东新四路万达广场",
         "request_id": "req-confirm-fixed"},
        config, stream_mode=["updates"]))
    payload = _interrupt_payload(events)
    assert payload["type"] == "confirm_create_task"
    assert payload["address"] == "三明市梅列区东新四路万达广场"
    assert payload["request_id"] == "req-confirm-fixed"


def test_task_gate_payload_address_empty_string_when_unknown():
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-address-empty"}}
    events = list(app.stream({"task_phase": "confirm"}, config,
                             stream_mode=["updates"]))
    assert _interrupt_payload(events)["address"] == ""


def test_dict_resume_address_overrides_preextracted(monkeypatch):
    """字典 resume 带改过的地址 -> submit_from_history 收到那个新地址。"""
    captured = {}

    def fake_submit(user_id, history, latest, *, address_hint="", coords=None,
                    session_id="", request_id="", draft=None):
        captured["address_hint"] = address_hint
        captured["coords"] = coords
        captured["request_id"] = request_id
        return {"action": "accepted", "requestId": "req-1"}

    monkeypatch.setattr("tools.hazard_submit.submit_from_history", fake_submit)
    app = _gate_submit_graph()
    config = {"configurable": {"thread_id": "gate-dict-address"}}
    for _ in app.stream(
        {"task_phase": "confirm", "address_text": "预抽取地址",
         "request_id": "req-confirm-fixed"}, config
    ):
        pass
    for _ in app.stream(
        Command(resume={
            "decision": "confirm",
            "request_id": "req-confirm-fixed",
            "address": "梅列区东新四路万达广场",
        }),
        config,
    ):
        pass
    assert captured["address_hint"] == "梅列区东新四路万达广场"
    assert captured["coords"] is None
    assert captured["request_id"] == "req-confirm-fixed"


def test_task_gate_rejects_mismatched_request_id_without_submitting(monkeypatch):
    called = []
    monkeypatch.setattr(
        "tools.hazard_submit.submit_from_history",
        lambda *a, **k: called.append(1) or {"action": "accepted", "requestId": "req-x"},
    )
    app = _gate_submit_graph()
    config = {"configurable": {"thread_id": "gate-request-id-mismatch"}}
    for _ in app.stream(
        {"task_phase": "confirm", "address_text": "预抽取地址",
         "request_id": "req-confirm-fixed"}, config
    ):
        pass
    for _ in app.stream(Command(resume={
        "decision": "confirm",
        "request_id": "req-confirm-other",
    }), config):
        pass
    assert called == []


def test_dict_resume_coords_skip_geocode_and_reach_payload(monkeypatch):
    """字典 resume 带经纬度 -> 不调 geocode，payload 直接用传入坐标。"""
    from tools import hazard_submit

    geocode_calls = []
    monkeypatch.setattr(hazard_submit, "_extract", lambda *a, **k: {
        "category": "traffic/road_occupancy", "address": "预抽取地址",
        "district": "梅列区", "description": "占道", "severity": 1,
    })
    monkeypatch.setattr(
        hazard_submit, "geocode",
        lambda address: geocode_calls.append(address) or {
            "longitude": 1.0, "latitude": 2.0, "district": ""})
    captured = {}
    monkeypatch.setattr(
        hazard_submit, "enqueue_hazard_create",
        lambda user_id, session_id, payload, request_id=None:
        captured.update(payload) or {"ok": True, "requestId": "req-coords"})

    app = _gate_submit_graph()
    config = {"configurable": {"thread_id": "gate-dict-coords"}}
    for _ in app.stream({"task_phase": "confirm", "address_text": "预抽取地址"}, config):
        pass
    for _ in app.stream(
        Command(resume={"decision": "confirm", "longitude": 117.63, "latitude": 26.26}),
        config,
    ):
        pass
    assert geocode_calls == []
    assert captured["longitude"] == 117.63
    assert captured["latitude"] == 26.26


def test_confirm_without_address_self_loops_to_address_phase(monkeypatch):
    """confirm 但最终地址为空 -> 自环回地址追问，不建任务。"""
    called = []
    monkeypatch.setattr("tools.hazard_submit.submit_from_history",
                        lambda *a, **k: called.append(1) or {"action": "accepted", "requestId": "req-called"})
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-empty-address"}}
    for _ in app.stream({"task_phase": "confirm"}, config):
        pass
    list(app.stream(Command(resume={"decision": "confirm"}), config,
                    stream_mode=["updates"]))
    values = app.get_state(config).values
    assert values["task_phase"] == "address"
    assert app.get_state(config).next == ("task_gate",)
    assert called == []


def test_parse_interrupt_reply_only_accepts_dict():
    assert parse_interrupt_reply("") is None
    assert parse_interrupt_reply(None) is None
    assert parse_interrupt_reply("{not json") is None
    assert parse_interrupt_reply("[1, 2]") is None
    assert parse_interrupt_reply('"just text"') is None
    assert parse_interrupt_reply('{"decision": "confirm"}') == {"decision": "confirm"}


def _road_occupancy_plan():
    return {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "road", "subcategory_code": "road_occupancy",
            "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"},
        }],
        "categories": ["road/road_occupancy"],
        "category_slots": {"road/road_occupancy": {
            "behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}},
        "question": "", "answer": "", "needs_search": True,
    }


def _patch_bridge(monkeypatch, ag, submit):
    monkeypatch.setattr(ag, "_APP", None)
    monkeypatch.setattr("tools.hazard_submit.extract_location",
                        lambda history, latest: "预抽取地址")
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _road_occupancy_plan())
    monkeypatch.setattr(ag, "_run_tool",
                        lambda name, kw, cancellation=None: f"[{name}] {kw}")
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "报告正文")]),
    )
    monkeypatch.setattr("tools.hazard_submit.submit_from_history", submit)


async def _bridge_turn(ag, message, session_id, interrupt_reply=""):
    return [event async for event in ag.run_stream_events(
        message=message, history=[], slots={}, vision_summary="",
        session_id=session_id, user_id=7, interrupt_reply=interrupt_reply)]


def test_interrupt_reply_address_end_to_end(monkeypatch):
    """interrupt_reply（JSON）带改过的地址 -> 新路径生效，submit 收到新地址。"""
    import asyncio
    import json

    import core.assistant_graph as ag

    captured = {}

    def fake_submit(user_id, history, latest, *, address_hint="", coords=None,
                    session_id="", request_id="", draft=None):
        captured["address_hint"] = address_hint
        captured["coords"] = coords
        return {"action": "accepted", "requestId": "req-5"}

    _patch_bridge(monkeypatch, ag, fake_submit)
    asyncio.run(_bridge_turn(ag, "长期摆摊占着盲道，完全堵死", "bridge-addr-2"))
    reply = json.dumps({"decision": "confirm", "address": "梅列区东新四路万达广场"})
    out = asyncio.run(_bridge_turn(ag, "好的", "bridge-addr-2", interrupt_reply=reply))
    assert captured["address_hint"] == "梅列区东新四路万达广场"
    assert any(kind == "chunk" and "已受理，正在创建隐患任务" in str(text) for kind, text in out)


def test_bad_interrupt_reply_falls_back_to_classify(monkeypatch):
    """坏 interrupt_reply -> 回落 classify_task_reply（好的 -> confirm），行为不变。"""
    import asyncio

    import core.assistant_graph as ag

    captured = {}

    def fake_submit(user_id, history, latest, *, address_hint="", coords=None,
                    session_id="", request_id="", draft=None):
        captured["address_hint"] = address_hint
        return {"action": "accepted", "requestId": "req-6"}

    _patch_bridge(monkeypatch, ag, fake_submit)
    asyncio.run(_bridge_turn(ag, "长期摆摊占着盲道，完全堵死", "bridge-bad-2"))
    out = asyncio.run(_bridge_turn(ag, "好的", "bridge-bad-2", interrupt_reply="{broken"))
    assert captured["address_hint"] == "预抽取地址"
    assert any(kind == "chunk" and "已受理，正在创建隐患任务" in str(text) for kind, text in out)
def test_task_gate_interrupt_redacts_evidence_fields():
    app = _gate_graph()
    config = {"configurable": {"thread_id": "gate-redaction"}}
    events = list(app.stream({
        "task_phase": "confirm",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "杂物"},
            "evidence": [{"slot": "blocker", "quote": "通道有杂物", "source_ref": "u1"}],
            "slot_evidence": {
                "blocker": {"status": "grounded", "quote": "通道有杂物", "source_ref": "u1"},
            },
        }],
    }, config, stream_mode=["updates"]))
    payload = _interrupt_payload(events)
    issue = payload["issues"][0]
    assert "evidence" not in issue
    assert "slot_evidence" not in issue
    assert issue["slots"] == {"blocker": "杂物"}