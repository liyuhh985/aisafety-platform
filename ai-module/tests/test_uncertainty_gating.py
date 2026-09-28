"""不确定性信号接进回合：紧急不再劫持本轮，追问/完整报告被按信号禁止。"""
from tests.reply_helpers import (collect_chunks, fake_report_model,
                                  render_reply, render_update, run_turn,
                                  streamed_text)
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag


def _plan(**overrides):
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "fire", "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "浓烟", "persistence": "持续中", "impact": "人员无法疏散"},
        }],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {
            "blocker": "浓烟", "persistence": "持续中", "impact": "人员无法疏散"}},
        "question": "被什么东西堵住了？", "answer": "我理解为消防通道被占。",
        "needs_search": True,
    }
    plan.update(overrides)
    return plan


def test_understand_no_longer_hijacks_an_emergency_turn(monkeypatch):
    """紧急不再提前返回：这轮仍要走规划器，才能拿到信号并继续检索/报告。"""
    seen = {}

    def fake_plan(messages, vision_summary, selected_major_code=""):
        seen["called"] = True
        return _plan()

    monkeypatch.setattr(ag, "_understand_plan", fake_plan)
    out = ag.understand({"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]})
    assert seen.get("called") is True
    assert out["danger_veto"] is True
    assert out["uncertainty_level"] == "cautious"
    # 编造的槽位被抓出来，而原文里真有依据的 blocker=浓烟 不能被误伤
    assert "fire_lane_blocked.persistence=持续中" in out["ungrounded_slots"]
    assert not any(item.startswith("fire_lane_blocked.blocker=")
                   for item in out["ungrounded_slots"])


def test_understand_forbids_questions_under_a_danger_veto(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    out = ag.understand({"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]})
    assert out["clarification_question"] == ""
    assert out["next_action"] != "ask_critical_question"


def test_understand_downgrades_to_preliminary_when_cautious(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    # 输入换成"非危险句"：本例断言的是 cautious→初步报告，不是危险路径。
    # 原输入是危险句，现在会走 emergency_guidance（见 tests/test_emergency_guidance.py）。
    # 新输入不含 _plan() 里的槽位值（浓烟/持续中/人员无法疏散）→ 未接地 → cautious。
    out = ag.understand({"messages": [HumanMessage(content="我们小区的消防通道长期堆着杂物")]})
    assert out["next_action"] == "report_preliminary"
    assert out["report_mode"] == "preliminary"


def test_routine_hazard_is_neither_vetoed_nor_cautious(monkeypatch):
    monkeypatch.setattr(
        ag, "_understand_plan",
        lambda *a, **k: _plan(
            issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                     "slots": {"blocker": "杂物", "persistence": "长期"}}],
            category_slots={"fire_lane_blocked": {"blocker": "杂物", "persistence": "长期"}},
            question="", answer="",
        ),
    )
    out = ag.understand({
        "messages": [HumanMessage(content="紧急出口被杂物堵住了，长期堆放")],
    })
    assert out["danger_veto"] is False
    assert out["uncertainty_level"] == "ok"


def test_scope_guard_does_not_downgrade_a_vetoed_turn(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    understood = ag.understand({"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]})
    update = ag.scope_guard({
        **understood,
        "messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")],
        "session_id": "veto-1",
    })
    assert update["scope"] == "emergency"


def test_a_failed_planner_still_honours_the_danger_veto(monkeypatch):
    """规划器挂掉时，漏词的紧急消息不能再被回成越界拒绝。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: {})
    out = ag.understand({"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]})
    assert out["danger_veto"] is True
    update = ag.scope_guard({
        **out,
        "messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")],
        "session_id": "veto-2",
    })
    assert update["scope"] == "emergency"


def test_state_exposes_the_uncertainty_fields():
    from core.langgraph_state import AssistantState
    for key in ("uncertainty_level", "danger_veto", "ungrounded_slots",
                "grounding_ratio", "uncertainty_signals"):
        assert key in AssistantState.__annotations__


def test_guidance_is_prepended_by_code_even_when_the_model_omits_it(monkeypatch):
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "### 一、触犯法规\n- 《消防法》第28条")]),
    )
    update = ag.report({
        "messages": [], "categories": ["fire_lane_blocked"],
        "category_results": {"fire_lane_blocked": {"regulation": "法", "case": "案例"}},
        "missing": [], "issues": [{"subcategory_code": "fire_lane_blocked"}],
        "report_mode": "preliminary", "danger_veto": True,
    })
    assert "119" in update["draft_report"]
    assert update["draft_report"].index("119") < update["draft_report"].index("消防法")


def test_report_streams_the_guidance_before_the_body(monkeypatch):
    """报告先流式再落 draft，无法事后判重：

    这里保证的是"指引一定排在最前面且至少出现一次"，去重留给能拿到完整文本的路径。
    """
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "请立即拨打 119 报警")]),
    )
    update = ag.report({
        "messages": [], "categories": ["fire_lane_blocked"],
        "category_results": {}, "missing": [],
        "issues": [{"subcategory_code": "fire_lane_blocked"}],
        "report_mode": "preliminary", "danger_veto": True,
    })
    draft = update["draft_report"]
    assert draft.count("119") >= 1
    assert draft.startswith(ag.GUIDANCE_LINE)


def test_guidance_is_not_duplicated_when_the_answer_already_says_119(monkeypatch):
    """direct_reply 能拿到完整文本，所以在这里判重。"""
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    update = render_update({
        "direct_mode": "", "next_action": "answer_now", "danger_veto": True,
        "messages": [],
        "dialogue_plan": {"ok": True, "answer": "请立即拨打 119 报警。", "question": ""},
    })
    assert update["messages"][-1].content.count("119") == 1


def test_guidance_is_skipped_when_understand_already_emitted_it(monkeypatch):
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "报告正文")]),
    )
    update = ag.report({
        "messages": [], "categories": ["fire_lane_blocked"],
        "category_results": {}, "missing": [],
        "issues": [{"subcategory_code": "fire_lane_blocked"}],
        "report_mode": "preliminary", "danger_veto": True, "guidance_emitted": True,
    })
    assert "119" not in update["draft_report"]


def test_cautious_reply_states_its_interpretation(monkeypatch):
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    update = render_update({
        "direct_mode": "", "next_action": "report_preliminary",
        "clarification_question": "", "uncertainty_level": "cautious",
        "ungrounded_slots": ["fire_lane_blocked.persistence=持续中"],
        "messages": [],
        "dialogue_plan": {"ok": True, "answer": "我理解为消防通道被占。", "question": ""},
    })
    content = update["messages"][-1].content
    assert "核实" in content
    assert "？" not in content


def test_vetoed_reply_never_ends_in_a_question(monkeypatch):
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    update = render_update({
        "direct_mode": "", "next_action": "answer_now", "danger_veto": True,
        "clarification_question": "被什么东西堵住了？",
        "messages": [],
        "dialogue_plan": {"ok": True, "answer": "浓烟环境应低姿撤离。", "question": ""},
    })
    content = update["messages"][-1].content
    assert "119" in content
    assert "？" not in content


def test_understand_emits_no_safety_text_and_the_node_owns_it(monkeypatch):
    """新契约：安全文本的唯一出处是 emergency_guidance。

    understand 不再在调模型之前先发一句；危险信号照样设置，规划器照常参与。
    """
    seen = {}

    def slow_plan(messages, vision_summary, selected_major_code=""):
        seen["called"] = True
        return {"ok": True, "intent": "other", "issues": [], "categories": [],
                "category_slots": {}, "question": "", "answer": "",
                "needs_search": False}

    monkeypatch.setattr(ag, "_understand_plan", slow_plan)
    chunks = collect_chunks(monkeypatch)
    out = ag.understand({"messages": [HumanMessage(content="楼下着火了，有人被困")]})
    assert out["danger_veto"] is True
    assert out["guidance_emitted"] is True
    assert streamed_text(chunks) == ""
    assert seen.get("called") is True
    fake_report_model(monkeypatch, "马上从楼梯撤离到楼下，并拨打 119 报警。")
    nodes, answer, _values = run_turn(
        ag.build_graph(), {"configurable": {"thread_id": "emg-single-source"}},
        "楼下着火了，有人被困")
    assert "emergency_guidance" in nodes
    assert nodes.index("emergency_guidance") > nodes.index("route")
    assert "119" in answer
