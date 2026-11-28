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
            "question": "房屋有没有墙体开裂、整体倾斜、地基沉降或承重构件变形？",
            "target_slot": "structure",
        }

    monkeypatch.setattr(ag, "_slot_question_llm", fake_question)
    cmd = ag.ask_slot_question(_multi_state())

    assert seen["subcategory_code"] == "dangerous_building"
    assert seen["missing"] == ["structure"]
    assert "墙体开裂、整体倾斜、地基沉降" in cmd.update["clarification_question"]
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
    assert "墙体开裂、整体倾斜、地基沉降" in question
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
        "question": "房屋有没有墙体开裂、整体倾斜、地基沉降或承重构件变形？",
        "answer": "",
        "needs_search": True,
    }
    out = decide_next_action(plan, {"user_text": "消防通道被占，旁边还有危房"})

    assert out["action"] == "ask_critical_question"
    assert out["needs_search"] is False
    assert out["question"] == "房屋有没有墙体开裂、整体倾斜、地基沉降或承重构件变形？"
    assert "请确认" not in out["question"]


def test_understand_stop_phrase_with_missing_slot_stays_out_of_search(monkeypatch):
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [{
            "major_code": "traffic",
            "subcategory_code": "road_occupancy",
            "slots": {"behavior": "摆摊", "blocked": "部分占用"},
        }],
        "categories": ["road_occupancy"],
        "category_slots": {"road_occupancy": {"behavior": "摆摊", "blocked": "部分占用"}},
        "question": "是长期占压还是临时停放？",
        "answer": "先按占道经营类隐患作初步判断。",
        "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: plan)
    out = ag.understand({
        "messages": [ag.HumanMessage(content="别问了，直接出报告")],
    })
    assert out["missing"] == ["road_occupancy_persistence"]
    assert out["next_action"] == "answer_now"
    assert out["report_mode"] == "none"
    assert out["asked_question_last_turn"] is False
    assert ag.route(out).goto in {"answer_reply", "fallback_reply"}
