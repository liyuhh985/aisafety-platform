# -*- coding: utf-8 -*-
"""缺口 1：第 1 轮问句的来源（ask_slot_question 节点）。

为什么不能"再跑一次完整 understand"：那会让第 1 轮多一次全量调用、可能两次分类不一致
（锁会乱），而且会变成第二个事实写入者 —— 项目不变式是「understand 是唯一的事实写入者」。
所以新节点只读事实、只写一句问句。
"""
import copy
import logging

import pytest
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag
from core.dialogue_understanding import (
    parse_slot_question,
    resolve_slot_question,
    schema_question_for_missing,
    slot_question_targets_missing,
)
from tests.reply_helpers import collect_chunks, run_turn, streamed_text

FACT_KEYS = ("locked_major", "locked_subcategory", "issues", "category_slots", "missing")

MANHOLE_STATE = {
    "messages": [HumanMessage(content="楼下井盖有问题")],
    "locked_major": "traffic",
    "locked_subcategory": "manhole_damage",
    "category_slots": {"manhole_damage": {}},
    "missing": ["manhole_damage_defect"],
    "issues": [{"major_code": "traffic", "subcategory_code": "manhole_damage",
                "slots": {}, "missing": ["defect"]}],
    "next_action": "ask_critical_question",
    "clarification_question": "井盖是缺失、破损还是松动？",
}


def _plan(**overrides):
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [], "categories": [], "category_slots": {},
        "question": "", "answer": "", "needs_search": True,
    }
    plan.update(overrides)
    return plan


# ---------------------------------------------------------------- 1. 只读事实

def test_node_only_writes_the_question(monkeypatch):
    """只读事实的不变式：跑完节点，五个事实字段逐字未变。"""
    monkeypatch.setattr(ag, "_slot_question_llm",
                        lambda **kw: {"question": "井盖是没了还是只是松动？", "target_slot": "defect"})
    state = copy.deepcopy(MANHOLE_STATE)
    before = {key: copy.deepcopy(state[key]) for key in FACT_KEYS}
    cmd = ag.ask_slot_question(state)
    merged = {**state, **(cmd.update or {})}
    for key in FACT_KEYS:
        assert merged[key] == before[key], key
    assert set(cmd.update or {}) <= {"clarification_question", "question_source",
                                     "asked_question_last_turn"}


def test_node_never_touches_the_lock_even_when_the_model_returns_junk(monkeypatch):
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: {"question": "x", "target_slot": "别的"})
    state = copy.deepcopy(MANHOLE_STATE)
    cmd = ag.ask_slot_question(state)
    merged = {**state, **(cmd.update or {})}
    assert merged["locked_major"] == "traffic"
    assert merged["locked_subcategory"] == "manhole_damage"


# ---------------------------------------------------------------- 2. 校验（纯函数）

def test_target_check_is_pure_and_exact():
    assert slot_question_targets_missing("persistence", ["persistence", "impact"])
    assert not slot_question_targets_missing("impact", ["persistence"])
    assert not slot_question_targets_missing("", ["persistence"])
    assert not slot_question_targets_missing(None, ["persistence"])
    assert not slot_question_targets_missing("persistence", [])


def test_parse_slot_question_survives_code_fences_and_junk():
    raw = "```json\n" + '{"target_slot": "defect", "question": "井盖怎么了？"}' + "\n```"
    assert parse_slot_question(raw) == {"question": "井盖怎么了？", "target_slot": "defect"}
    assert parse_slot_question("没有 JSON") == {}
    assert parse_slot_question("") == {}


def test_schema_question_follows_the_schema_order():
    assert schema_question_for_missing(["persistence"], "fire_lane_blocked") == "是长期还是临时？"


# ---------------------------------------------------------------- 3. 三级降级

def test_level1_new_node_wins_when_it_targets_a_missing_slot(monkeypatch):
    monkeypatch.setattr(ag, "_slot_question_llm",
                        lambda **kw: {"question": "井盖是没了还是只是松动？", "target_slot": "defect"})
    cmd = ag.ask_slot_question(copy.deepcopy(MANHOLE_STATE))
    assert cmd.update["clarification_question"] == "井盖是没了还是只是松动？"
    assert cmd.update["question_source"] == "ask_slot_question"


def test_level2_falls_back_to_the_question_understand_already_had(monkeypatch):
    monkeypatch.setattr(ag, "_slot_question_llm",
                        lambda **kw: {"question": "这个井盖在哪个小区？", "target_slot": "location"})
    cmd = ag.ask_slot_question(copy.deepcopy(MANHOLE_STATE))
    assert cmd.update["clarification_question"] == "井盖是缺失、破损还是松动？"
    assert cmd.update["question_source"] == "understand"


def test_level3_falls_back_to_the_slot_schema_question(monkeypatch):
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: {})
    state = copy.deepcopy(MANHOLE_STATE)
    state["clarification_question"] = ""
    cmd = ag.ask_slot_question(state)
    assert cmd.update["clarification_question"] == "井盖是缺失、破损还是松动？"
    assert cmd.update["question_source"] == "slot_schema"


def test_resolver_returns_empty_when_all_three_levels_are_gone():
    assert resolve_slot_question("x", "wrong", ["defect"], "", "") == ("", "none")


def test_level1_rejects_a_question_that_targets_a_slot_that_is_not_missing(monkeypatch):
    """B 类（impact）缺失不该被问 —— 自报槽位不在 A 类缺失里，就不采纳。"""
    monkeypatch.setattr(ag, "_slot_question_llm",
                        lambda **kw: {"question": "是否影响消防车通行？", "target_slot": "impact"})
    state = copy.deepcopy(MANHOLE_STATE)
    state["clarification_question"] = "兜底问句"
    cmd = ag.ask_slot_question(state)
    assert cmd.update["clarification_question"] == "兜底问句"
    assert cmd.update["question_source"] == "understand"


# ---------------------------------------------------------------- 4. 不该跑的轮次不跑

def test_no_model_call_when_missing_is_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: calls.append(kw) or {})
    cmd = ag.ask_slot_question({**copy.deepcopy(MANHOLE_STATE), "missing": [],
                                "next_action": "ask_critical_question"})
    assert calls == []
    assert cmd.update is None or not cmd.update


def test_no_model_call_when_the_action_does_not_ask(monkeypatch):
    calls = []
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: calls.append(kw) or {})
    ag.ask_slot_question({**copy.deepcopy(MANHOLE_STATE), "next_action": "answer_now"})
    assert calls == []


def test_no_model_call_under_a_danger_veto(monkeypatch):
    calls = []
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: calls.append(kw) or {})
    ag.ask_slot_question({**copy.deepcopy(MANHOLE_STATE), "danger_veto": True})
    assert calls == []


def test_a_plain_turn_makes_no_extra_model_call(monkeypatch):
    """整轮：不需要追问的回合，新节点一次都不调模型。"""
    calls = []
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: calls.append(kw) or {})
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(
        intent="quick_assessment", risk_level="medium", needs_search=False,
        issues=[{"major_code": "traffic", "subcategory_code": "manhole_damage",
                 "slots": {"defect": "缺失"}}],
        categories=["manhole_damage"],
        category_slots={"manhole_damage": {"defect": "缺失"}},
        question="", answer="这属于井盖缺失。",
    ))
    nodes, answer, _v = run_turn(ag.build_graph(),
                                 {"configurable": {"thread_id": "gap1-no-call"}},
                                 "楼下井盖缺失，这算隐患吗")
    assert calls == []
    assert "ask_slot_question" not in nodes
    assert answer.strip()


# ---------------------------------------------------------------- 5. route 接线

def test_route_diverts_to_the_new_node_only_when_asking(monkeypatch):
    assert ag.route(copy.deepcopy(MANHOLE_STATE)).goto == "ask_slot_question"
    assert ag.route({**copy.deepcopy(MANHOLE_STATE), "missing": [],
                    "dialogue_plan": {"ok": True}}).goto == "answer_reply"
    assert ag.route({"next_action": "answer_now"}).goto in (
        "answer_reply", "fallback_reply", "boundary_reply", "smalltalk_reply")


def test_the_node_lands_on_a_reply_node(monkeypatch):
    """原保证不丢：追问之后仍然落到某个回复节点，不会走丢。"""
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: {})
    cmd = ag.ask_slot_question(copy.deepcopy(MANHOLE_STATE))
    assert cmd.goto in ("answer_reply", "fallback_reply", "boundary_reply", "smalltalk_reply")


def test_graph_runs_the_node_and_asks_a_slot_question(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(
        intent="report_hazard", risk_level="high", needs_search=False,
        issues=[{"major_code": "traffic", "subcategory_code": "manhole_damage", "slots": {}}],
        categories=["manhole_damage"], category_slots={"manhole_damage": {}},
        question="", answer="",
    ))
    monkeypatch.setattr(ag, "_slot_question_llm",
                        lambda **kw: {"question": "井盖是没了还是只是松动？", "target_slot": "defect"})
    chunks = collect_chunks(monkeypatch)
    nodes, answer, values = run_turn(ag.build_graph(),
                                     {"configurable": {"thread_id": "gap1-graph"}},
                                     "楼下井盖有问题")
    assert "ask_slot_question" in nodes
    assert nodes.index("ask_slot_question") > nodes.index("route")
    assert "井盖是没了还是只是松动？" in answer
    assert values["question_source"] == "ask_slot_question"


def test_the_first_turn_can_now_ask_about_the_missing_decision_slot(monkeypatch):
    """缺口 1 的原始症状：第 1 轮该问 persistence(A)，以前问的是别的。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(
        intent="quick_assessment", risk_level="medium", needs_search=False,
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车"}}],
        categories=["fire_lane_blocked"],
        category_slots={"fire_lane_blocked": {"blocker": "私家车"}},
        question="这种占用是否影响了消防车通行？", answer="这属于消防通道占用。",
    ))
    seen = {}
    monkeypatch.setattr(ag, "_slot_question_llm",
                        lambda **kw: seen.update(kw) or {
                            "question": "这堆东西是长期放着的还是临时停一下？",
                            "target_slot": "persistence"})
    nodes, answer, values = run_turn(ag.build_graph(),
                                     {"configurable": {"thread_id": "gap1-first-turn"}},
                                     "我们小区消防通道长期被私家车占用")
    assert seen["missing"] == ["persistence"]          # 传的就是 A 类缺失
    assert seen["subcategory_code"] == "fire_lane_blocked"
    assert "长期放着的还是临时" in answer
    assert values["question_source"] == "ask_slot_question"


# ---------------------------------------------------------------- 6. 缺口 2：A 类为空则丢弃问句

def test_question_is_dropped_and_recorded_when_no_decision_slot_is_missing(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(
        intent="quick_assessment", risk_level="medium", needs_search=False,
        issues=[{"major_code": "road", "subcategory_code": "road_occupancy",
                 "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}}],
        categories=["road_occupancy"],
        category_slots={"road_occupancy": {"behavior": "摆摊", "persistence": "长期",
                                           "blocked": "完全堵死"}},
        question="需要我帮你创建一条整改任务吗？", answer="这属于占道经营。",
    ))
    out = ag.understand({"messages": [HumanMessage(content="路边长期有人摆摊，把路完全堵死，这算隐患吗")]})
    assert out["missing"] == []
    assert out["clarification_question"] == ""
    assert out["question_dropped"] == "no_decision_class_missing"


def test_drop_rule_is_logged_not_silent(monkeypatch, caplog):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(
        intent="quick_assessment", risk_level="medium", needs_search=False,
        issues=[{"major_code": "road", "subcategory_code": "road_occupancy",
                 "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}}],
        categories=["road_occupancy"],
        category_slots={"road_occupancy": {"behavior": "摆摊", "persistence": "长期",
                                           "blocked": "完全堵死"}},
        question="需要我帮你创建一条整改任务吗？", answer="这属于占道经营。",
    ))
    with caplog.at_level(logging.INFO, logger="core.assistant_graph"):
        ag.understand({"messages": [HumanMessage(content="路边长期有人摆摊，把路完全堵死，这算隐患吗")]})
    assert "no_decision_class_missing" in caplog.text


def test_question_is_kept_when_a_decision_slot_is_missing(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(
        intent="quick_assessment", risk_level="medium", needs_search=False,
        issues=[{"major_code": "traffic", "subcategory_code": "manhole_damage", "slots": {}}],
        categories=["manhole_damage"], category_slots={"manhole_damage": {}},
        question="井盖是缺失、破损还是松动？", answer="这属于井盖隐患。",
    ))
    out = ag.understand({"messages": [HumanMessage(content="楼下井盖有问题")]})
    assert out["missing"] == ["manhole_damage_defect"]
    assert out["clarification_question"] == "井盖是缺失、破损还是松动？"
    assert out["question_dropped"] == ""


def test_the_drop_rule_does_not_touch_the_in_major_enumeration_question(monkeypatch):
    """例外（有意）：连小类都定不下来时的枚举问句不受影响 —— 丢了会话会卡死。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(
        intent="report_hazard", risk_level="medium", needs_search=True,
        issues=[], categories=[], category_slots={},
        question="需要我帮你创建一条整改任务吗？", answer="",
    ))
    out = ag.understand({
        "messages": [HumanMessage(content="我们这栋楼有消防问题")],
        "locked_major": "fire", "locked_subcategory": "",
        "selected_major_code": "fire",
    })
    assert out["clarification_question"]
    assert "消防" in out["clarification_question"]

# ---------------------------------------------------------------- 7. 缺口 2 的三条防误伤

def test_address_phase_still_asks_when_the_turn_dropped_its_question(monkeypatch):
    """防误伤：位置问句走 task_gate 的 interrupt，与 clarification_question 无关。

    A 类缺失为空、问句被丢弃，也不能把"请提供具体地址"这条流程砍掉。
    """
    from typing import Annotated, TypedDict

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph

    from core.assistant_graph import task_gate
    from core.langgraph_state import append_messages

    class _GateState(TypedDict, total=False):
        messages: Annotated[list, append_messages]
        task_phase: str
        task_offered: bool
        address_text: str
        missing: list
        clarification_question: str
        question_dropped: str

    graph = StateGraph(_GateState)
    graph.add_node("task_gate", task_gate)
    graph.add_node("submit_task", lambda s: {"address_text": "sent"})
    graph.add_edge(START, "task_gate")
    graph.add_edge("submit_task", END)
    app = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "gap2-address"}}
    payload = None
    for _mode, item in app.stream(
            {"task_phase": "address", "missing": [],
             "clarification_question": "",
             "question_dropped": "no_decision_class_missing"},
            config, stream_mode=["updates"]):
        if isinstance(item, dict) and "__interrupt__" in item:
            payload = item["__interrupt__"][0].value
    assert payload is not None and payload["type"] == "ask_address"
    assert "地址" in payload["question"]


def test_task_gate_invitation_is_not_the_clarification_question(monkeypatch):
    """防误伤：建任务邀请由 task_gate 的 interrupt 给出，不受缺口 2 影响。

    这条同时证明"问句被丢弃"和"邀请照常发出"可以同时成立。
    """
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(
        issues=[{"major_code": "road", "subcategory_code": "road_occupancy",
                 "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}}],
        categories=["road_occupancy"],
        category_slots={"road_occupancy": {"behavior": "摆摊", "persistence": "长期",
                                           "blocked": "完全堵死"}},
        question="需要我帮你创建一条整改任务吗？",
    ))
    monkeypatch.setattr(ag, "_run_tool", lambda name, kw, cancellation=None: "[%s] %s" % (name, kw))
    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events",
                        lambda messages, cancellation=None: iter([("chunk", "报告正文")]))
    collect_chunks(monkeypatch)
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "gap2-gate"}}
    payload = None
    for mode, item in app.stream(
            {"session_id": "gap2-gate",
             "messages": [HumanMessage(content="路边长期摆摊，完全堵死")]},
            config, stream_mode=["updates", "custom"]):
        if mode == "updates" and isinstance(item, dict) and "__interrupt__" in item:
            payload = item["__interrupt__"][0].value
    assert payload is not None and payload["type"] == "confirm_create_task"
    assert "建一条隐患任务" in payload["question"]
    # 邀请不依赖 clarification_question：报告分支下它是空的，闸门照样发邀请。
    # （注意：报告路径的问句在 dialogue_policy 里就已经不返回了 —— 缺口 2 规则
    #  在这条路上不可达，它只作用于"答+可选追问"那条路。）
    values = app.get_state(config).values
    assert values["clarification_question"] == ""
    assert payload["question"] != values["clarification_question"]
