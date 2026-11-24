# -*- coding: utf-8 -*-
"""阶段 2：槽位 A/B 两类划分的行为与不变量。"""
import pytest
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag
from core.hazard_taxonomy import ALL_SUBCATEGORY_CODES
from core.slot_schemas import (
    DECISION_CLASS,
    REPORT_CLASS,
    Slot,
    get_slot_schema,
    missing_decision_slots,
    missing_report_slots,
)


def _plan(**over):
    base = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [], "categories": [], "category_slots": {},
        "question": "", "answer": "", "needs_search": True,
    }
    base.update(over)
    return base


def _issue(major, sub, slots):
    return {"major_code": major, "subcategory_code": sub, "slots": slots}


# ---------- 结构 ----------

def test_every_slot_in_every_subcategory_has_a_valid_class():
    seen = 0
    for code in ALL_SUBCATEGORY_CODES:
        for slot in get_slot_schema(code):
            assert slot.value_class in {"A", "B"}, (code, slot.key)
            seen += 1
    assert seen > 0


def test_value_class_distribution_snapshot():
    """钉住当前划分：任何槽位的类别改动都会让这条变红，必须是有意的。"""
    counts = {}
    max_a = 0
    for code in ALL_SUBCATEGORY_CODES:
        a = len([s for s in get_slot_schema(code) if s.value_class == DECISION_CLASS])
        counts[a] = counts.get(a, 0) + 1
        max_a = max(max_a, a)
    # 重划前是 14x1 / 9x2 / 9x3（追问上界 3）；现在 A 类最多 2 → 追问上界 2
    assert counts == {1: 21, 2: 11}
    assert max_a == 2


def test_critical_is_derived_from_the_decision_class():
    """兼容层：A 类 == 旧的 critical=True，必须逐槽一致。"""
    for code in ALL_SUBCATEGORY_CODES:
        for slot in get_slot_schema(code):
            assert slot.critical is (slot.value_class == DECISION_CLASS), (code, slot.key)


def test_only_a_and_b_value_classes_exist():
    from core.slot_schemas import VALUE_CLASSES
    assert VALUE_CLASSES == ("A", "B")


def test_decorative_c_slots_are_removed():
    dangerous = {slot.key for slot in get_slot_schema("dangerous_building")}
    electrical = {slot.key for slot in get_slot_schema("exposed_wire")}
    assert "risk" not in dangerous
    assert "risk" not in electrical


def test_unknown_value_class_is_rejected_loudly():
    with pytest.raises(ValueError):
        Slot("x", "问句", "C")


# ---------- 选择器语义 ----------

def test_decision_selector_returns_only_a_class_in_schema_order():
    slots = missing_decision_slots("fire_lane_blocked", {})
    assert [s.key for s in slots] == ["blocker", "persistence"]
    assert all(s.value_class == "A" for s in slots)


def test_report_selector_includes_b_class_but_decision_selector_does_not():
    decision = [s.key for s in missing_decision_slots("fire_lane_blocked", {})]
    report = [s.key for s in missing_report_slots("fire_lane_blocked", {})]
    assert "impact" not in decision            # B 类不追问
    assert report == ["blocker", "persistence", "impact"]   # 但进报告材料


def test_filled_slots_are_never_selected():
    filled = {"blocker": "杂物", "persistence": ""}
    assert [s.key for s in missing_decision_slots("fire_lane_blocked", filled)] == ["persistence"]


# ---------- rebuild_missing 两个口径 ----------

def test_rebuild_missing_is_decision_only():
    miss = ag.rebuild_missing(["fire_lane_blocked"], {"fire_lane_blocked": {}})
    assert miss == ["fire_lane_blocked_blocker", "fire_lane_blocked_persistence"]


def test_rebuild_report_missing_adds_the_b_class():
    cats = ["fire_lane_blocked"]
    slots = {"fire_lane_blocked": {}}
    report = ag.rebuild_report_missing(cats, slots)
    assert report == [
        "fire_lane_blocked_blocker",
        "fire_lane_blocked_persistence",
        "fire_lane_blocked_impact",
    ]


# ---------- 端到端：B 类缺失不触发追问 ----------

def test_b_class_missing_never_triggers_a_followup(monkeypatch):
    """消防通道的 blocker/persistence 已答，只缺 impact(B)：
    不应再追问，但报告材料里要留着 impact。"""
    plan = _plan(
        issues=[_issue("fire", "fire_lane_blocked",
                       {"blocker": "私家车", "persistence": "长期"})],
        categories=["fire_lane_blocked"],
        category_slots={"fire_lane_blocked": {"blocker": "私家车", "persistence": "长期"}},
    )
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [HumanMessage(content="消防通道停车，长期停")]})
    assert out["missing"] == []
    assert out["issues"][0]["missing"] == []
    assert out["issues"][0]["report_missing"] == ["impact"]
    assert out["next_action"] != "ask_critical_question"
    assert out["question_missing"] == []


def test_a_class_missing_still_triggers_a_followup(monkeypatch):
    plan = _plan(
        issues=[_issue("fire", "fire_lane_blocked", {"blocker": "私家车"})],
        categories=["fire_lane_blocked"],
        category_slots={"fire_lane_blocked": {"blocker": "私家车"}},
    )
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [HumanMessage(content="消防通道被私家车占了")]})
    assert out["missing"] == ["fire_lane_blocked_persistence"]
    assert out["issues"][0]["report_missing"] == ["persistence", "impact"]
    assert out["next_action"] in {"ask_critical_question", "answer_with_optional_question"}


def test_report_missing_field_is_always_present(monkeypatch):
    plan = _plan(
        issues=[_issue("building", "dangerous_building", {"structure": "有裂缝"})],
        categories=["dangerous_building"],
        category_slots={"dangerous_building": {"structure": "有裂缝"}},
    )
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [HumanMessage(content="楼上有裂缝")]})
    assert out["issues"][0]["report_missing"] == ["occupancy"]
    assert out["issues"][0]["missing"] == ["occupancy"]
