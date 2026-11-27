# -*- coding: utf-8 -*-
"""多条隐患时的并列追问：每条取它自己最靠前的一个 A 类缺失，由代码拼成一句。

为什么让代码拼、不让模型写：多条的归属歧义比单条大得多，而槽位问句本来就写死在
slot_schemas 里 —— 交回代码更准，还省掉这一路上那次模型调用。
单条隐患一律走原路径（三级降级、target 审核），行为一个字不变。
"""
import copy

from langchain_core.messages import HumanMessage

import core.assistant_graph as ag

TWO_MUNICIPAL = {
    "messages": [HumanMessage(content="楼下井盖破了，旁边那根路灯杆也歪了")],
    "locked_major": "municipal",
    "locked_subcategory": "manhole_damage",
    "category_slots": {"manhole_damage": {}, "street_light_pole": {}},
    "missing": ["manhole_damage_defect", "street_light_pole_pole_status"],
    "issues": [
        {"major_code": "municipal", "subcategory_code": "manhole_damage",
         "slots": {}, "missing": ["defect"]},
        {"major_code": "municipal", "subcategory_code": "street_light_pole",
         "slots": {}, "missing": ["pole_status"]},
    ],
    "next_action": "ask_critical_question",
    "clarification_question": "模型自己写的问句？",
}

EXPECTED_TWO = (
    "还想确认两件事："
    "①『井盖缺失/破损』井盖是缺失、破损还是松动？"
    "②『路灯/线杆损坏』是灯杆倾斜折断，还是路灯不亮？"
)


def _no_model(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ag, "_slot_question_llm",
        lambda **kw: calls.append(kw) or {"question": "模型写的？", "target_slot": "defect"})
    return calls


def test_two_hazards_become_one_question_with_two_clauses(monkeypatch):
    calls = _no_model(monkeypatch)
    cmd = ag.ask_slot_question(copy.deepcopy(TWO_MUNICIPAL))
    assert cmd.update["clarification_question"] == EXPECTED_TWO
    assert cmd.update["question_source"] == "multi_hazard"
    assert cmd.update["asked_question_last_turn"] is True
    assert calls == [], "并列追问由代码拼，不该再调模型"


def test_the_node_still_only_writes_the_question(monkeypatch):
    """只读事实的不变式在多条路径上同样成立。"""
    _no_model(monkeypatch)
    state = copy.deepcopy(TWO_MUNICIPAL)
    keys = ("locked_major", "locked_subcategory", "issues", "category_slots", "missing")
    before = {k: copy.deepcopy(state[k]) for k in keys}
    cmd = ag.ask_slot_question(state)
    merged = {**state, **(cmd.update or {})}
    for key in keys:
        assert merged[key] == before[key], key


def test_a_hazard_that_needs_nothing_does_not_take_a_clause(monkeypatch):
    """只剩一条缺 A 类信息 → 退回原来的单条路径（模型仍然参与）。"""
    calls = _no_model(monkeypatch)
    state = copy.deepcopy(TWO_MUNICIPAL)
    state["missing"] = ["manhole_damage_defect"]
    state["issues"][1]["missing"] = []
    state["category_slots"]["street_light_pole"] = {"pole_status": "灯杆已经歪了"}
    cmd = ag.ask_slot_question(state)
    assert cmd.update["clarification_question"] == "模型写的？"
    assert cmd.update["question_source"] == "ask_slot_question"
    assert len(calls) == 1


def test_only_the_first_missing_slot_of_each_hazard_is_asked(monkeypatch):
    """每条只问一个槽：并列问点一多用户就答不动，剩下的留到下一轮。"""
    _no_model(monkeypatch)
    state = {
        "messages": [HumanMessage(content="消防通道被杂物堵了，旁边消火栓也坏了")],
        "locked_major": "fire",
        "locked_subcategory": "fire_lane_blocked",
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物"},
                           "fire_equipment_fault": {}},
        "missing": ["fire_lane_blocked_persistence",
                    "fire_equipment_fault_facility_type",
                    "fire_equipment_fault_condition"],
        "issues": [
            {"major_code": "fire", "subcategory_code": "fire_lane_blocked",
             "slots": {"blocker": "杂物"}, "missing": ["persistence"]},
            {"major_code": "fire", "subcategory_code": "fire_equipment_fault",
             "slots": {}, "missing": ["facility_type", "condition"]},
        ],
        "next_action": "ask_critical_question",
        "clarification_question": "",
    }
    question = ag.ask_slot_question(state).update["clarification_question"]
    assert "①『消防通道占用』是长期还是临时？" in question
    assert "②『消防设施故障』具体是哪一类消防设施" in question
    assert "老旧、损坏还是完全无法使用" not in question, "第二条缺失不该挤进来"


def test_three_hazards_use_three_clause_numbers(monkeypatch):
    _no_model(monkeypatch)
    codes = ["dangerous_building", "falling_object", "illegal_structure"]
    state = {
        "messages": [HumanMessage(content="危房、高空坠物、违规搭建")],
        "locked_major": "building",
        "locked_subcategory": codes[0],
        "category_slots": {code: {} for code in codes},
        "missing": [
            "structure" if code == "dangerous_building"
            else "source" if code == "falling_object"
            else "structure_detail"
            for code in codes
        ],
        "issues": [
            {"major_code": "building", "subcategory_code": "dangerous_building",
             "slots": {}, "missing": ["structure"]},
            {"major_code": "building", "subcategory_code": "falling_object",
             "slots": {}, "missing": ["source"]},
            {"major_code": "building", "subcategory_code": "illegal_structure",
             "slots": {}, "missing": ["structure_detail"]},
        ],
        "next_action": "ask_critical_question",
        "clarification_question": "",
    }
    question = ag.ask_slot_question(state).update["clarification_question"]
    assert question.startswith("还想确认三件事：")
    assert question.count("①") == 1 and question.count("②") == 1 and question.count("③") == 1
    assert "①『危房』" in question
    assert "③『违规搭建』" in question


def test_the_question_is_still_asked_when_the_focus_needs_nothing(monkeypatch):
    """焦点那条已经齐、缺的是别的条 —— 并列追问照样要发出。

    这条曾会被"焦点没有缺失就直接返回"挡住（开关放在缺失判断之后）。
    """
    _no_model(monkeypatch)
    state = {
        "messages": [HumanMessage(content="井盖、路灯杆、路面都有问题")],
        "locked_major": "municipal",
        "locked_subcategory": "manhole_damage",
        "category_slots": {"manhole_damage": {"defect": "整个盖子都没了"},
                           "street_light_pole": {}, "road_surface_collapse": {}},
        "missing": ["street_light_pole_pole_status", "road_surface_collapse_collapse_scale"],
        "issues": [
            {"major_code": "municipal", "subcategory_code": "manhole_damage",
             "slots": {"defect": "整个盖子都没了"}, "missing": []},
            {"major_code": "municipal", "subcategory_code": "street_light_pole",
             "slots": {}, "missing": ["pole_status"]},
            {"major_code": "municipal", "subcategory_code": "road_surface_collapse",
             "slots": {}, "missing": ["collapse_scale"]},
        ],
        "next_action": "ask_critical_question",
        "clarification_question": "",
    }
    cmd = ag.ask_slot_question(state)
    assert cmd.update["question_source"] == "multi_hazard"
    question = cmd.update["clarification_question"]
    assert "路灯/线杆损坏" in question and "路面塌陷" in question
    assert "井盖缺失/破损" not in question      # 已经齐的那条不占问句名额


def test_a_single_hazard_still_goes_through_the_model(monkeypatch):
    """单条隐患是主路径：一个字都不变，仍然走模型 + 三级降级。"""
    calls = _no_model(monkeypatch)
    state = {
        "messages": [HumanMessage(content="楼下井盖破了")],
        "locked_major": "municipal",
        "locked_subcategory": "manhole_damage",
        "category_slots": {"manhole_damage": {}},
        "missing": ["manhole_damage_defect"],
        "issues": [{"major_code": "municipal", "subcategory_code": "manhole_damage",
                    "slots": {}, "missing": ["defect"]}],
        "next_action": "ask_critical_question",
        "clarification_question": "",
    }
    cmd = ag.ask_slot_question(state)
    assert cmd.update["clarification_question"] == "模型写的？"
    assert cmd.update["question_source"] == "ask_slot_question"
    assert len(calls) == 1
