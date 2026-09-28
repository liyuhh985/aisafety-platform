from tests.reply_helpers import (collect_chunks, fake_report_model,
                                  render_reply, render_update, run_turn,
                                  streamed_text)
import core.assistant_graph as assistant_graph
import pytest
from core import dialogue_understanding
from core.scope_policy import DOMAIN_KEYWORDS, decide_scope


def test_hazard_text_is_in_scope():
    out = decide_scope({}, "消防设施老旧，无法正常使用")
    assert out["scope"] == "hazard"


def test_weather_question_is_out_of_scope():
    out = decide_scope({}, "今天天气怎么样")
    assert out["scope"] == "out_of_scope"
    assert out["response"]


def test_emergency_has_priority_over_scope():
    out = decide_scope({}, "楼下着火了，有人被困")
    assert out["scope"] == "emergency"
    assert "119" in out["response"]


def test_ambiguous_request_gets_anchoring_question():
    out = decide_scope({}, "我有个问题想问")
    assert out["scope"] == "ambiguous"
    assert "是否涉及" in out["response"]


def test_generic_fire_word_does_not_create_false_positive():
    out = decide_scope({"scope": "out_of_scope"}, "消防员招聘条件")
    assert out["scope"] == "out_of_scope"


def test_planner_issue_overrides_weak_text():
    out = decide_scope(
        {"ok": True, "issues": [{"subcategory_code": "fire_equipment_fault"}]},
        "你说的这个",
    )
    assert out["scope"] == "hazard"


def test_plan_reads_scope_metadata():
    raw = (
        '{"intent":"other","scope":"out_of_scope","scope_confidence":0.92,'
        '"issues":[],"question":"","answer":"","needs_search":false}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["scope"] == "out_of_scope"
    assert plan["scope_confidence"] == 0.92


def test_invalid_scope_defaults_to_empty_hint():
    raw = (
        '{"intent":"other","scope":"invalid","issues":[],"question":"",'
        '"answer":"","needs_search":false}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["scope"] == ""


def test_scope_guard_refuses_out_of_scope_without_search(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True,
        "intent": "other",
        "scope": "out_of_scope",
        "scope_confidence": 0.95,
        "issues": [],
        "categories": [],
        "category_slots": {},
        "question": "",
        "answer": "今天多云",
        "needs_search": False,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="今天天气怎么样")],
    })
    update = assistant_graph.scope_guard({
        **understood,
        "messages": [assistant_graph.HumanMessage(content="今天天气怎么样")],
    })
    assert update["scope"] == "out_of_scope"
    assert update["direct_mode"] == "out_of_scope"


def test_scope_guard_keeps_hazard_flow(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True,
        "intent": "report_hazard",
        "scope": "hazard",
        "scope_confidence": 0.95,
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": [],
        }],
        "categories": ["fire_equipment_fault"],
        "category_slots": {},
        "question": "",
        "answer": "",
        "needs_search": True,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
    })
    update = assistant_graph.scope_guard({
        **understood,
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
    })
    assert update["scope"] == "hazard"
    assert "direct_mode" not in update


def test_scope_guard_emergency(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True,
        "intent": "other",
        "scope": "emergency",
        "scope_confidence": 0.9,
        "issues": [],
        "categories": [],
        "category_slots": {},
        "question": "",
        "answer": "",
        "needs_search": False,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="楼下着火了，有人被困")],
    })
    # 紧急不再由 understand 提前劫持整轮；它只表达 danger_veto，
    # 范围由 scope_guard 钉成 emergency。
    assert understood["danger_veto"] is True
    assert understood["direct_mode"] == ""
    update = assistant_graph.scope_guard({
        **understood,
        "messages": [assistant_graph.HumanMessage(content="楼下着火了，有人被困")],
    })
    assert update["scope"] == "emergency"


def test_scope_guard_ambiguous(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True,
        "intent": "other",
        "scope": "ambiguous",
        "scope_confidence": 0.4,
        "issues": [],
        "categories": [],
        "category_slots": {},
        "question": "",
        "answer": "",
        "needs_search": False,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="我有个问题想问")],
    })
    update = assistant_graph.scope_guard({
        **understood,
        "messages": [assistant_graph.HumanMessage(content="我有个问题想问")],
    })
    assert update["scope"] == "ambiguous"
    assert update["direct_mode"] == "anchor_domain"


def test_scope_guard_does_not_override_smalltalk_fast_path():
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="你好")],
    })
    assert understood["direct_mode"] == "smalltalk"
    assert assistant_graph.scope_guard({**understood}) == {}


def test_safety_text_comes_only_from_the_emergency_node(monkeypatch):
    """新契约：understand 不再发安全文本（即时反馈换成唯一出处），但规划器照常参与；
    安全文本由 emergency_guidance 产出，危险轮不进检索/报告/建单。
    """
    seen = {}

    def slow_plan(messages, vision_summary="", selected_major_code=""):
        seen["called"] = True
        return {"ok": True, "intent": "other", "issues": [], "categories": [],
                "category_slots": {}, "question": "", "answer": "", "needs_search": False}

    monkeypatch.setattr(assistant_graph, "_understand_plan", slow_plan)
    chunks = collect_chunks(monkeypatch)
    update = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="楼下着火了，有人被困")],
    })
    assert update["danger_veto"] is True
    assert update["guidance_emitted"] is True
    assert streamed_text(chunks) == ""            # understand 一个字都不发
    assert seen.get("called") is True             # 不再劫持这一轮
    fake_report_model(monkeypatch, "请立即撤离到楼下并拨打 119。")
    nodes, answer, _values = run_turn(
        assistant_graph.build_graph(), {"configurable": {"thread_id": "emg-scope"}},
        "楼下着火了，有人被困")
    assert "emergency_guidance" in nodes
    for forbidden in ("search", "report", "task_gate"):
        assert forbidden not in nodes, forbidden
    assert "119" in answer


def test_planner_smalltalk_does_not_hijack_non_greeting():
    out = decide_scope({"scope": "smalltalk"}, "今天天气")
    assert out["scope"] == "out_of_scope"
    assert "我主要负责城市安全隐患" in out["response"]


def test_exact_greeting_still_wins_over_planner_scope():
    out = decide_scope({"scope": "out_of_scope"}, "你好")
    assert out["scope"] == "smalltalk"


def test_out_of_scope_templates_vary_by_scope_key():
    first = decide_scope({}, "今天天气", scope_key="session-a|1")
    second = decide_scope({}, "今天天气", scope_key="session-a|2")
    assert first["response"] != second["response"]


def test_direct_reply_greeting_variants_are_contextual(monkeypatch):
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda _: None)
    cases = {
        "你好": "你好，我在",
        "在吗": "在的",
        "嗨": "嗨，我在",
        "谢谢": "不客气",
    }
    for text, expected in cases.items():
        update = render_update({
            "direct_mode": "smalltalk",
            "messages": [assistant_graph.HumanMessage(content=text)],
        })
        assert update["messages"][-1].content.startswith(expected)


def test_scope_guard_uses_varied_response(monkeypatch):
    first = assistant_graph.scope_guard({
        "dialogue_plan": {"ok": True, "scope": "out_of_scope", "issues": []},
        "messages": [assistant_graph.HumanMessage(content="今天天气")],
        "session_id": "scope-session",
    })
    second = assistant_graph.scope_guard({
        "dialogue_plan": {"ok": True, "scope": "out_of_scope", "issues": []},
        "messages": [
            assistant_graph.HumanMessage(content="今天天气"),
            assistant_graph.AIMessage(content=first["scope_response"]),
            assistant_graph.HumanMessage(content="今天天气"),
        ],
        "session_id": "scope-session",
    })
    assert first["scope_response"] != second["scope_response"]


def test_direct_reply_scope_templates_are_fixed(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    update = render_update({
        "direct_mode": "out_of_scope",
        "messages": [],
    })
    content = update["messages"][-1].content
    assert "我主要负责城市安全隐患" in content
    assert chunks == [{"chunk": content}]

# ===== 占道家族：确定性兜底的回归（2026-09-28 扩表）=====
# 背景：扩表前这一族在 DOMAIN_KEYWORDS 里只有字面「占道」一个词，范围判据完全依赖
# 规划器稳定抽出 issues；实测记录过一次真实误拦（db/eval_stage5_e2e.txt：
# 「有人在人行道上摆摊经营」被规划器报成 smalltalk → out_of_scope → boundary_reply）。
# 下面这组用例把「规划器什么都没给」当成最坏情况，锁住确定性兜底。

ROAD_OCCUPANCY_PHRASINGS = (
    "有人在人行道上摆摊经营",
    "路口那边摆摊的特别多",
    "人行道上摆了很多摊",
    "人行道被摊位占了",
    "店门口摆摊卖东西",
    "马路市场把路都占了",
    "小商贩占道摆摊",
    "流动摊贩占道经营",
    "路边有人占道卖水果",
    "马路边上占道的情况挺严重",
    "有建材乱堆在人行道上",
    "路边堆放了不少杂物",
    "私家车违停在人行道上",
)

OFF_DOMAIN_SAMPLES = (
    "今天天气怎么样",
    "红烧肉怎么做好吃",
    "帮我写一首关于秋天的诗",
    "推荐一部适合周末看的电影",
    "Python 列表如何去重",
    "今天股市收盘涨了多少",
)


@pytest.mark.parametrize("text", ROAD_OCCUPANCY_PHRASINGS)
def test_road_occupancy_phrasings_survive_a_silent_planner(text):
    """plan={}（规划器没抽 issues、也没给 scope 信心）时也必须判成 hazard。"""
    out = decide_scope({}, text)
    assert out["scope"] == "hazard", (text, out)


@pytest.mark.parametrize("text", OFF_DOMAIN_SAMPLES)
def test_off_domain_samples_are_still_rejected_after_widening(text):
    """扩表不能把越界输入一起放进来 —— 反向误伤检查。"""
    out = decide_scope({}, text)
    assert out["scope"] == "out_of_scope", (text, out)


def test_bare_tan_is_deliberately_not_a_domain_keyword():
    """有意不收单字「摊」：摊开/摊牌/摊销是域外说法，收了会误放。"""
    assert "摊" not in DOMAIN_KEYWORDS
    assert decide_scope({}, "把事情摊开讲清楚")["scope"] == "out_of_scope"
    assert decide_scope({}, "他准备跟老板摊牌了")["scope"] == "out_of_scope"
