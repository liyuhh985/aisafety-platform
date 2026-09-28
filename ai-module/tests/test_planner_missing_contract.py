# -*- coding: utf-8 -*-
"""阶段 2：missing 喂规划器（提示词契约）+ question_missing 校验不静默。"""
import logging

from langchain_core.messages import HumanMessage

import core.assistant_graph as ag
from core.dialogue_understanding import build_planner_messages, parse_plan


def _prompt_text(**kwargs):
    return "\n".join(m["content"] for m in build_planner_messages([], **kwargs))


def _plan(**over):
    base = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [], "categories": [], "category_slots": {},
        "question": "", "answer": "", "needs_search": True,
    }
    base.update(over)
    return base


# ---------- 提示词契约 ----------

def test_prompt_carries_the_actual_missing_values():
    """断言的是真正拼进请求的文本，不是变量名。"""
    text = _prompt_text(
        missing=["persistence"],
        known_slots={"blocker": "私家车"},
        subcategory_code="fire_lane_blocked",
    )
    assert "仍缺的决策级信息" in text
    assert "persistence" in text                       # missing 的值本身
    assert "私家车" in text                             # 已知事实的值本身
    assert "消防通道占用" in text                        # 焦点隐患
    assert "question 必须针对" in text                   # 契约句


def test_prompt_states_the_contract_even_when_nothing_is_missing():
    text = _prompt_text(subcategory_code="manhole_damage", known_slots={"defect": "缺失"})
    assert "仍缺的决策级信息：（无）" in text
    assert "question 留空" in text


def test_prompt_has_no_focus_block_without_a_locked_subcategory():
    text = _prompt_text()
    assert "槽位状态" not in text
    assert "仍缺的决策级信息" not in text


def test_prompt_tells_the_model_not_to_copy_the_hint_verbatim():
    text = _prompt_text(missing=["blocker"], subcategory_code="fire_lane_blocked")
    assert "不要照抄" in text


def test_parse_plan_issues_carry_report_missing():
    raw = (
        '{"intent":"report_hazard","issues":[{"major_code":"fire",'
        '"subcategory_code":"fire_lane_blocked","slots":{"blocker":"杂物"}}]}'
    )
    issue = parse_plan(raw)["issues"][0]
    assert issue["missing"] == ["persistence"]
    assert issue["report_missing"] == ["persistence", "impact"]


# ---------- 图节点接线 ----------

def test_understand_node_feeds_missing_to_the_planner(monkeypatch):
    seen = {}

    def fake_plan(messages, vision, selected_major_code="", **kwargs):
        seen.update(kwargs)
        return _plan()

    monkeypatch.setattr(ag, "_understand_plan", fake_plan)
    ag.understand({
        "messages": [HumanMessage(content="还是没人来处理")],
        "locked_major": "fire",
        "locked_subcategory": "fire_lane_blocked",
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物"}},
    })
    assert seen["missing"] == ["persistence"]
    assert seen["known_slots"] == {"blocker": "杂物"}
    assert seen["subcategory_code"] == "fire_lane_blocked"


def test_understand_node_omits_context_without_a_locked_subcategory(monkeypatch):
    """兼容约定：没有锁定小类时不传新参数 —— 老的三参签名调用方仍然可用。"""
    called = []

    def strict_plan(messages, vision, selected_major_code=""):
        called.append(True)
        return _plan()

    monkeypatch.setattr(ag, "_understand_plan", strict_plan)
    ag.understand({"messages": [HumanMessage(content="楼下消防通道被占了")]})
    assert called == [True]


# ---------- question_missing 校验 ----------

def test_question_missing_is_recorded_when_the_planner_asks_nothing(monkeypatch):
    plan = _plan(
        intent="quick_assessment", risk_level="medium", needs_search=False,
        issues=[{"major_code": "traffic", "subcategory_code": "manhole_damage",
                 "slots": {}}],
        categories=["manhole_damage"], category_slots={"manhole_damage": {}},
        answer="我先按井盖隐患理解。",
    )
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [HumanMessage(content="楼下井盖有问题")]})
    assert out["missing"] == ["manhole_damage_defect"]
    assert out["question_missing"] == ["manhole_damage_defect"]
    assert out["question_missing_reason"] == "planner_no_question"


def test_question_missing_is_logged_loudly(caplog, monkeypatch):
    plan = _plan(
        intent="quick_assessment", risk_level="medium", needs_search=False,
        issues=[{"major_code": "traffic", "subcategory_code": "manhole_damage",
                 "slots": {}}],
        categories=["manhole_damage"], category_slots={"manhole_damage": {}},
        answer="我先按井盖隐患理解。",
    )
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        ag.understand({"messages": [HumanMessage(content="楼下井盖有问题")]})
    assert "question_missing" in caplog.text
    assert "planner_no_question" in caplog.text


def test_question_missing_reason_is_report_when_a_report_was_requested(monkeypatch):
    plan = _plan(
        issues=[{"major_code": "traffic", "subcategory_code": "manhole_damage",
                 "slots": {}}],
        categories=["manhole_damage"], category_slots={"manhole_damage": {}},
    )
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [HumanMessage(content="井盖有问题，帮我查法规")]})
    assert out["next_action"] == "report_preliminary"
    assert out["question_missing"] == ["manhole_damage_defect"]
    assert out["question_missing_reason"] == "report"


def test_question_missing_reason_is_danger_veto_on_the_danger_path(monkeypatch):
    plan = _plan(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {}}],
        categories=["fire_lane_blocked"], category_slots={"fire_lane_blocked": {}},
    )
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]})
    assert out["danger_veto"] is True
    assert out["question_missing"] == ["fire_lane_blocked_blocker", "fire_lane_blocked_persistence"]
    assert out["question_missing_reason"] == "danger_veto"
    assert out["clarification_question"] == ""


def test_question_missing_is_empty_when_a_question_was_asked(monkeypatch):
    plan = _plan(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车"}}],
        categories=["fire_lane_blocked"],
        category_slots={"fire_lane_blocked": {"blocker": "私家车"}},
        question="这种情况持续多久了？",
    )
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [HumanMessage(content="消防通道被私家车占了")]})
    assert out["clarification_question"] == "这种情况持续多久了？"
    assert out["question_missing"] == []
    assert out["question_missing_reason"] == ""
