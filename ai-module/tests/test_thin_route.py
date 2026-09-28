"""C4a: understand is the only writer of facts + policy; route is a pure mapping."""
import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Command

import core.assistant_graph as ag
from core.assistant_graph import route


def _plan(**overrides):
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "categories": ["fire/fire_equipment_fault"],
        "category_slots": {"fire/fire_equipment_fault": {}},
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "slots": {},
            "missing": [],
        }],
        "question": "",
        "answer": "",
        "needs_search": True,
        "selected_major_code": "fire",
        "major_mismatch": False,
    }
    plan.update(overrides)
    return plan


def test_route_sends_report_actions_to_search():
    assert route({"next_action": "report_full"}).goto == "search"
    assert route({"next_action": "report_preliminary"}).goto == "search"


def test_route_sends_answer_actions_to_direct_reply():
    for action in ("answer_now", "answer_with_optional_question",
                   "ask_critical_question", ""):
        assert route({"next_action": action}).goto in (
            "boundary_reply", "smalltalk_reply", "answer_reply", "fallback_reply")


def test_route_returns_a_command_not_a_dict():
    assert isinstance(route({"next_action": "report_full"}), Command)


def test_route_never_routes_to_a_clarify_branch():
    for action in ("answer_now", "ask_critical_question", "report_full"):
        assert route({"next_action": action}).goto not in {"clarify", "meta_clarify"}


def test_understand_recomputes_missing_and_overrides_the_planner(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    out = ag.understand({"messages": [HumanMessage(content="楼下消火栓坏了")]})
    # 规划器声称 missing 为空，但 critical 槽未填 → 确定性重算必须纠正它
    assert out["missing"] == [
        "fire_equipment_fault_facility_type",
        "fire_equipment_fault_condition",
    ]
    assert out["issues"][0]["missing"] == ["facility_type", "condition"]
    assert out["categories"] == ["fire_equipment_fault"]


def test_understand_carries_persisted_slots_forward(monkeypatch):
    monkeypatch.setattr(
        ag, "_understand_plan",
        lambda *a, **k: _plan(issues=[{
            "major_code": "fire", "subcategory_code": "fire_equipment_fault",
            "slots": {"condition": "损坏"}, "missing": [],
        }]),
    )
    out = ag.understand({
        "messages": [HumanMessage(content="已经到了完全不能用的程度")],
        "category_slots": {"fire_equipment_fault": {"facility_type": "消火栓"}},
    })
    assert out["category_slots"]["fire_equipment_fault"] == {
        "facility_type": "消火栓", "condition": "损坏",
    }
    assert out["missing"] == []


def test_understand_decides_the_next_action_instead_of_route(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    out = ag.understand({"messages": [HumanMessage(content="楼下消火栓坏了")]})
    assert out["next_action"] in {"answer_now", "ask_critical_question",
                                  "answer_with_optional_question"}
    # direct_mode 只用于范围/社交特殊模式；正常隐患回合必须留空，否则 scope_guard 会被跳过
    assert not out["direct_mode"]


def test_understand_falls_back_cleanly_when_the_planner_fails(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: {})
    out = ag.understand({"messages": [HumanMessage(content="随便说点什么")]})
    assert out["next_action"] == "answer_now"
    assert out["issues"] == []
    assert out["dialogue_plan"] == {}


def test_understand_clears_stale_direct_mode(monkeypatch):
    """上一轮是问候，本轮是隐患：不能把 smalltalk 残留下来。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    out = ag.understand({
        "messages": [HumanMessage(content="楼下消火栓坏了")],
        "direct_mode": "smalltalk",
    })
    assert out["direct_mode"] == ""


def test_scope_guard_still_runs_on_a_normal_hazard_turn(monkeypatch):
    """回归：understand 不再设 direct_mode，护栏必须仍然生效并决定 scope。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan())
    understood = ag.understand({"messages": [HumanMessage(content="楼下消火栓坏了")]})
    update = ag.scope_guard({
        **understood,
        "messages": [HumanMessage(content="楼下消火栓坏了")],
        "session_id": "s1",
    })
    assert update["scope"] == "hazard"


def test_scope_guard_pins_next_action_for_out_of_scope(monkeypatch):
    no_hazard = {
        "ok": True, "intent": "other", "issues": [], "categories": [],
        "category_slots": {}, "question": "", "answer": "", "needs_search": False,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(no_hazard))
    understood = ag.understand({"messages": [HumanMessage(content="帮我写一首诗")]})
    update = ag.scope_guard({
        **understood,
        "messages": [HumanMessage(content="帮我写一首诗")],
        "session_id": "s2",
    })
    assert update["scope"] == "out_of_scope"
    assert update["next_action"] == "answer_now"
    assert update["report_mode"] == "none"
