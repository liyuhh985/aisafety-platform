from tests.reply_helpers import render_reply, render_update
import asyncio
import json
import re
import uuid

import core.assistant_graph as assistant_graph
import pytest
from core import dialogue_understanding
from core.agent import Agent
from core.hazard_categories import CONSULT_CATEGORIES


def test_fire_facilities_are_distinct_from_fire_lanes():
    assert "消防设施" in CONSULT_CATEGORIES
    assert "消防通道" in CONSULT_CATEGORIES


def _parse_vision_taxonomy(prompt):
    taxonomy_start = prompt.index("\n  【") + 1
    taxonomy_block = prompt[taxonomy_start:prompt.index("\n- 判别要点", taxonomy_start)]
    headings = list(
        re.finditer(
            r"^  【([a-z_]+) ([^】]+)】$",
            taxonomy_block,
            flags=re.MULTILINE,
        )
    )

    parsed = []
    for index, heading in enumerate(headings):
        body_end = (
            headings[index + 1].start()
            if index + 1 < len(headings)
            else len(taxonomy_block)
        )
        subcategory_codes = re.findall(
            r"^    ([a-z][a-z0-9_]*)\s{2,}\S",
            taxonomy_block[heading.end():body_end],
            flags=re.MULTILINE,
        )
        parsed.append(
            {
                "code": heading.group(1),
                "label": heading.group(2),
                "subcategories": subcategory_codes,
            }
        )
    return parsed


def test_vision_prompt_uses_complete_two_level_taxonomy():
    from core.hazard_taxonomy import HAZARD_TAXONOMY
    from prompts import VISION_PROMPT

    expected = [
        {
            "code": item["code"],
            "label": item["label"],
            "subcategories": [
                code for code, _ in item["subcategories"]
            ],
        }
        for item in HAZARD_TAXONOMY
    ]
    assert _parse_vision_taxonomy(VISION_PROMPT) == expected


def test_vision_prompt_taxonomy_alias_uses_compatible_prompt():
    from prompts import VISION_PROMPT, VISION_PROMPT_TAXONOMY

    assert VISION_PROMPT_TAXONOMY == VISION_PROMPT


def test_vision_prompt_keeps_legacy_json_fields():
    from prompts import VISION_PROMPT

    json_start = VISION_PROMPT.index("{")
    json_end = VISION_PROMPT.index("\n}", json_start) + 2
    schema = json.loads(VISION_PROMPT[json_start:json_end])
    assert {
        "has_hazard",
        "confidence",
        "hazard_category",
        "severity",
        "description",
        "reason_if_no_hazard",
        "location_hint",
        "rectification",
    } <= schema.keys()


def test_vision_prompt_defines_false_and_ambiguous_fallbacks():
    from prompts import VISION_PROMPT

    false_rule = next(
        line
        for line in VISION_PROMPT.splitlines()
        if "has_hazard 为 false 时" in line
    )
    assert "必须填写 reason_if_no_hazard" in false_rule
    assert (
        "hazard_category、major_category、subcategory、severity、description、"
        "location_hint 填空字符串"
    ) in false_rule
    assert "rectification 和 secondary_subcategories 填空数组" in false_rule

    ambiguous_rule = next(
        line
        for line in VISION_PROMPT.splitlines()
        if "无清晰客观异常依据" in line
    )
    assert "has_hazard 为 false" in ambiguous_rule
    assert "图像证据不足，无法确认安全隐患" in ambiguous_rule
    assert "不得为了报出隐患而强行归入" in ambiguous_rule


def test_vision_prompt_has_eight_confusion_guidelines():
    from prompts import VISION_PROMPT

    guidelines = VISION_PROMPT.split("- 判别要点（易混淆项）:", 1)[1].split(
        "\n- 消防通道占用", 1
    )[0]
    numbered_lines = re.findall(
        r"^\s*(\d+)\.\s+(.+)$",
        guidelines,
        flags=re.MULTILINE,
    )
    assert [int(number) for number, _ in numbered_lines] == list(range(1, 9))

    expected_keywords = {
        1: ("井盖破损", "manhole_damage", "路面整体塌陷", "road_surface_collapse"),
        2: ("施工无警示", "no_warning", "路面塌陷", "road_surface_collapse"),
        3: ("未设置围挡", "no_barrier", "无安全警示", "no_warning"),
        4: ("燃气泄漏", "gas_leak", "管道老化", "gas_pipe_aging"),
        5: ("裸露电线", "exposed_wire", "私拉乱接", "illegal_wiring"),
        6: ("施工临时用电", "temporary_power", "裸露电线", "exposed_wire"),
        7: ("电梯停运", "elevator_stopped", "电梯困人", "elevator_trapped"),
        8: ("车辆占道", "vehicle_occupancy", "消防通道占用", "fire_lane_blocked"),
    }
    for number, line in numbered_lines:
        missing = [
            keyword
            for keyword in expected_keywords[int(number)]
            if keyword not in line
        ]
        assert missing == [], f"判别要点 {number} 缺少关键词: {missing}"


def test_subcategory_default_risk_overrides_model_low_risk():
    raw = (
        '{"intent":"report_hazard","risk_level":"low",'
        '"issues":[{"major_code":"environment_other","subcategory_code":"hazmat_storage",'
        '"slots":{"material_info":"不明化工桶","environment":"居民楼旁"},'
        '"confidence":0.9}],"question":"","answer":"","needs_search":true}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["risk_level"] == "high"
    assert plan["issues"][0]["risk_level"] == "high"


def test_planner_prompt_uses_subcategory_default_risk_not_environment_low_rule():
    prompt = dialogue_understanding._planner_system_prompt()
    assert "环境和其他为 low" not in prompt
    assert "按小类默认风险" in prompt


def test_planner_prompt_requires_one_information_point_and_no_default_location_question():
    prompt = dialogue_understanding._planner_system_prompt()
    assert "只允许一个信息点" in prompt
    assert "不要追问具体位置" in prompt


def test_planner_prompt_lists_subcategory_slots():
    prompt = dialogue_understanding._planner_system_prompt()
    assert "fire_equipment_fault" in prompt
    assert "facility_type" in prompt
    assert "condition" in prompt


def test_planner_resolves_subcategory_under_selected_major():
    raw = (
        '{"intent":"report_hazard","selected_major_code":"fire",'
        '"major_mismatch":false,"issues":[{"major_code":"fire",'
        '"subcategory_code":"fire_equipment_fault","slots":{'
        '"facility_type":"消火栓和灭火器","condition":"老旧",'
        '"function_impact":"无法正常使用"},"confidence":0.95}],'
        '"question":"","answer":"","needs_search":true,'
        '"relationship_hint":"add"}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["ok"] is True
    assert plan["issues"][0]["major_code"] == "fire"
    assert plan["issues"][0]["subcategory_code"] == "fire_equipment_fault"
    assert plan["needs_search"] is True


def test_planner_marks_major_mismatch_and_keeps_issue_taxonomy():
    raw = (
        '{"intent":"report_hazard","selected_major_code":"municipal",'
        '"major_mismatch":true,"issues":[{"major_code":"fire",'
        '"subcategory_code":"fire_equipment_fault","slots":{},'
        '"confidence":0.9}],"question":"","answer":"",'
        '"needs_search":false,"relationship_hint":""}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["major_mismatch"] is True
    assert plan["issues"][0]["major_code"] == "fire"


def test_planner_accepts_legacy_plan_format_without_regression():
    raw = (
        '{"intent":"quick_assessment","categories":["消防设施"],'
        '"category_slots":{"消防设施":{"condition":"老旧"}},'
        '"question":"具体是哪一类消防设施？","answer":"收到",'
        '"needs_search":false,"relationship_hint":"add","confidence":0.9}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["ok"] is True
    assert plan["issues"][0]["subcategory_code"] == "fire_equipment_fault"


def test_plan_parser_rejects_unknown_categories_and_extra_questions():
    raw = (
        '{"intent":"report_hazard","categories":["消防通道","不存在"],'
        '"category_slots":{"消防通道":{"blocker":"车辆","unknown":"x"}},'
        '"question":"第一个？第二个？","answer":"收到","needs_search":false,'
        '"confidence":0.9}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["ok"] is True
    assert plan["categories"] == ["fire_lane_blocked"]
    assert set(plan["category_slots"]["fire_lane_blocked"]) == {"blocker"}
    assert plan["question"].count("？") == 1
    assert plan["question"] == "第一个？"


def test_plan_parser_accepts_markdown_fenced_json():
    raw = '```json\n{"intent":"smalltalk","categories":[],"category_slots":{},"question":"","answer":"你好","needs_search":false,"confidence":0.8}\n```'
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["ok"] is True
    assert plan["intent"] == "smalltalk"


def test_plan_parser_returns_empty_plan_for_invalid_json():
    assert dialogue_understanding.parse_plan("not json") == {}


def test_screenshot_utterance_uses_fire_facility_not_fire_lane(monkeypatch):
    monkeypatch.setattr(
        assistant_graph,
        "_understand_plan",
        lambda messages, vision, selected_major_code="", **kwargs: {
            "ok": True,
            "intent": "quick_assessment",
            "categories": ["消防设施"],
            "category_slots": {
                "消防设施": {
                    "condition": "老旧",
                    "function_impact": "不能正常使用",
                }
            },
            "question": "具体是哪一类消防设施？",
            "answer": "我理解为消防设施老旧、无法正常使用。",
            "needs_search": False,
            "relationship_hint": "add",
            "confidence": 0.95,
        },
    )
    update = assistant_graph.understand({
        "messages": [
            assistant_graph.HumanMessage(
                content="三明市万达广场对面的消防设施过于老旧，不能正常使用"
            )
        ],
        "vision_summary": "",
    })
    assert update["categories"] == ["fire_equipment_fault"]
    assert "消防通道" not in update["categories"]
    assert update["clarification_question"] == "具体是哪一类消防设施？"


def test_understand_prompt_contains_history_and_vision(monkeypatch):
    seen = {}

    def fake_plan(messages, vision_summary, selected_major_code="", **kwargs):
        seen["text"] = " ".join(getattr(m, "content", "") for m in messages)
        seen["vision"] = vision_summary
        return {"ok": True, "categories": [], "category_slots": {}, "question": "", "answer": "好"}

    monkeypatch.setattr(assistant_graph, "_understand_plan", fake_plan)
    assistant_graph.understand({
        "messages": [
            assistant_graph.HumanMessage(content="第一轮提到消防设施"),
            assistant_graph.AIMessage(content="请继续描述"),
            assistant_graph.HumanMessage(content="现在不能正常使用"),
        ],
        "vision_summary": "[视觉分析] {\"hazard_category\":\"消防安全\"}",
    })
    assert "消防设施" in seen["text"]
    assert "现在不能正常使用" in seen["text"]
    assert "消防安全" in seen["vision"]


def test_understand_derives_facts_only_from_the_plan(monkeypatch):
    """understand 没有第二套抽槽路径：事实只来自规划器结果。"""
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *a, **k: {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "categories": ["消防设施"],
        "category_slots": {"消防设施": {"condition": "老旧", "facility_type": "消火栓"}},
        "question": "", "answer": "", "needs_search": True,
    })
    update = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
        "categories": [], "category_slots": {}, "vision_summary": "",
    })
    assert update["categories"] == ["fire_equipment_fault"]
    assert update["category_slots"]["fire_equipment_fault"]["condition"] == "老旧"
    # 旧的抽槽/关键词分类器已整体删除，不可能再被调用
    assert not hasattr(assistant_graph, "_llm_extract_slots")
    assert not hasattr(assistant_graph, "_infer_categories")


def test_plan_reply_exposes_answer_and_single_question(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    update = render_update({
        "direct_mode": "plan_reply",
        "messages": [],
        "dialogue_plan": {
            "ok": True,
            "answer": "我理解为消防设施老旧、无法正常使用。",
            "question": "具体是哪一类消防设施？",
        },
    })
    content = update["messages"][-1].content
    assert "消防设施老旧" in content
    assert content.count("？") == 1
    assert chunks == [{"chunk": content}]


def test_a_second_hazard_is_not_merged_and_gets_a_scope_notice(monkeypatch):
    """一条会话一个活跃隐患：第二轮说危房不会把危房并进来，而是提示越界。"""
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *a, **k: {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "building", "subcategory_code": "dangerous_building",
                    "slots": {}}],
        "categories": ["dangerous_building"],
        "category_slots": {"dangerous_building": {}},
        "question": "", "answer": "", "needs_search": False,
    })
    update = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="旁边还有一栋危房")],
        "selected_major_code": "fire",
        "locked_major": "fire",
        "locked_subcategory": "fire_lane_blocked",
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物"}},
    })
    assert update["locked_major"] == "fire"
    assert update["locked_subcategory"] == "fire_lane_blocked"
    assert "dangerous_building" not in update["categories"]
    assert any("更像是" in str(c.get("chunk", "")) for c in chunks)
def test_rebuild_missing_supports_subcategory_codes():
    missing = assistant_graph.rebuild_missing(
        ["fire_equipment_fault"], {"fire_equipment_fault": {"condition": "老旧"}}
    )
    assert "fire_equipment_fault_facility_type" in missing
    assert "fire_equipment_fault_condition" not in missing


def test_pick_keyword_uses_chinese_subcategory_label():
    keyword = assistant_graph._pick_keyword(
        "fire_equipment_fault", {"condition": "老旧"}
    )
    assert "消防设施故障" in keyword


def test_understand_passes_selected_major_to_planner(monkeypatch):
    seen = {}

    def fake_plan(messages, vision, selected_major_code=""):
        seen["selected"] = selected_major_code
        return {"ok": True, "categories": [], "category_slots": {}}

    monkeypatch.setattr(assistant_graph, "_understand_plan", fake_plan)
    assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
        "selected_major_code": "fire",
    })
    assert seen["selected"] == "fire"


def test_fire_equipment_fault_can_offer_task_creation():
    assert assistant_graph.can_offer_task_creation({
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
        }],
        "missing": [],
    }) is True


def test_a_complete_issue_can_offer_task_creation():
    assert assistant_graph.can_offer_task_creation({
        "issues": [
            {"major_code": "traffic", "subcategory_code": "vehicle_occupancy"},
            {"major_code": "fire", "subcategory_code": "fire_equipment_fault"},
        ],
        "missing": [],
    }) is True


def test_graph_emits_taxonomy_event(monkeypatch):
    monkeypatch.setattr(
        assistant_graph,
        "_understand_plan",
        lambda messages, vision, selected_major_code="", **kwargs: {
            "ok": True,
            "intent": "quick_assessment",
            "selected_major_code": "fire",
            "major_mismatch": False,
            "issues": [{
                "major_code": "fire",
                "subcategory_code": "fire_equipment_fault",
                "slots": {"condition": "老旧"},
                "evidence": [{
                    "slot": "condition",
                    "quote": "老旧",
                    "source_ref": "u1",
                }],
            }],
            "categories": ["fire_equipment_fault"],
            "category_slots": {"fire_equipment_fault": {"condition": "老旧"}},
            "question": "",
            "answer": "收到",
            "needs_search": False,
            "relationship_hint": "add",
            "confidence": 0.9,
        },
    )

    async def collect():
        return [event async for event in assistant_graph.run_stream_events(
            message="消防设施老旧", history=[], slots={}, vision_summary="",
            session_id="taxonomy-event-test", user_id=None,
            selected_major_code="fire",
        )]

    events = asyncio.run(collect())
    taxonomy_events = [event for event in events if event[0] == "taxonomy"]
    assert taxonomy_events
    issue = taxonomy_events[0][1]["issues"][0]
    assert issue["subcategory_code"] == "fire_equipment_fault"
    assert "evidence" not in issue
    assert "slot_evidence" not in issue
    assert "active_skills" not in taxonomy_events[0][1]
    assert "skill_route_source" not in taxonomy_events[0][1]


def test_assistant_stream_passes_selected_major(monkeypatch):
    import server
    from core.memory import WorkingMemory

    seen = {}
    mem = WorkingMemory(session_id="taxonomy-passthrough-test")
    monkeypatch.setattr(server, "get_session", lambda *_: mem)

    async def fake_stream(**kwargs):
        seen.update(kwargs)
        yield "done", ""

    monkeypatch.setattr(server, "assistant_graph_stream", fake_stream)

    class Request:
        async def is_disconnected(self):
            return False

    async def collect():
        response = await server.assistant_stream(
            Request(),
            message="消防设施老旧",
            session_id="taxonomy-passthrough-test",
            user_id=1,
            selected_major_code="fire",
        )
        return [event async for event in response.body_iterator]

    asyncio.run(collect())
    assert seen["selected_major_code"] == "fire"


def test_offer_state_is_owned_by_the_graph_not_by_history_strings():
    """"问过没有"由图状态（闸门是否挂起）表达，不再靠历史里的句子做子串匹配。

    建库失败后闸门仍挂在原地，用户再说一次照常恢复；
    建库成功后 submit_task 直接 goto END，闸门不再挂起，所以不会重复创建。
    """
    assert not hasattr(assistant_graph, "_asked_to_create")
    assert not hasattr(assistant_graph, "_is_confirmation")
    assert not hasattr(assistant_graph, "_PENDING_ADDRESS")


def test_report_body_no_longer_carries_the_invitation():
    """报告正文与建任务邀请解耦：措辞改动不会再影响任何状态判定。"""
    import inspect

    source = inspect.getsource(assistant_graph.report)
    assert "建一条隐患任务" not in source


def test_complete_report_hazard_automatically_enables_search():
    raw = (
        '{"intent":"report_hazard","selected_major_code":"fire",'
        '"major_mismatch":false,"issues":[{"major_code":"fire",'
        '"subcategory_code":"fire_equipment_fault","slots":{'
        '"facility_type":"消火栓和灭火器","condition":"老旧",'
        '"function_impact":"无法正常使用"},"confidence":0.95}],'
        '"question":"","answer":"已记录","needs_search":false,'
        '"relationship_hint":"add"}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["needs_search"] is True


def test_complete_hazard_report_searches_and_offers_task(monkeypatch):
    monkeypatch.setattr(
        assistant_graph,
        "_understand_plan",
        lambda messages, vision, selected_major_code="", **kwargs: {
            "ok": True,
            "intent": "report_hazard",
            "selected_major_code": "fire",
            "major_mismatch": False,
            "issues": [{
                "major_code": "fire",
                "subcategory_code": "fire_equipment_fault",
                "slots": {
                    "facility_type": "消火栓和灭火器",
                    "condition": "老旧",
                    "function_impact": "无法正常使用",
                },
                "missing": [],
            }],
            "categories": ["fire_equipment_fault"],
            "category_slots": {"fire_equipment_fault": {
                "facility_type": "消火栓和灭火器",
                "condition": "老旧",
                "function_impact": "无法正常使用",
            }},
            "question": "",
            "answer": "已记录",
            "needs_search": True,
            "relationship_hint": "add",
            "confidence": 0.95,
        },
    )
    search_calls = []
    monkeypatch.setattr(
        assistant_graph, "_run_tool",
        lambda name, keyword, cancellation=None: (
            search_calls.append((name, keyword)) or f"[{name}] {keyword}"),
    )
    monkeypatch.setattr(
        assistant_graph._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation: iter([("chunk", "消防设施故障报告")]),
    )
    # after_report 会预抽取地址；测试不打真模型
    monkeypatch.setattr("tools.hazard_submit.extract_location", lambda history, latest: "")

    async def collect():
        return [event async for event in assistant_graph.run_stream_events(
            message="消防栓和灭火器都老旧了，不能正常使用", history=[], slots={}, vision_summary="",
            session_id=f"complete-report-test-{uuid.uuid4().hex}", user_id=None,
            selected_major_code="fire",
        )]

    events = asyncio.run(collect())
    assert any("检索" in text for kind, text in events if kind == "status")
    assert any(name == "search_regulation" for name, _ in search_calls)
    assert any(name == "search_cases" for name, _ in search_calls)
    # 邀请不再由报告正文拼装，改由 task_gate 的 interrupt 事件表达
    assert any(kind == "interrupt" for kind, _ in events)


def _fire_plan(**overrides):
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "slots": {"condition": "老旧"},
        }],
        "categories": ["fire_equipment_fault"],
        "category_slots": {"fire_equipment_fault": {"condition": "老旧"}},
        "question": "具体是哪一类消防设施？",
        "answer": "我理解为消防设施老旧。",
        "needs_search": True,
    }
    plan.update(overrides)
    return plan


def test_missing_critical_fact_asks_before_search(monkeypatch):
    monkeypatch.setattr(
        assistant_graph, "_understand_plan", lambda *a, **k: _fire_plan()
    )
    update = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
        "categories": [], "category_slots": {}, "vision_summary": "",
    })
    assert update["next_action"] == "ask_critical_question"
    # 回复出口现在多一个：ask_slot_question（见 test_slot_question_node.py）。
    assert assistant_graph.route(update).goto in (
        "answer_reply", "fallback_reply", "ask_slot_question")
    assert update["clarification_question"]


def test_missing_critical_without_planner_question_uses_slot_question(monkeypatch):
    monkeypatch.setattr(
        assistant_graph, "_understand_plan",
        lambda *a, **k: _fire_plan(question="", answer=""),
    )
    update = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
        "categories": [], "category_slots": {}, "vision_summary": "",
    })
    # 规划器没给问句时，回落到槽位 schema 里的固定问句
    assert update["next_action"] == "ask_critical_question"
    assert "消防设施" in update["clarification_question"]


def test_complete_issue_forces_search_even_for_quick_assessment():
    raw = (
        '{"intent":"quick_assessment","selected_major_code":"fire",'
        '"major_mismatch":false,"issues":[{"major_code":"fire",'
        '"subcategory_code":"fire_equipment_fault","slots":{'
        '"facility_type":"消火栓和灭火器","condition":"老旧",'
        '"function_impact":"无法正常使用"},"confidence":0.95}],'
        '"question":"是否需要建任务？","answer":"已确认","needs_search":false,'
        '"relationship_hint":"add"}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["needs_search"] is True


def test_graph_entry_uses_understanding_node():
    graph = assistant_graph.get_app().get_graph()
    assert "understand" in graph.nodes
    assert "route" in graph.nodes


def test_payload_includes_system_prompt_when_absent():
    agent = Agent(
        name="planner",
        system_prompt="SYSTEM_RULES",
        tools=[],
        base_url="http://example.invalid",
        api_key="k",
        model="m",
    )
    payload = agent._build_payload([{"role": "user", "content": "hi"}], stream=False)
    assert payload["messages"][0] == {"role": "system", "content": "SYSTEM_RULES"}


def test_payload_does_not_duplicate_existing_system_message():
    agent = Agent(
        name="planner",
        system_prompt="SYSTEM_RULES",
        tools=[],
        base_url="http://example.invalid",
        api_key="k",
        model="m",
    )
    payload = agent._build_payload(
        [
            {"role": "system", "content": "SYSTEM_RULES"},
            {"role": "user", "content": "hi"},
        ],
        stream=False,
    )
    assert [m for m in payload["messages"] if m["role"] == "system"] == [
        {"role": "system", "content": "SYSTEM_RULES"}
    ]


def test_payload_keeps_agent_prompt_when_other_system_messages_exist():
    agent = Agent(
        name="reporter",
        system_prompt="REPORT_RULES",
        tools=[],
        base_url="http://example.invalid",
        api_key="k",
        model="m",
    )
    payload = agent._build_payload(
        [
            {"role": "system", "content": "[视觉分析] {\"has_hazard\": true}"},
            {"role": "user", "content": "生成报告"},
        ],
        stream=False,
    )
    assert {"role": "system", "content": "REPORT_RULES"} in payload["messages"]
