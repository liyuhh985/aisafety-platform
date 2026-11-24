# -*- coding: utf-8 -*-
"""Phase A: every active issue owns the follow-up and report gate."""

import core.assistant_graph as ag
from core.dialogue_policy import decide_next_action


def _multi_state(**overrides):
    state = {
        "messages": [],
        "locked_major": "fire",
        "locked_majors": ["fire", "building"],
        "locked_subcategory": "fire_lane_blocked",
        "issues": [
            {
                "major_code": "fire",
                "subcategory_code": "fire_lane_blocked",
                "slots": {"blocker": "私家车", "persistence": "长期"},
                "missing": [],
            },
            {
                "major_code": "building",
                "subcategory_code": "dangerous_building",
                "slots": {"occupancy": "有人居住"},
                "missing": ["structure"],
            },
        ],
        "categories": ["fire_lane_blocked", "dangerous_building"],
        "category_slots": {
            "fire_lane_blocked": {"blocker": "私家车", "persistence": "长期"},
            "dangerous_building": {"occupancy": "有人居住"},
        },
        "missing": ["dangerous_building_structure"],
        "next_action": "ask_critical_question",
    }
    state.update(overrides)
    return state


def test_non_focus_missing_a_slot_is_selected(monkeypatch):
    seen = {}

    def fake_question(**kwargs):
        seen.update(kwargs)
        return {
            "question": "房屋有没有裂缝、倾斜或沉降？",
            "target_slot": "structure",
        }

    monkeypatch.setattr(ag, "_slot_question_llm", fake_question)
    cmd = ag.ask_slot_question(_multi_state())

    assert seen["subcategory_code"] == "dangerous_building"
    assert seen["missing"] == ["structure"]
    assert "裂缝、倾斜或沉降" in cmd.update["clarification_question"]
    assert cmd.update["question_source"] == "ask_slot_question"


def test_two_issues_missing_a_slots_are_asked_in_one_parallel_question():
    state = _multi_state()
    state["issues"][0]["slots"] = {"blocker": "私家车"}
    state["issues"][0]["missing"] = ["persistence"]
    state["category_slots"]["fire_lane_blocked"] = {"blocker": "私家车"}
    state["missing"] = [
        "fire_lane_blocked_persistence",
        "dangerous_building_structure",
    ]

    cmd = ag.ask_slot_question(state)
    question = cmd.update["clarification_question"]

    assert "消防通道" in question
    assert "长期还是临时" in question
    assert "危房" in question
    assert "裂缝、倾斜或沉降" in question
    assert "请确认我理解得对不对" not in question
    assert question.count("还想确认") == 1


def test_focus_complete_non_focus_missing_is_not_sent_to_search():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [
            {"major_code": "fire", "subcategory_code": "fire_lane_blocked", "missing": []},
            {"major_code": "building", "subcategory_code": "dangerous_building", "missing": ["structure"]},
        ],
        "question": "房屋有没有裂缝、倾斜或沉降？",
        "answer": "",
        "needs_search": True,
    }
    out = decide_next_action(plan, {"user_text": "消防通道被占，旁边还有危房"})

    assert out["action"] == "ask_critical_question"
    assert out["needs_search"] is False
    assert out["question"] == "房屋有没有裂缝、倾斜或沉降？"
    assert "请确认" not in out["question"]
