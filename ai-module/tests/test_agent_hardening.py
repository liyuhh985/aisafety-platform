"""本轮加固：取消穿透 / 危险判定范围 / 指引只发一次 / 死条件 / 死代码。"""
from tests.reply_helpers import (collect_chunks, fake_report_model, render_reply,
                                  render_update, run_turn, streamed_text)
import pytest
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag
from core.cancellation import CancellationToken, StreamCancelled
from core.uncertainty import assess

SMOKE = "楼道里全是浓烟，人都出不来"


# ---------- 1. 取消令牌穿进图内 ----------
class _FakeTool:
    def __init__(self):
        self.kwargs = None

    def execute(self, **kwargs):
        self.kwargs = kwargs
        return "TOOL_RESULT"


def test_retrieve_passes_the_cancel_token_into_the_tool(monkeypatch):
    fake = _FakeTool()
    monkeypatch.setitem(ag._TOOL_MAP, "search_cases", fake)
    token = CancellationToken()
    out = ag.retrieve({"category": "road", "tool": "search_cases", "keyword": "占道"},
                      {"configurable": {"cancel_token": token}})
    assert fake.kwargs["cancellation"] is token
    assert out["category_results"]["road"]["case"] == "TOOL_RESULT"


def test_retrieve_without_config_still_works(monkeypatch):
    fake = _FakeTool()
    monkeypatch.setitem(ag._TOOL_MAP, "search_cases", fake)
    ag.retrieve({"category": "road", "tool": "search_cases", "keyword": "占道"})
    assert fake.kwargs["cancellation"] is None


def test_report_passes_the_cancel_token_into_the_model(monkeypatch):
    seen = {}

    def fake_stream(messages, cancellation=None):
        seen["token"] = cancellation
        yield ("chunk", "BODY")

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    token = CancellationToken()
    ag.report({"messages": [], "categories": [], "category_results": {}, "missing": [],
               "report_mode": "preliminary"}, {"configurable": {"cancel_token": token}})
    assert seen["token"] is token


def test_direct_reply_fallback_passes_the_cancel_token(monkeypatch):
    seen = {}

    def fake_stream(messages, cancellation=None):
        seen["token"] = cancellation
        yield ("chunk", "ANSWER")

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    token = CancellationToken()
    render_update({"direct_mode": "", "messages": [], "dialogue_plan": {}},
                    {"configurable": {"cancel_token": token}})
    assert seen["token"] is token


def test_tool_execute_does_not_swallow_cancellation():
    from core.tool import Tool

    def boom(**_kwargs):
        raise StreamCancelled()

    tool = Tool(name="x", description="", parameters={}, required=[], func=boom)
    with pytest.raises(StreamCancelled):
        tool.execute()


def test_run_tool_reraises_cancellation_instead_of_returning_a_failure_string(monkeypatch):
    class _CancelTool:
        def execute(self, **kwargs):
            raise StreamCancelled()

    monkeypatch.setitem(ag._TOOL_MAP, "search_cases", _CancelTool())
    with pytest.raises(StreamCancelled):
        ag._run_tool("search_cases", "占道")


# ---------- 2. 危险判定只看当前话题 ----------
def test_danger_comes_only_from_this_turn_or_the_model():
    """危险只看本轮原话 + 模型标志：上一轮的危险不再被代码继承。"""
    inherited = assess(
        {"ok": True, "issues": []},
        [{"role": "user", "content": "楼道里全是浓烟"},
         {"role": "user", "content": "我该怎么跑"}],
    )
    assert inherited["danger_veto"] is False
    this_turn = assess(
        {"ok": True, "issues": []},
        [{"role": "user", "content": "楼下井盖破了"},
         {"role": "user", "content": "刚才起火了"}],
    )
    assert this_turn["danger_veto"] is True
    model_says = assess(
        {"ok": True, "immediate_danger": True, "issues": []},
        [{"role": "user", "content": "我该怎么跑"}],
    )
    assert model_says["danger_veto"] is True


def test_first_turn_never_inherits():
    verdict = assess({"ok": True, "issues": []}, [{"role": "user", "content": "楼下井盖破了"}])
    assert verdict["danger_veto"] is False


# ---------- 3. 指引尽早发出，且一次危险事件只发一次 ----------
def test_model_flagged_danger_still_gets_guidance_from_the_emergency_node(monkeypatch):
    """不变式：词表没命中、只有模型判定危险时，用户仍然拿得到安全文本。

    出处变了 —— understand 不再发，由 emergency_guidance 按类型产出。
    """
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: {
        "ok": True, "immediate_danger": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "utility", "subcategory_code": "exposed_wire", "slots": {}}],
        "categories": ["exposed_wire"], "category_slots": {}, "question": "", "answer": "",
        "needs_search": True})
    chunks = collect_chunks(monkeypatch)
    out = ag.understand({"messages": [HumanMessage(content="墙里有嗡嗡声还发烫")]})
    assert out["danger_veto"] is True
    assert out["guidance_emitted"] is True
    assert out["next_action"] == ag.EMERGENCY_ACTION
    assert streamed_text(chunks) == ""            # understand 自己一个字都不发
    calls = fake_report_model(monkeypatch, "请立即撤离到安全区域并拨打 119。")
    nodes, answer, _values = run_turn(
        ag.build_graph(), {"configurable": {"thread_id": "emg-model-only"}},
        "墙里有嗡嗡声还发烫")
    assert "emergency_guidance" in nodes
    assert "119" in answer
    assert calls, "应急指引的措辞要由模型组织"


def _plan_for(text):
    """让 stub 像真实规划器一样跟着话题变：井盖 -> manhole_damage。"""
    code = "manhole_damage" if "井盖" in text else "fire_lane_blocked"
    return {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "municipal", "subcategory_code": code,
                    "slots": {"blocker": "浓烟"} if code == "fire_lane_blocked" else {}}],
        "categories": [code],
        "category_slots": {code: {"blocker": "浓烟"} if code == "fire_lane_blocked" else {}},
        "question": "", "answer": "", "needs_search": True}


def test_every_danger_turn_gets_its_own_guidance(monkeypatch):
    """新契约：指引是「这一轮的产物」，所以同一场危险的第 2 轮照样给，不再静默。

    旧不变式「一次危险事件只提醒一次」描述的是「指引是前缀」的旧结构，已作废。
    """
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: {
        "ok": True, "immediate_danger": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {"blocker": "浓烟"}}],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {"blocker": "浓烟"}},
        "question": "", "answer": "", "needs_search": True})
    chunks = collect_chunks(monkeypatch)
    fake_report_model(monkeypatch, "请立即低姿撤离并拨打 119。")
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "emg-two-turns"}}
    first_nodes, first_answer, _v1 = run_turn(app, config, "楼道里全是浓烟")
    second_nodes, second_answer, values2 = run_turn(app, config, "我该怎么跑")
    assert values2.get("danger_veto") is True          # 第 2 轮仍在同一场危险里
    for nodes, answer in ((first_nodes, first_answer), (second_nodes, second_answer)):
        assert "emergency_guidance" in nodes
        assert "119" in answer
    assert streamed_text(chunks).count("119") == 2     # 两轮各一次，且都不是 understand 发的
def test_scope_guard_skip_modes_only_contains_smalltalk():
    assert ag._SCOPE_DIRECT_MODES == ("smalltalk",)


def test_stream_local_dead_code_is_gone():
    assert not hasattr(ag, "_stream_local")


def test_a_danger_turn_emits_its_safety_text_exactly_once(monkeypatch):
    """一轮内安全文本只出现一次：understand 不发，emergency_guidance 缓冲后只流一次。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: {
        "ok": True, "immediate_danger": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked", "slots": {}}],
        "categories": ["fire_lane_blocked"], "category_slots": {}, "question": "",
        "answer": "", "needs_search": True})
    chunks = collect_chunks(monkeypatch)
    fake_report_model(monkeypatch, "请立即低姿撤离，远离浓烟，并拨打 119 报警。")
    nodes, answer, _values = run_turn(
        ag.build_graph(), {"configurable": {"thread_id": "emg-once"}}, SMOKE)
    assert nodes.count("emergency_guidance") == 1
    assert answer.count("119") == 1
    assert sum(1 for c in chunks if "119" in str(c)) == 1
