# -*- coding: utf-8 -*-
"""闭环的最后一改（M1 产物判据 + M2 危险词表）。

依据：`docs/superpowers/specs/2026-10-01-loop-closure-final.md` §3。

M1 要解决的问题（实测）：同一句话、同一段历史，规划器跑 10 次给出 4 种 intent
（report_hazard 6 / quick_assessment 2 / other 1 / 空 1），而 intent 是决定进哪个节点的
唯一输入 —— 产物就跟着飘。改法：产物的判据全部换成**代码可判**的信号 + 跨轮继承。
"""
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag
from core.dialogue_policy import (MODE_PLAIN, MODE_PRELIMINARY, MODE_REPORT,
                                 decide_next_action, mode_of_action, wants_report)
from core.uncertainty import has_active_danger


# ---------------------------------------------------------------- M2：危险词表

def test_burning_smoke_sentence_is_now_recognised_as_danger():
    """实测漏网的那句（词表原来一个词都没命中）现在必须命中。"""
    assert has_active_danger("楼道里面有易燃物品正在燃烧有很大的黑烟里面还有人")


def test_burning_terms_do_not_swallow_ordinary_hazards():
    """不能误伤：光杆"燃烧"没收，露天焚烧这种普通隐患不该走应急指引。"""
    assert not has_active_danger("楼下有人露天焚烧垃圾")
    assert not has_active_danger("路边那个井盖不见了")


# ---------------------------------------------------------------- M1：产物由代码判

def _plan(intent, issues):
    return {"ok": True, "intent": intent, "risk_level": "high", "answer": "嗯",
            "question": "", "issues": issues, "needs_search": True}


MISSING_ISSUE = [{"major_code": "building", "subcategory_code": "falling_object",
                  "slots": {}, "missing": ["source"]}]
FULL_ISSUE = [{"major_code": "building", "subcategory_code": "falling_object",
               "slots": {"source": "外墙"}, "missing": []}]


def _decide(intent, issues, user_text, prev_mode=""):
    return decide_next_action(
        _plan(intent, issues),
        {"user_text": user_text, "missing": [],
         "dialogue_mode": prev_mode, "danger_veto": False, "uncertainty_level": "ok"},
    )


def test_report_intent_no_longer_forces_a_report():
    """模型说 report_hazard、但用户话里没有"要报告"的信号 → 不给报告。"""
    d = _decide("report_hazard", MISSING_ISSUE, "那人行道旁边摇摇欲坠的广告牌呢")
    assert d["action"] not in ("report_full", "report_preliminary"), d


def test_explicit_report_request_still_switches_to_report():
    """用户明说要法规/报告 → 必须切报告（这是升级的唯一通道）。"""
    d = _decide("other", MISSING_ISSUE, "帮我查一下广告牌的法规")
    assert d["action"] == "report_preliminary"
    assert wants_report("帮我查一下广告牌的法规")


def test_plain_mode_never_upgrades_even_when_facts_are_complete():
    """决策 5 的天花板：纯回答档，事实补齐了也不升级成报告。"""
    d = _decide("report_hazard", FULL_ISSUE, "这算不算隐患", prev_mode=MODE_PLAIN)
    assert d["action"] == "answer_now"
    assert d.get("report_mode") in ("", "none", None)


def test_omitted_question_inherits_the_previous_mode():
    """省略句（"那 X 呢"）单看判不出产物 → 靠继承。"""
    d = _decide("report_hazard", MISSING_ISSUE, "那那个呢", prev_mode=MODE_PLAIN)
    assert d["action"] == "answer_now"


def test_action_to_mode_mapping():
    assert mode_of_action("answer_now") == MODE_PLAIN
    assert mode_of_action("answer_with_optional_question") == MODE_PLAIN
    # 关键信息缺失→追问，属「初步判断+追问」档，补全后**能**升级
    assert mode_of_action("ask_critical_question") == MODE_PRELIMINARY
    assert mode_of_action("report_preliminary") == MODE_PRELIMINARY
    assert mode_of_action("report_full") == MODE_REPORT


def test_danger_does_not_rewrite_the_mode():
    """危险是临时的：一场火不该把会话永久变成别的模式。"""
    assert mode_of_action("emergency_guidance", MODE_PLAIN) == MODE_PLAIN
    assert mode_of_action("fallback", MODE_REPORT) == MODE_REPORT


# ---------------------------------------------------------------- M1：端到端（真图）

TURN1 = "路边那个新的井盖是不是隐患？"
TURN2 = "那人行道旁边摇摇欲坠的广告牌呢"

PLAN1 = {"ok": True, "intent": "quick_assessment", "risk_level": "low",
         "answer": "这不算隐患，新井盖安装到位就没有安全问题。",
         "question": "", "needs_search": False, "perceived_major": "municipal",
         "issues": [{"major_code": "municipal", "subcategory_code": "manhole_damage",
                     "slots": {"defect": "新装完好"}}],
         "categories": ["manhole_damage"],
         "category_slots": {"manhole_damage": {"defect": "新装完好"}}}
PLAN2 = {"ok": True, "intent": "report_hazard", "risk_level": "high",
         "answer": "", "question": "", "needs_search": True,
         "perceived_major": "building", "perceived_subcategory": "falling_object",
         "issues": [{"major_code": "building", "subcategory_code": "falling_object",
                     "slots": {}}],
         "categories": ["falling_object"], "category_slots": {"falling_object": {}}}


def _stub(monkeypatch):
    seq = [dict(PLAN1), dict(PLAN2)]
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: seq.pop(0))
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **k: {"question": "哪一块？", "target_slot": ""})
    monkeypatch.setattr(ag, "_run_tool", lambda name, keyword, cancellation=None: "")
    monkeypatch.setattr(ag, "_probe_top1_score", lambda *a, **k: None)


def _turn(app, config, text):
    nodes = []
    for mode, item in app.stream(
        {"session_id": "s", "messages": [HumanMessage(content=text)]},
        config, stream_mode=["updates", "custom"],
    ):
        if mode == "updates":
            nodes.extend(item.keys())
    return nodes, app.get_state(config).values


def test_second_turn_keeps_plain_mode_and_does_not_report(monkeypatch):
    """用户第 1 轮问"是不是隐患"，第 2 轮用省略句换一件事 → 仍然是纯回答，不出报告。

    这条正是 spec §2 里 #1 的复现路径：改之前，第 2 轮 6/10 会走 report。
    """
    _stub(monkeypatch)
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "loop-plain"}}

    _nodes1, v1 = _turn(app, config, TURN1)
    assert v1.get("dialogue_mode") == "plain", v1.get("dialogue_mode")

    nodes2, v2 = _turn(app, config, TURN2)
    assert v2.get("dialogue_mode") == "plain"
    assert v2.get("next_action") == "answer_now"
    assert v2.get("report_mode") in ("none", "", None)
    assert "search" not in nodes2 and "report" not in nodes2, nodes2
