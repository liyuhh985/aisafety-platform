"""回声填充：把隐患名称复述进槽位，不算答过 → 按"缺"处理，应该重新问。"""
import core.assistant_graph as ag
from core.uncertainty import echo_slots, is_echo_slot


def test_echo_slot_is_detected():
    assert is_echo_slot("危房", "dangerous_building") is True
    assert is_echo_slot("消防通道", "fire_lane_blocked") is True
    assert is_echo_slot("消防设施", "fire_equipment_fault") is True


def test_real_answers_are_not_treated_as_echo():
    assert is_echo_slot("杂物", "fire_lane_blocked") is False
    assert is_echo_slot("消火栓", "fire_equipment_fault") is False
    assert is_echo_slot("长期", "fire_lane_blocked") is False
    assert is_echo_slot("完全堵死", "fire_lane_blocked") is False


def test_too_short_values_are_not_echo():
    assert is_echo_slot("占", "road_occupancy") is False


def test_option_words_are_not_echoes():
    """选项词大多是两个字，而它们往往正好是事件名字的一部分 —— 不能因此判成复述。

    实测：用户答「楼下井盖是缺失的」→ defect="缺失" 被判复述丢掉 → 同一道题再问一遍。
    """
    assert is_echo_slot("缺失", "manhole_damage") is False
    assert is_echo_slot("破损", "manhole_damage") is False
    assert is_echo_slot("松动", "manhole_damage") is False
    assert is_echo_slot("裂缝", "dangerous_building") is False


def test_longer_names_are_still_echoes():
    """长度下限只放行两个字；四个字的隐患名照旧判成复述（既有行为不变）。"""
    assert is_echo_slot("消防通道", "fire_lane_blocked") is True
    assert is_echo_slot("消防设施", "fire_equipment_fault") is True
    assert is_echo_slot("危房", "dangerous_building") is True


def test_echo_slots_groups_by_issue():
    issues = [
        {"subcategory_code": "dangerous_building",
         "slots": {"structure": "危房", "occupancy": "有人居住"}},
        {"subcategory_code": "fire_lane_blocked", "slots": {"blocker": "杂物"}},
    ]
    assert echo_slots(issues) == {"dangerous_building": ["structure=危房"]}


def test_understand_treats_an_echo_slot_as_missing_and_asks(monkeypatch):
    """用户只说"旁边还有一栋危房"，模型把"危房"填进 structure：
    这不算答过，系统应当问那一句，而不是把它当完整隐患出三段式。"""
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "building", "subcategory_code": "dangerous_building",
                    "slots": {"structure": "危房", "occupancy": "危房", "risk": "危房"},
                    "evidence": [{"slot": "structure", "quote": "危房", "source_ref": "u1"}]}],
        "categories": ["dangerous_building"],
        "category_slots": {"dangerous_building": {
            "structure": "危房", "occupancy": "危房", "risk": "危房"}},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [ag.HumanMessage(content="旁边还有一栋危房")]})

    assert out["issues"][0]["slots"] == {}
    assert out["issues"][0]["evidence"] == []
    assert "dangerous_building_structure" in out["missing"]
    assert out["next_action"] == "ask_critical_question"
    assert out["clarification_question"]
    assert any("echo_slot" in sig for sig in out["uncertainty_signals"])


def test_understand_keeps_genuine_slots(monkeypatch):
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "building", "subcategory_code": "dangerous_building",
                    "slots": {"structure": "有裂缝且已倾斜", "occupancy": "有人居住",
                              "risk": "随时可能坍塌"}}],
        "categories": ["dangerous_building"],
        "category_slots": {"dangerous_building": {
            "structure": "有裂缝且已倾斜", "occupancy": "有人居住", "risk": "随时可能坍塌"}},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [ag.HumanMessage(
        content="旁边那栋危房有裂缝还倾斜了，里面有人住，随时可能塌")]})
    assert out["missing"] == []
    assert out["issues"][0]["slots"]["structure"] == "有裂缝且已倾斜"
    assert not any("echo_slot" in sig for sig in out["uncertainty_signals"])
