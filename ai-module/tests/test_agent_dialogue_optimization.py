from tests.reply_helpers import render_reply, render_update
import asyncio

import core.assistant_graph as assistant_graph
import pytest
from core.hazard_categories import CONSULT_CATEGORIES, SUBMIT_CATEGORIES, normalize_vision_category


def test_consultation_and_submission_category_boundaries_are_explicit():
    assert CONSULT_CATEGORIES == (
        "占道", "危房", "消防通道", "消防设施", "高空坠物", "井盖/道路", "电气", "施工", "其他"
    )
    assert {"fire_equipment_fault", "fire_lane_blocked", "manhole_damage", "no_barrier"} <= set(SUBMIT_CATEGORIES)


def test_vision_aliases_normalize_to_dialogue_categories():
    assert normalize_vision_category("消防安全") == "消防通道"
    assert normalize_vision_category("电气安全") == "电气"
    assert normalize_vision_category("燃气安全") == "其他"


def test_direct_mode_only_short_circuits_greetings():
    """G5：语义判断不再被关键词在规划器之前短路。"""
    assert assistant_graph._detect_direct_mode("你好") == "smalltalk"
    assert assistant_graph._detect_direct_mode("你好！") == "smalltalk"
    assert assistant_graph._detect_direct_mode("谢谢。") == "smalltalk"
    # 这两句以前会命中 quick_judgment 而绕过规划器，只能拿到一句没有检索的回答
    assert assistant_graph._detect_direct_mode("盲道被车占了，算安全隐患吗？") == ""
    assert assistant_graph._detect_direct_mode("长期占着盲道，完全堵死，帮我查相关法规和案例") == ""


def test_direct_mode_does_not_ignore_a_supplied_image():
    assert assistant_graph._detect_direct_mode("盲道被车占算隐患吗？", "[视觉分析] {}") == ""


_COMPLETE_PLAN = {
    "ok": True, "intent": "report_hazard", "risk_level": "high",
    "issues": [{
        "major_code": "road", "subcategory_code": "road_occupancy",
        "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"},
    }],
    "categories": ["road/road_occupancy"],
    "category_slots": {"road/road_occupancy": {
        "behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}},
    "question": "", "answer": "", "needs_search": True,
}


def test_understand_clears_mode_before_followup(monkeypatch):
    """上一轮是问候，本轮是隐患：understand 必须清空 direct_mode，否则会串到问候分支。"""
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *a, **k: dict(_COMPLETE_PLAN))
    update = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="长期占着盲道，查一下法规和案例")],
        "direct_mode": "smalltalk", "categories": [], "category_slots": {},
        "vision_summary": "",
    })
    assert update["direct_mode"] == ""
    assert assistant_graph.route(update).goto == "search"


def test_smalltalk_emits_visible_chunk(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    update = render_update({"direct_mode": "smalltalk", "messages": []})
    assert chunks == [{"chunk": update["messages"][-1].content}]


def test_thanks_gets_a_natural_reply(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    reply = render_update({
        "direct_mode": "smalltalk",
        "messages": [assistant_graph.HumanMessage(content="谢谢。")],
    })["messages"][-1].content
    assert reply.startswith("不客气")
    assert chunks == [{"chunk": reply}]


def test_greeting_traverses_graph_without_retrieval(monkeypatch):
    def forbid(*_, **__):
        pytest.fail("greeting should not call the planner or retrieval")

    monkeypatch.setattr(assistant_graph, "_understand_plan", forbid)
    monkeypatch.setattr(assistant_graph, "_run_tool", forbid)

    async def collect():
        return [event async for event in assistant_graph.run_stream_events(
            message="你好！", history=[], slots={}, vision_summary="",
            session_id="greeting-graph-test", user_id=None,
        )]

    events = asyncio.run(collect())
    assert ("chunk", "你好，我在。你可以直接描述现场隐患，或者上传图片。") in events
    assert not any(kind == "status" and "检索" in text for kind, text in events)
    assert events[-1] == ("done", "")


def test_quick_judgment_goes_through_the_planner(monkeypatch):
    """G5 回归："算隐患吗" 必须交给规划器判断，而不是被关键词短路成无检索的泛泛回答。"""
    seen = {}

    def fake_plan(messages, vision_summary, selected_major_code="", **kwargs):
        seen["called"] = True
        return {
            "ok": True, "intent": "quick_assessment", "risk_level": "medium",
            "issues": [], "categories": [], "category_slots": {},
            "question": "是完全堵死还是部分占用？",
            "answer": "占用盲道属于安全隐患。",
            "needs_search": False,
        }

    def forbid(*_, **__):
        pytest.fail("quick judgment must not run retrieval")

    monkeypatch.setattr(assistant_graph, "_understand_plan", fake_plan)
    monkeypatch.setattr(assistant_graph, "_run_tool", forbid)

    async def collect():
        return [event async for event in assistant_graph.run_stream_events(
            message="盲道被车占了，算安全隐患吗？", history=[], slots={},
            vision_summary="", session_id="judgment-graph-test", user_id=None,
        )]

    events = asyncio.run(collect())
    assert seen.get("called") is True
    assert any(kind == "chunk" and "占用盲道属于安全隐患" in text for kind, text in events)
    assert not any("建一条隐患任务" in text for _, text in events)
    assert events[-1] == ("done", "")


def test_report_offers_task_creation_for_any_resolved_category(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(
        assistant_graph._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation: iter([("chunk", "这是初步分析。")]),
    )
    update = assistant_graph.report({"messages": [], "categories": ["电气"], "missing": []})
    # 任何已识别且信息完整的隐患都可以建任务，不再限定特定类别
    assert update["offer_task"] is True
    assert "建一条隐患任务" not in update["draft_report"]
    assert chunks == [{"chunk": "这是初步分析。"}]


def test_empty_or_unsupported_submit_category_never_becomes_roadblock(monkeypatch):
    from tools import hazard_submit

    def forbid_external(*_, **__):
        pytest.fail("unsupported category must not call external services")

    monkeypatch.setattr(hazard_submit, "geocode", forbid_external)
    monkeypatch.setattr(hazard_submit, "enqueue_hazard_create", forbid_external)

    for category in ("", "燃气安全"):
        monkeypatch.setattr(
            hazard_submit._extractor, "_call_llm",
            lambda *_, **__: {"content": (
                '{"category":"' + category + '","address":"北京市朝阳区建国路",'
                '"district":"朝阳区","description":"疑似隐患","severity":1}'
            )},
        )
        result = hazard_submit.submit_from_history(1, [], "这里有隐患")
        assert result["action"] == "no_category"


@pytest.mark.parametrize("vision_result", [None, RuntimeError("视觉超时"), '{"hazard_category":"消防安全"}'])
def test_stream_stores_user_and_vision_context_once(monkeypatch, tmp_path, vision_result):
    import server
    import mimo_client
    from core.memory import WorkingMemory

    mem = WorkingMemory(session_id="dialogue-test")
    seen = []
    monkeypatch.setattr(server, "get_session", lambda *_: mem)
    monkeypatch.setattr(server, "_save_upload", lambda _: str(tmp_path / "upload.png"))

    def analyze(*_):
        if isinstance(vision_result, Exception):
            raise vision_result
        return vision_result

    monkeypatch.setattr(mimo_client.MiMoVisionClient, "analyze_json", analyze)
    monkeypatch.setattr(mimo_client.MiMoVisionClient, "__init__", lambda self, *args, **kwargs: None)

    async def fake_stream(**kwargs):
        seen.append(kwargs)
        yield "chunk", "已经收到，我先根据文字判断。"
        yield "done", ""

    monkeypatch.setattr(server, "assistant_graph_stream", fake_stream)

    class Request:
        async def is_disconnected(self):
            return False

    class File:
        filename = "upload.png"

    async def collect():
        response = await server.assistant_stream(
            Request(), message="请看看是否危险", session_id="dialogue-test",
            user_id=1, file=File()
        )
        return [event async for event in response.body_iterator]

    events = asyncio.run(collect())
    assert any('"type": "chunk"' in event for event in events)
    assert len([item for item in mem.messages if item["role"] == "user"]) == 1
    system = [item["content"] for item in mem.messages if item["role"] == "system"]
    assert len(system) == 1
    assert not any("[视觉分析] None" in item["content"] for item in mem.messages)
    if isinstance(vision_result, str):
        assert system[0].startswith("[视觉分析] ")
        assert seen[0]["vision_summary"] == system[0]
    else:
        assert system[0].startswith("[视觉分析失败")
        assert seen[0]["vision_summary"] == ""
