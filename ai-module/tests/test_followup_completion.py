# -*- coding: utf-8 -*-
"""G2：跨轮的「上一轮问过」标志。

修复前：begin_turn 每轮把 asked_question_last_turn 清零，而它唯一的读者在**下一轮**
（dialogue_policy.py:122），于是「用户回答了追问 且 信息齐全 → 出完整报告」这条分支
永远不成立。高/中风险小类还有 `risk in {high, medium}` 那条兜底挡着，行为不变；
低风险小类（environment_other 下的 garbage_pile / sewage_odor / other）会退化成
「只回一句话」。

本测试跑两轮真图（stub 掉模型与检索）：
  第 1 轮 缺 A 类槽 → 把问句交付给用户
  第 2 轮 补齐   → 必须出完整报告
"""
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag

# 检索结果必须"看起来正常"：否则会触发检索重试环去调改写模型（联网）。
# 类别行必须与锁定大类同属「环境与其他」，否则 filter_by_major 判成 T2 触发重试。
CASE_OK = (
    "=== 混合检索结果: 「垃圾堆积 装修垃圾」(语义1+关键词1) ===\n"
    "\n【结果1】[语义匹配] 小区内装修垃圾长期堆放\n  类别: 环境与其他/垃圾堆积\n"
)

_REPLY = "这属于环境卫生问题，建议联系物业或街道清运。"


def _plan(**over):
    plan = {
        "ok": True, "intent": "quick_assessment", "risk_level": "low",
        "answer": "", "question": "", "needs_search": True,
        "issues": [], "categories": [], "category_slots": {},
        "perceived_major": "environment_other",
    }
    plan.update(over)
    return plan


# 第 1 轮：describe 还空着，规划器自己带了一句问话
PLAN_ASKING = _plan(
    question="能再具体描述一下这个安全隐患是什么吗？",
    issues=[{"major_code": "environment_other", "subcategory_code": "garbage_pile",
             "slots": {}}],
    categories=["garbage_pile"],
    category_slots={"garbage_pile": {}},
)

# 第 2 轮：用户答了，槽位补齐
PLAN_COMPLETE = _plan(
    issues=[{"major_code": "environment_other", "subcategory_code": "garbage_pile",
             "slots": {"describe": "装修垃圾"}}],
    categories=["garbage_pile"],
    category_slots={"garbage_pile": {"describe": "装修垃圾"}},
)


def _stub(monkeypatch, plans):
    seq = [dict(p) for p in plans]
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **k: {
        "question": "具体是些什么东西堆在这儿？", "target_slot": "describe"})
    monkeypatch.setattr(ag, "_run_tool",
                        lambda name, keyword, cancellation=None: CASE_OK)
    monkeypatch.setattr(ag, "_probe_top1_score", lambda *a, **k: None)
    monkeypatch.setattr(ag, "_report_llm", type("F", (), {
        "_call_llm_stream_events": staticmethod(
            lambda messages, cancellation=None: iter([("chunk", _REPLY)]))})())
    monkeypatch.setattr(ag, "_rewrite_llm", type("F", (), {
        "_call_llm": staticmethod(
            lambda messages, cancellation=None: {"content": "垃圾堆积 装修垃圾"})})())


def _run(app, config, text):
    for _mode, _item in app.stream(
        {"session_id": "s", "messages": [HumanMessage(content=text)]},
        config, stream_mode=["updates", "custom"],
    ):
        pass
    return app.get_state(config).values


def test_answering_the_follow_up_produces_a_full_report(monkeypatch):
    _stub(monkeypatch, [PLAN_ASKING, PLAN_COMPLETE])
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "followup-completion"}}

    first = _run(app, config, "楼下垃圾堆成山了")
    assert first["missing"] == ["garbage_pile_describe"]
    assert first["asked_question_last_turn"] is True
    assert "？" in first["messages"][-1].content      # 用户真的看见了那个问句

    second = _run(app, config, "堆了半个月没人管，是装修垃圾")
    assert second["missing"] == []
    assert second["asked_question_last_turn"] is False  # 本轮没问 → 下一轮读到的就是 False
    assert second["next_action"] == "report_full"       # ← 修复前是 answer_now
    assert second["report_mode"] == "full"


# 第 2 轮仍没补齐：规划器继续追问，而不是"因为上一轮问过就直接出报告"
PLAN_STILL_INCOMPLETE = _plan(
    question="那堆的是生活垃圾还是装修垃圾？",
    issues=[{"major_code": "environment_other", "subcategory_code": "garbage_pile",
             "slots": {}}],
    categories=["garbage_pile"],
    category_slots={"garbage_pile": {}},
)


def test_incomplete_facts_still_do_not_produce_a_report(monkeypatch):
    """标志跨轮保留后，仍不能凭"上一轮问过"越过"信息齐全"这道闸门。

    dialogue_policy 的这条分支带 `complete and` 前置条件 —— 这条测试把它钉住，
    防止以后有人把条件放松成"问过就出报告"。
    """
    _stub(monkeypatch, [PLAN_ASKING, PLAN_STILL_INCOMPLETE])
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "followup-still-incomplete"}}

    _run(app, config, "楼下垃圾堆成山了")
    second = _run(app, config, "还是那样，没人管")

    assert second["missing"] == ["garbage_pile_describe"]
    assert second["next_action"] != "report_full"
    assert second["report_mode"] != "full"
