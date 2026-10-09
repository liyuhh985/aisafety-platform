"""C3：建任务确认改用 interrupt + Command(resume=...)，替掉全局字典和子串匹配。"""
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from core.assistant_graph import classify_task_reply, close_task, task_gate
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
    address_text: str
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
    for _ in app.stream(Command(resume={"decision": "confirm"}), config):
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
    for _ in app.stream(Command(resume={"decision": "confirm"}), config):
        pass
    assert app.get_state(config).next == ()


def test_stream_bridge_asks_then_creates_the_task(monkeypatch):
    """端到端：第一轮以 interrupt 收尾，第二轮 resume 后建库成功。"""
    import asyncio

    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "_APP", None)
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

    def fake_submit(user_id, history, latest):
        calls.append((user_id, latest))
        return {"action": "created", "hazardId": 42}

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
    assert any(kind == "chunk" and "已创建隐患任务" in str(text) for kind, text in second)
    assert ("task_created", {"hazard_id": 42, "hazard_code": "#HAZ-42"}) in second
    chunk_texts = [str(text) for kind, text in second if kind == "chunk"]
    assert chunk_texts and all("42" not in c for c in chunk_texts)
    assert all("任务编号" not in c for c in chunk_texts)
    assert second[-1] == ("done", "")
    assert calls and calls[0][0] == 7


def test_stream_bridge_skips_task_created_without_hazard_id(monkeypatch):
    """边界：hazardId 为 None 时不发 task_created 事件，也不抛异常。"""
    import asyncio

    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "_APP", None)
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
        lambda *a, **k: {"action": "created", "hazardId": None},
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
    assert any(kind == "chunk" and "已创建隐患任务" in str(text)
               for kind, text in second)
    assert not any(kind == "task_created" for kind, _ in second)
    assert second[-1] == ("done", "")


def test_stream_bridge_decline_does_not_submit(monkeypatch):
    import asyncio

    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "_APP", None)
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
                        lambda *a, **k: denied.append(1) or {"action": "created"})

    async def turn(message, session_id):
        return [event async for event in ag.run_stream_events(
            message=message, history=[], slots={}, vision_summary="",
            session_id=session_id, user_id=7)]

    asyncio.run(turn("长期摆摊占着盲道，完全堵死", "bridge-decline-1"))
    out = asyncio.run(turn("不用了", "bridge-decline-1"))
    assert any(kind == "chunk" and "不建任务" in str(text) for kind, text in out)
    assert denied == []
