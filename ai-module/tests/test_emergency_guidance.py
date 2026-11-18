# -*- coding: utf-8 -*-
"""阶段 1：危险场景的产物是「应急指引」，不是报告（决策 1 + 决策 4）。

四条硬不变式：
  1. danger_veto 时产出应急指引：不进 search/retrieve/report、不进建任务闸门（无 interrupt）；
  2. 回复里一个问号都不许有 —— 哪怕模型自己写了问句；
  3. 必含要点由代码定义、由代码核对；覆盖不到才前置该类型的兜底句；
  4. 措辞由模型组织，不是固定模板（同类型两次不同输出 → 两次不同结果）。
"""
import pytest
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag
from core.scope_policy import (
    covers_emergency_points,
    emergency_guidance_fallback,
    emergency_guidance_points,
    emergency_guidance_type,
)

DANGER_TEXT = "楼道里全是浓烟，人都出不来"

# 每个类型一条"覆盖了必含要点"的模型输出（措辞各不相同，证明不是模板）
COVERING = {
    "fire": "请立即低姿撤离，远离浓烟，并拨打 119 报警。",
    "gas": "马上关掉燃气总阀，开窗通风，不要开关任何电器，撤到室外。",
    "earthquake": "先在原地蹲下护住头颈，震动停止后走楼梯到室外空旷地带。",
    "electric": "先切断电源再靠近，有人昏迷请立即拨打 120。",
    "collapse": "请立即撤离并远离坍塌区域，有人被埋压请拨打 119。",
}

UNDER_COVERED = "请尽快处理，注意安全。"

PLAN = {
    "ok": True, "intent": "report_hazard", "risk_level": "high",
    "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                "slots": {"blocker": "浓烟"}}],
    "categories": ["fire_lane_blocked"],
    "category_slots": {"fire_lane_blocked": {"blocker": "浓烟"}},
    "question": "", "answer": "现场有人被困。", "needs_search": True,
}


def _patch_model(monkeypatch, reply):
    calls = []

    def fake_stream(messages, cancellation=None):
        calls.append(messages)
        yield ("chunk", reply)

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    return calls


def _run_graph(monkeypatch, text, reply, plan=None):
    """跑完整图，返回 (节点序列, 最终回复文本, 模型调用记录, 终态)。

    最终回复取 state.messages 的最后一条 —— _append_reply 会把整段历史写回来，
    所以不能把 messages 里的每一条都当成回复。
    """
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan or PLAN))
    calls = _patch_model(monkeypatch, reply)
    streamed = []
    monkeypatch.setattr(ag, "get_stream_writer", lambda: streamed.append)
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "emg-" + text}}
    nodes = []
    for mode, item in app.stream(
        {"session_id": "s", "messages": [HumanMessage(content=text)]},
        config, stream_mode=["updates", "custom"],
    ):
        if mode == "updates":
            nodes.extend(item.keys())
    values = app.get_state(config).values
    messages = values.get("messages") or []
    answer = getattr(messages[-1], "content", "") if messages else ""
    return nodes, answer, calls, values



# ---------- 1. 产物分型：不进检索/报告/建单 ----------

def test_danger_never_reaches_search_report_or_task_gate(monkeypatch):
    nodes, _texts, _calls, _values = _run_graph(
        monkeypatch, DANGER_TEXT, COVERING["fire"])
    assert "emergency_guidance" in nodes
    for forbidden in ("search", "retrieve", "report", "after_report",
                      "task_gate", "submit_task", "close_task"):
        assert forbidden not in nodes, forbidden
    assert nodes.index("emergency_guidance") > nodes.index("route")


def test_danger_turn_emits_no_interrupt(monkeypatch):
    """建任务闸门不可达 → 这一轮不会挂起等人确认。"""
    nodes, _t, _c, values = _run_graph(monkeypatch, DANGER_TEXT, COVERING["fire"])
    assert "task_gate" not in nodes
    assert values.get("offer_task") in (None, False)


def test_understand_never_gives_a_report_action_under_a_danger_veto(monkeypatch):
    """不变式：danger_veto 与 next_action 不能各说各话（决策权只有 understand 一处）。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(PLAN))
    out = ag.understand({"messages": [HumanMessage(content=DANGER_TEXT)]})
    assert out["danger_veto"] is True
    assert out["next_action"] == ag.EMERGENCY_ACTION
    assert out["report_mode"] == "none"
    assert ag.route(out).goto == "emergency_guidance"


def test_route_still_maps_report_actions_to_search():
    assert ag.route({"next_action": "report_full"}).goto == "search"
    assert ag.route({"next_action": "report_preliminary"}).goto == "search"


# ---------- 2. 一个字问号都不许有 ----------

def test_question_mark_is_removed_even_when_the_model_asks(monkeypatch):
    _nodes, answer, _calls, _v = _run_graph(
        monkeypatch, DANGER_TEXT,
        "请立即撤离到室外并拨打 119 报警。需要我帮你建一条任务吗？")
    assert "？" not in answer and "?" not in answer
    assert "119" in answer
    assert "需要我帮你建" not in answer


def test_a_model_reply_that_is_only_a_question_falls_back(monkeypatch):
    _n, answer, _c, _v = _run_graph(monkeypatch, DANGER_TEXT, "你在几楼？")
    assert answer.strip()
    assert "？" not in answer and "?" not in answer
    assert covers_emergency_points(answer, "fire")


@pytest.mark.parametrize("text", [
    "楼道里全是浓烟，人都出不来",      # fire
    "我家厨房燃气管道漏气",            # gas
    "地震了房子在晃",                  # earthquake
    "有人触电了",                      # electric
    "围墙坍塌了，有人被压住",          # collapse
])
def test_no_question_mark_for_every_emergency_type(monkeypatch, text):
    _n, answer, _c, _v = _run_graph(
        monkeypatch, text, "请撤离到安全地带并拨打 119。要建任务吗？")
    assert "？" not in answer and "?" not in answer


# ---------- 3. 必含要点：代码核对 + 兜底 ----------

@pytest.mark.parametrize("kind", sorted(COVERING))
def test_five_types_cover_their_required_points(monkeypatch, kind):
    text = {
        "fire": "楼道里全是浓烟，人都出不来",
        "gas": "我家厨房燃气管道漏气",
        "earthquake": "地震了房子在晃",
        "electric": "有人触电了",
        "collapse": "围墙坍塌了",
    }[kind]
    assert emergency_guidance_type(text) == kind
    _n, answer, calls, _v = _run_graph(monkeypatch, text, COVERING[kind])
    assert calls, "应急指引必须由模型组织措辞"
    assert covers_emergency_points(answer, kind)
    # 模型已覆盖要点 → 不该再前置兜底句
    assert not answer.lstrip().startswith(emergency_guidance_fallback(kind))


@pytest.mark.parametrize("kind", sorted(COVERING))
def test_under_covered_reply_gets_the_fallback_prepended(monkeypatch, kind):
    text = {
        "fire": "楼道里全是浓烟，人都出不来",
        "gas": "我家厨房燃气管道漏气",
        "earthquake": "地震了房子在晃",
        "electric": "有人触电了",
        "collapse": "围墙坍塌了",
    }[kind]
    _n, answer, _c, _v = _run_graph(monkeypatch, text, UNDER_COVERED)
    assert answer.startswith(emergency_guidance_fallback(kind))
    assert covers_emergency_points(answer, kind)


def test_every_type_has_points_and_a_covering_fallback():
    for kind in COVERING:
        assert emergency_guidance_points(kind)
        fallback = emergency_guidance_fallback(kind)
        assert covers_emergency_points(fallback, kind), kind
        assert "？" not in fallback and "?" not in fallback


# ---------- 4. 措辞由模型组织，不是固定模板 ----------

def test_wording_comes_from_the_model_not_from_a_template(monkeypatch):
    text_a = _run_graph(monkeypatch, DANGER_TEXT, COVERING["fire"])[1]
    text_b = _run_graph(
        monkeypatch, DANGER_TEXT, "马上从楼梯撤离，路上别回头，到楼下打 119 报警。")[1]
    assert text_a and text_b
    assert text_a != text_b
    for text in (text_a, text_b):
        assert emergency_guidance_fallback("fire") not in text
        assert covers_emergency_points(text, "fire")


def test_guidance_is_streamed_to_the_client(monkeypatch):
    """产物必须真的流出去（前端靠 custom 流的 chunk 渲染）。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(PLAN))
    _patch_model(monkeypatch, COVERING["fire"])
    chunks = []
    monkeypatch.setattr(ag, "get_stream_writer", lambda: chunks.append)
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "emg-stream"}}
    for _mode, _item in app.stream(
        {"session_id": "s", "messages": [HumanMessage(content=DANGER_TEXT)]},
        config, stream_mode=["updates", "custom"],
    ):
        pass
    streamed = "".join(
        str(item.get("chunk", "")) for item in chunks if isinstance(item, dict))
    assert "119" in streamed
    assert "？" not in streamed and "?" not in streamed


def test_unknown_type_still_gets_safety_points():
    assert emergency_guidance_type("楼道里堆了很多纸箱") == ""
    fallback = emergency_guidance_fallback("")
    assert covers_emergency_points(fallback, "")
