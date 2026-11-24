from tests.reply_helpers import render_reply, render_update
import json
import core.assistant_graph as assistant_graph
import pytest
from core import dialogue_understanding
from core.dialogue_policy import decide_next_action


def test_high_risk_missing_critical_asks_one_question():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": ["facility_type"],
        }],
        "question": "具体是哪一类消防设施？",
        "answer": "我先理解为消防设施故障。",
    }
    out = decide_next_action(plan, {"user_text": "消防设施有问题"})
    assert out["action"] == "ask_critical_question"
    assert out["question"] == "具体是哪一类消防设施？"
    assert out["needs_search"] is False


def test_low_risk_missing_noncritical_answers_with_optional_question():
    plan = {
        "ok": True,
        "intent": "quick_assessment",
        "risk_level": "low",
        "issues": [{
            "major_code": "environment_other",
            "subcategory_code": "garbage_pile",
            "missing": [],
        }],
        "question": "如果方便，可以补充垃圾堆积范围。",
        "answer": "这通常属于需要清理的安全隐患。",
    }
    out = decide_next_action(plan, {"user_text": "垃圾堆着"})
    assert out["action"] in {"answer_with_optional_question", "answer_now"}
    assert out["needs_search"] is False


def test_explicit_stop_questioning_skips_clarification():
    plan = {
        "ok": True,
        "intent": "ask_solution",
        "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": ["facility_type"],
        }],
        "question": "具体是哪一类消防设施？",
        "answer": "可以先按消防设施失效处理。",
    }
    out = decide_next_action(plan, {"user_text": "别问了，直接说怎么办"})
    assert out["action"] in {"answer_now", "report_preliminary"}
    assert out["question"] == ""


def test_complete_report_uses_full_mode():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": [],
        }],
        "answer": "已确认消防设施失效。",
    }
    out = decide_next_action(plan, {"user_text": "消防栓没水，灭火器过期"})
    assert out["action"] == "report_full"
    assert out["needs_search"] is True
    assert out["report_mode"] == "full"


def test_incomplete_explicit_report_still_asks_critical_question():
    plan = {
        "ok": True,
        "intent": "ask_regulation",
        "risk_level": "high",
        "issues": [{
            "major_code": "building",
            "subcategory_code": "dangerous_building",
            "missing": ["structure"],
        }],
        "question": "",
        "answer": "",
    }
    out = decide_next_action(plan, {"user_text": "帮我查危房法规"})
    assert out["action"] == "ask_critical_question"
    assert out["needs_search"] is False
    assert out["report_mode"] == "none"
    assert "裂缝、倾斜或沉降" in out["question"]


def test_complete_issue_waits_when_another_issue_is_missing():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [
            {"major_code": "fire", "subcategory_code": "fire_equipment_fault", "missing": []},
            {"major_code": "building", "subcategory_code": "dangerous_building", "missing": ["structure"]},
        ],
        "answer": "已记录两个问题。",
    }
    out = decide_next_action(plan, {"user_text": "消防设施坏了，旁边还有危房"})
    assert out["action"] == "ask_critical_question"
    assert out["needs_search"] is False
    assert out["report_mode"] == "none"


def test_answering_previous_question_with_complete_facts_reports_full():
    plan = {
        "ok": True,
        "intent": "quick_assessment",
        "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": [],
        }],
        "answer": "已确认消防设施失效。",
        "question": "",
    }
    state = {
        "messages": [
            assistant_graph.AIMessage(content="具体是哪一类消防设施？"),
            assistant_graph.HumanMessage(content="消防栓和灭火器都有"),
        ],
        "user_text": "消防栓和灭火器都有",
    }
    out = decide_next_action(plan, state)
    assert out["action"] == "report_full"
    assert out["needs_search"] is True


def test_plan_parser_reads_risk_level():
    raw = (
        '{"intent":"report_hazard","risk_level":"high","issues":[{"major_code":"fire",'
        '"subcategory_code":"fire_equipment_fault","slots":{},"confidence":0.9}],'
        '"question":"","answer":"","needs_search":false,"relationship_hint":""}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["risk_level"] == "high"


def test_plan_parser_defaults_invalid_risk_level_to_medium():
    raw = (
        '{"intent":"other","risk_level":"unknown","categories":[],"category_slots":{},'
        '"question":"","answer":"","needs_search":false,"relationship_hint":""}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["risk_level"] == "medium"


def test_preliminary_report_does_not_offer_task_creation(monkeypatch):
    chunks = []
    captured = {}
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)

    def fake_stream(messages, cancellation=None):
        captured["prompt"] = messages
        yield ("chunk", "初步判断")

    monkeypatch.setattr(assistant_graph._report_llm, "_call_llm_stream_events", fake_stream)
    update = assistant_graph.report({
        "messages": [], "categories": ["fire_equipment_fault"],
        "category_results": {"fire_equipment_fault": {"regulation": "法", "case": "案例"}},
        "missing": ["facility_type"], "issues": [{"subcategory_code": "fire_equipment_fault"}],
        "report_mode": "preliminary",
    })
    assert "初步判断" in update["draft_report"]
    assert "建一条隐患任务" not in update["draft_report"]


def test_full_report_offers_task_creation_when_complete(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(
        assistant_graph._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation: iter([("chunk", "完整报告")]),
    )
    update = assistant_graph.report({
        "messages": [], "categories": ["fire_equipment_fault"],
        "category_results": {"fire_equipment_fault": {"regulation": "法", "case": "案例"}},
        "missing": [], "issues": [{"subcategory_code": "fire_equipment_fault"}],
        "report_mode": "full",
    })
    # 邀请不再由报告正文拼装，而是交给 task_gate 的 interrupt
    assert update["offer_task"] is True
    assert "建一条隐患任务" not in update["draft_report"]


def test_negative_confirmation_is_not_a_creation_confirmation():
    assert assistant_graph.classify_task_reply("不需要") == "decline"
    assert assistant_graph.classify_task_reply("不用了") == "decline"
    assert assistant_graph.classify_task_reply("需要") == "confirm"


def test_legacy_report_mode_none_still_offers_task_when_complete(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(
        assistant_graph._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation: iter([("chunk", "报告")]),
    )
    update = assistant_graph.report({
        "messages": [], "categories": ["fire_equipment_fault"],
        "category_results": {"fire_equipment_fault": {"regulation": "法", "case": "案例"}},
        "missing": [], "report_mode": "none",
    })
    assert update["offer_task"] is True


def test_explicit_create_task_intent_reaches_full_report():
    plan = {
        "ok": True,
        "intent": "create_task",
        "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": [],
        }],
        "answer": "信息已完整。",
        "question": "",
    }
    out = decide_next_action(plan, {"user_text": "帮我建个任务"})
    assert out["action"] == "report_full"
    assert out["report_mode"] == "full"


def test_previous_report_offer_does_not_count_as_clarification():
    plan = {
        "ok": True,
        "intent": "quick_assessment",
        "risk_level": "medium",
        "issues": [{
            "major_code": "traffic",
            "subcategory_code": "vehicle_occupancy",
            "missing": [],
        }],
        "answer": "这属于占道问题。",
        "question": "如果方便，补充持续时长。",
    }
    state = {
        "messages": [
            assistant_graph.AIMessage(content="报告内容。\n\n需要我帮你在系统建一条隐患任务吗？"),
            assistant_graph.HumanMessage(content="盲道被车占了，算安全隐患吗？"),
        ],
        "user_text": "盲道被车占了，算安全隐患吗？",
    }
    out = decide_next_action(plan, state)
    assert out["action"] in {"answer_now", "answer_with_optional_question"}
    assert out["needs_search"] is False


def test_quick_assessment_without_answer_never_falls_into_report():
    plan = {
        "ok": True,
        "intent": "quick_assessment",
        "risk_level": "medium",
        "issues": [{
            "major_code": "traffic",
            "subcategory_code": "vehicle_occupancy",
            "missing": [],
        }],
        "answer": "",
        "question": "是否能补充一下现场情况？",
    }
    out = decide_next_action(plan, {"user_text": "盲道被车占了，算安全隐患吗？"})
    assert out["needs_search"] is False
    assert out["report_mode"] == "none"


def test_colloquial_directly_is_not_stop_phrase():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": ["facility_type"],
        }],
        "question": "具体是哪一类消防设施？",
        "answer": "我先按消防设施故障理解。",
    }
    out = decide_next_action(plan, {"user_text": "我家楼下就直接停了一辆车堵着消防设施"})
    assert out["action"] == "ask_critical_question"


def test_incomplete_issue_asks_before_retrieval():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [
            {"major_code": "fire", "subcategory_code": "fire_equipment_fault", "missing": []},
            {"major_code": "building", "subcategory_code": "dangerous_building", "missing": ["structure"]},
        ],
        "answer": "已记录两个问题。",
        "question": "",
    }
    out = decide_next_action(plan, {"user_text": "消防设施坏了，旁边还有危房"})
    assert out["action"] == "ask_critical_question"
    assert out["needs_search"] is False


def test_complaint_sentence_is_not_a_confirmation():
    # 子串匹配会把"我要投诉物业"里的"要"当成同意，必须用精确/前缀匹配
    assert assistant_graph.classify_task_reply("我要投诉物业") == "other"
    assert assistant_graph.classify_task_reply("这个很重要") == "other"


def test_answer_now_never_includes_planner_leftover_question(monkeypatch):
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda _: None)
    update = render_update({
        "direct_mode": "plan_reply",
        "next_action": "answer_now",
        "clarification_question": "",
        "messages": [],
        "dialogue_plan": {
            "ok": True,
            "answer": "这属于需要关注的安全隐患。",
            "question": "要不要补充现场情况？",
        },
    })
    content = update["messages"][-1].content
    assert "？" not in content
    assert "要不要补充" not in content


def test_complete_detailed_hazard_reports_full_without_previous_question():
    plan = {
        "ok": True,
        "intent": "quick_assessment",
        "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": [],
        }],
        "answer": "消防设施失效属于严重隐患。",
        "question": "",
    }
    out = decide_next_action(plan, {
        "user_text": "消防栓是生锈的，拧开也没有水，灭火器都是过期的",
    })
    assert out["action"] == "report_full"
    assert out["needs_search"] is True


def test_casual_judgment_stays_quick_even_when_complete():
    plan = {
        "ok": True,
        "intent": "quick_assessment",
        "risk_level": "medium",
        "issues": [{
            "major_code": "traffic",
            "subcategory_code": "vehicle_occupancy",
            "missing": [],
        }],
        "answer": "这属于占道问题。",
        "question": "",
    }
    out = decide_next_action(plan, {"user_text": "盲道被车占了，算安全隐患吗？"})
    assert out["action"] == "answer_now"
    assert out["needs_search"] is False


def test_understand_exposes_policy_action(monkeypatch):
    monkeypatch.setattr(
        assistant_graph, "_understand_plan",
        lambda messages, vision, selected_major_code="": {
            "ok": True, "intent": "report_hazard", "risk_level": "high",
            "issues": [{
                "major_code": "fire", "subcategory_code": "fire_equipment_fault",
                "slots": {}, "missing": ["facility_type", "condition"],
            }],
            "categories": ["fire_equipment_fault"],
            "category_slots": {"fire_equipment_fault": {}},
            "question": "具体是哪一类消防设施？",
            "answer": "我先理解为消防设施故障。",
            "needs_search": False,
        },
    )
    state = {
        "messages": [assistant_graph.HumanMessage(content="消防设施有问题")],
        "categories": [], "category_slots": {},
    }
    understood = assistant_graph.understand(state)
    assert understood["next_action"] in {
        "ask_critical_question", "answer_with_optional_question",
    }
    # 回复出口现在多一个：ask_slot_question（它只生成问句，随后转发到回复节点）。
    # 本条要保的是"不落到 search"，精确的"落在哪个回复节点"由
    # test_slot_question_node.py::test_the_node_lands_on_a_reply_node 兜着。
    assert assistant_graph.route(understood).goto in (
        "answer_reply", "fallback_reply", "ask_slot_question")


def test_understand_downgrades_full_report_when_recomputed_missing(monkeypatch):
    monkeypatch.setattr(
        assistant_graph, "_understand_plan",
        lambda messages, vision, selected_major_code="": {
            "ok": True, "intent": "report_hazard", "risk_level": "high",
            "issues": [{
                "major_code": "fire", "subcategory_code": "fire_equipment_fault",
                "slots": {}, "missing": [],
            }],
            "categories": ["fire_equipment_fault"],
            "category_slots": {"fire_equipment_fault": {}},
            "question": "", "answer": "已确认。", "needs_search": True,
        },
    )
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="消防设施故障，帮我出报告")],
        "categories": [], "category_slots": {},
    })
    # 规划器声称 missing 为空，但 critical 槽实际没填：
    # 确定性重算必须压过规划器，用户又要了报告 → 先追问，不检索、不出正式报告。
    assert understood["missing"]
    assert understood["next_action"] == "ask_critical_question"
    assert understood["report_mode"] == "none"
    assert assistant_graph.route(understood).goto == "ask_slot_question"


def test_plan_parser_keeps_at_most_one_question():
    plan = dialogue_understanding.parse_plan(json.dumps({
        "intent": "report_hazard",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_equipment_fault",
                    "slots": {}}],
        "answer": "消防设施故障属于较高风险。请问是哪种设施？",
        "question": "请问是哪种消防设施出现了问题？",
    }))
    assert plan["question"].count("？") == 1
    assert plan["answer"].count("？") == 0


def test_plan_parser_drops_interrogative_sentence_without_question_mark():
    plan = dialogue_understanding.parse_plan(json.dumps({
        "intent": "report_hazard",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_equipment_fault",
                    "slots": {}}],
        "answer": "消防设施故障属于较高风险隐患，可能影响初期火灾扑救。方便说明一下具体是哪类设施、出现了什么问题吗。",
        "question": "请问具体是哪种消防设施出了问题？",
    }))
    assert "方便说明" not in plan["answer"]
    assert plan["answer"].count("？") == 0


def test_danger_veto_forbids_asking_but_keeps_retrieval():
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {}, "missing": ["blocker"]}],
        "categories": ["fire_lane_blocked"], "category_slots": {},
        "question": "", "answer": "", "needs_search": True,
    }
    result = decide_next_action(plan, {
        "user_text": "楼道里全是浓烟", "danger_veto": True,
        "uncertainty_signals": ["danger_term:浓烟"],
    })
    assert result["action"] != "ask_critical_question"
    assert result["needs_search"] is True


def test_cautious_uncertainty_still_asks_while_an_a_slot_is_missing():
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {}, "missing": ["blocker"]}],
        "categories": ["fire_lane_blocked"], "category_slots": {},
        "question": "被什么堵住了？", "answer": "", "needs_search": True,
    }
    result = decide_next_action(plan, {
        "user_text": "楼道里全是浓烟", "uncertainty_level": "cautious",
        "uncertainty_signals": ["ungrounded_slot:fire_lane_blocked.persistence=持续中"],
    })
    assert result["action"] == "ask_critical_question"
    assert result["needs_search"] is False


def test_danger_veto_forbids_an_optional_question_too():
    plan = {
        "ok": True, "intent": "quick_assessment", "risk_level": "medium",
        "issues": [], "categories": [], "category_slots": {},
        "question": "是冒烟还是有明火？", "answer": "浓烟环境应低姿撤离。",
        "needs_search": False,
    }
    result = decide_next_action(plan, {"user_text": "楼道里全是浓烟", "danger_veto": True})
    assert result["action"] == "answer_now"
    assert not result.get("question")


def test_policy_reason_carries_the_signal():
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {}, "missing": ["blocker"]}],
        "categories": [], "category_slots": {}, "question": "", "answer": "",
        "needs_search": True,
    }
    result = decide_next_action(plan, {
        "user_text": "楼道里全是浓烟", "danger_veto": True,
        "uncertainty_signals": ["danger_term:浓烟"],
    })
    assert "danger_term:浓烟" in result["reason"]


def test_answering_clarification_with_complete_facts_reports_full():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "medium",
        "issues": [{"major_code": "traffic", "subcategory_code": "road_occupancy", "missing": []}],
        "question": "",
        "answer": "长期占用公共通道属于占道经营。",
    }
    out = decide_next_action(plan, {
        "user_text": "长期",
        "dialogue_mode": "plain",
        "asked_question_last_turn": True,
    })
    assert out["action"] == "report_full"
    assert out["needs_search"] is True


def test_answering_clarification_with_missing_slot_asks_next():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "medium",
        "issues": [{"major_code": "traffic", "subcategory_code": "road_occupancy", "missing": ["persistence"]}],
        "question": "这个摊贩占道是长期还是临时？",
        "answer": "已记录占道经营。",
    }
    out = decide_next_action(plan, {
        "user_text": "长期",
        "dialogue_mode": "plain",
        "asked_question_last_turn": True,
    })
    assert out["action"] == "ask_critical_question"
    assert "长期还是临时" in out["question"]


def test_answering_clarification_without_planner_question_uses_schema_question():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "medium",
        "issues": [{"major_code": "traffic", "subcategory_code": "road_occupancy", "missing": ["persistence"]}],
        "question": "",
        "answer": "已记录占道经营。",
    }
    out = decide_next_action(plan, {
        "user_text": "长期",
        "dialogue_mode": "plain",
        "asked_question_last_turn": True,
    })
    assert out["action"] == "ask_critical_question"
    assert out["needs_search"] is False
    assert "长期占压还是临时停放" in out["question"]


def test_plain_mode_without_pending_question_stays_short():
    plan = {
        "ok": True,
        "intent": "quick_assessment",
        "risk_level": "medium",
        "issues": [{"major_code": "traffic", "subcategory_code": "road_occupancy", "missing": []}],
        "question": "",
        "answer": "这属于占道经营。",
    }
    out = decide_next_action(plan, {
        "user_text": "这算不算隐患",
        "dialogue_mode": "plain",
        "asked_question_last_turn": False,
    })
    assert out["action"] == "answer_now"


def test_planner_history_window_is_configurable(monkeypatch):
    from core import dialogue_understanding as du
    monkeypatch.setattr(du, "PLANNER_HISTORY_MESSAGES", 4)
    msgs = [{"role": "user", "content": "m%d" % i} for i in range(10)]
    out = du.build_planner_messages(msgs)
    blob = json.dumps(out, ensure_ascii=False)
    assert "m9" in blob and "m6" in blob
    assert "m0" not in blob


def test_report_hazard_with_answer_does_not_short_answer():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "medium",
        "issues": [{"major_code": "traffic", "subcategory_code": "road_occupancy", "missing": ["persistence"]}],
        "question": "摊贩占道是长期还是临时？",
        "answer": "这属于占道经营类隐患。",
    }
    out = decide_next_action(plan, {"user_text": "三明万达广场东北角有摊贩违规占道"})
    assert out["action"] == "ask_critical_question"


def test_report_hazard_without_planner_question_uses_schema_question():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "medium",
        "issues": [{"major_code": "traffic", "subcategory_code": "road_occupancy", "missing": ["persistence"]}],
        "question": "",
        "answer": "这属于占道经营类隐患。",
    }
    out = decide_next_action(plan, {"user_text": "三明万达广场东北角有摊贩违规占道"})
    assert out["action"] == "ask_critical_question"
    assert out["needs_search"] is False
    assert "长期占压还是临时停放" in out["question"]


def test_ask_solution_still_asks_while_a_decision_slot_is_missing():
    plan = {
        "ok": True,
        "intent": "ask_solution",
        "risk_level": "medium",
        "issues": [{"major_code": "traffic", "subcategory_code": "road_occupancy", "missing": ["persistence"]}],
        "question": "",
        "answer": "这类情况一般找城管或属地街道。",
    }
    out = decide_next_action(plan, {"user_text": "这个归谁管"})
    assert out["action"] == "ask_critical_question"
    assert out["needs_search"] is False
    assert "长期占压还是临时停放" in out["question"]
