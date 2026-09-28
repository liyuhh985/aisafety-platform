# -*- coding: utf-8 -*-
"""阶段 5a：消冗余的观测侧 + 提示词去重规则（只告警，不改写正文）。

按 A/B/C 分工，不靠「抑制某一侧」：
  A 决策级 -> 由末尾那一个追问承载；B 报告级 -> 由正文分情况判断承载、不再追问。
观测分两档：
  判得出来的（结构化字段）：问句的目标槽 key、A 类缺失是否为空、是否写了 B 类分支；
  判不出来的（正文里那句自由措辞的问句）：只告警，不硬猜。
"""
import copy
import logging

import pytest
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag

# 线上复现的那条冗余：B 类 impact 既写成分支、又被问一遍
BODY_ONLINE = (
    "消防通道被占用这个隐患，判断本身比较明确：违反《消防法》第28条。\n\n"
    "不过，是否影响消防车或人员通行这一点，会改变适用条款和处罚档次："
    "若已实际妨碍消防车通行，则适用第60条第1款第3项，责任落在占用方；"
    "若只是占用但尚未造成实际妨碍，则仍以第28条为依据，先责令改正、限期清理。\n\n"
    "最关键的一个问题：被占用的通道现在是否已经挡住消防车通行？"
)

# 阶段 4 用例 C 的形态：A 类 persistence 既写成分支、又被追问
BODY_A_EXPANDED = (
    "初步判断是占用消防通道，违反《消防法》第28条。目前还差两块信息："
    "一是占用是长期还是临时——若为长期占用，可依第60条予以处罚；"
    "若为临时占用，则以责令改正、限期清理为主。"
    "二是是否实际影响通行——若已影响，责任更重；若未妨碍，从轻。\n\n"
    "最关键的一点是：这块地方到底是长期占着还是临时放一下？"
)


def _state(**overrides):
    state = {
        "messages": [],
        "locked_major": "fire",
        "locked_subcategory": "fire_lane_blocked",
        "category_slots": {"fire_lane_blocked": {"blocker": "私家车", "persistence": "长期"}},
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {"blocker": "私家车", "persistence": "长期"},
                    "missing": [], "report_missing": ["impact"]}],
        "categories": ["fire_lane_blocked"],
        "category_results": {"fire_lane_blocked": {"regulation": "消防法第28条",
                                                   "case": "萍乡案例"}},
        "missing": [],
        "report_mode": "full",
    }
    state.update(overrides)
    return state


def _state_with_a_missing():
    return _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车"}, "missing": ["persistence"],
                 "report_missing": ["persistence", "impact"]}],
        category_slots={"fire_lane_blocked": {"blocker": "私家车"}},
        missing=["fire_lane_blocked_persistence"],
        report_mode="preliminary",
    )


def _plan(**over):
    base = {"ok": True, "intent": "report_hazard", "risk_level": "high",
            "issues": [], "categories": [], "category_slots": {},
            "question": "", "question_target": "", "answer": "", "needs_search": True}
    base.update(over)
    return base


# ---------------------------------------------------------------- 1. 问句识别（严口径）

def test_question_sentences_ignores_advice_with_interrogative_words():
    """建议句里出现「什么时候」不算问句 —— 实测第一版就是这么误报的。"""
    assert ag.question_sentences("建议向现场人员问清占用从什么时候开始的，并拍照留证。") == []
    assert ag.question_sentences("不管怎么样都要先清理通道。") == []


def test_question_sentences_counts_question_marks_and_ma_ne_endings():
    assert len(ag.question_sentences("通道被占用了。能说说堆了多久吗？")) == 1
    # 多余问号被 question_limiter 去掉之后的残留形态也要认出来
    assert len(ag.question_sentences("通道被占了。这块地方是谁在管呢")) == 1
    assert ag.question_sentences("通道被占了，请尽快清理。") == []


# ---------------------------------------------------------------- 2. 冗余重叠检测

def test_online_repro_b_class_branch_and_question_is_flagged():
    """线上复现那条：B 类缺失写成分支，正文又问一遍。"""
    reasons = ag.redundancy_reasons(_state(), BODY_ONLINE)
    assert "question_without_decision_missing" in reasons
    assert "b_class_also_branched" in reasons


def test_a_class_followup_alone_is_not_redundant():
    """A 类缺失 + 只问、不展开成分支 —— 这是正确形态，不许误报。"""
    body = "初步判断是占用消防通道，违反第28条。目前仍需确认这处占用是长期还是临时，能说说吗？"
    assert ag.redundancy_reasons(_state_with_a_missing(), body) == []


def test_expanding_an_a_class_slot_beside_its_followup_is_flagged():
    """A 类缺失既写成分支、又被追问 —— 该由追问承载的那一项被承载了两次。"""
    reasons = ag.redundancy_reasons(_state_with_a_missing(), BODY_A_EXPANDED)
    assert "a_slot_expanded_beside_followup:persistence" in reasons
    # B 类那一项没被问，不该在这里出现
    assert not [r for r in reasons if r.startswith("b_slot_question_overlap")]


def test_branch_only_report_is_clean():
    """只写分支、一个问句都没有 —— 标准形态，不许误报。"""
    body = "若为长期占用，适用第28条并可处罚；若为临时占用，则以责令改正为主。"
    assert ag.redundancy_reasons(_state(), body) == []
    assert ag.redundancy_reasons(_state_with_a_missing(), body) == []


def test_two_questions_beside_a_followup_are_flagged():
    """A 类缺失本该只有末尾那一个追问，正文却出现两个问句。"""
    body = ("初步判断是占用消防通道。仍需确认是长期还是临时，能说说吗？"
            "另外，是否影响消防车通行，你能量一下净宽吗？")
    reasons = ag.redundancy_reasons(_state_with_a_missing(), body)
    assert "extra_question_beside_followup" in reasons


def test_overlap_heuristic_needs_enough_shared_text():
    assert ag.slot_question_overlap("是否影响消防车或人员通行？", "是否影响消防车或人员通行？")
    assert not ag.slot_question_overlap("这块地方是谁在管呢", "是否影响消防车或人员通行？")
    assert not ag.slot_question_overlap("", "是否影响消防车或人员通行？")


def test_legacy_state_without_issues_does_not_claim_no_decision_missing():
    """只给了 categories 的旧形状：A 类缺失要看 state["missing"]，不能当成空。"""
    legacy = {"categories": ["fire_lane_blocked"],
              "missing": ["fire_lane_blocked_persistence"]}
    reasons = ag.redundancy_reasons(legacy, "初步判断是占用消防通道。这块地方是谁在管呢？")
    assert "question_without_decision_missing" not in reasons
    assert "b_class_also_branched" not in reasons


def test_warning_is_emitted_for_the_redundant_body(caplog):
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        ag._warn_redundancy(_state(), BODY_ONLINE)
    hit = [r for r in caplog.records if "report_question_redundancy" in r.getMessage()]
    assert hit and "b_class_also_branched" in hit[0].getMessage()


def test_no_warning_for_a_clean_body(caplog):
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        ag._warn_redundancy(_state(), "若为长期占用，适用第28条；若为临时，责令改正。")
    assert not [r for r in caplog.records if "report_question_redundancy" in r.getMessage()]


# ---------------------------------------------------------------- 3. report 节点集成

def _run_report(monkeypatch, state, reply):
    """跑 report 节点（不经图），返回 (状态更新, 流出的 chunk, 请求里的材料+规则)。"""
    sent = []
    captured = {}

    def fake_stream(messages, cancellation=None):
        captured["prompt"] = messages[-1]["content"]
        yield ("chunk", reply)

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", staticmethod(fake_stream))
    monkeypatch.setattr(ag, "get_stream_writer", lambda: sent.append)
    update = ag.report(state)
    return update, sent, captured["prompt"]


def test_report_node_warns_when_the_body_is_redundant(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        update, sent, _prompt = _run_report(monkeypatch, _state(), BODY_ONLINE)
    assert "".join(item["chunk"] for item in sent) == update["draft_report"]
    assert [r for r in caplog.records if "report_question_redundancy" in r.getMessage()]


def test_preliminary_report_path_also_warns(monkeypatch, caplog):
    """两个档位都要接上观测 —— 初步档漏接是最容易发生的那种漏（变异测试抓到过）。"""
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        _run_report(monkeypatch, _state_with_a_missing(), BODY_A_EXPANDED)
    assert [r for r in caplog.records if "report_question_redundancy" in r.getMessage()]


def test_report_node_stays_quiet_when_the_body_is_clean(monkeypatch, caplog):
    body = "若为长期占用，适用第28条并可处罚；若为临时占用，以责令改正为主。"
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        _run_report(monkeypatch, _state(), body)
    assert not [r for r in caplog.records if "report_question_redundancy" in r.getMessage()]


def test_dedup_rule_is_a_relationship_not_a_prohibition_list(monkeypatch):
    """提示词只描述「同一条信息不要承载两次」，不列「不许展开」这类禁止词。"""
    _update, _sent, prompt = _run_report(monkeypatch, _state_with_a_missing(), "正文。")
    assert "同一条缺失信息不要承载两次" in prompt
    assert "[法规适用待确认]" in prompt and "[仍缺信息]" in prompt     # 两条材料行都在
    for banned in ("不要展开", "不许", "禁止提到"):
        assert banned not in prompt, banned


def test_dedup_rule_does_not_quote_the_material_labels_with_brackets():
    """去重规则只提「材料里标着…的那一项」，不照抄带方括号的标签。

    为什么这条要单独钉：照抄 `[仍缺信息]` 会让「A 类已齐时材料里不该出现那一行」
    这类断言被规则文案本身触发（实测踩过），而断言本身是对的、不该改。
    """
    rule = ag.REPORT_DEDUP_RULE
    assert "同一条缺失信息不要承载两次" in rule
    assert "法规适用待确认" in rule and "仍缺信息" in rule
    assert "[仍缺信息]" not in rule and "[法规适用待确认]" not in rule


def test_dedup_rule_is_injected_only_when_something_can_be_duplicated(monkeypatch):
    """既没有 B 类分支、也没有 A 类缺失时，不谈去重 —— 否则模型会以为还有信息没确认。"""
    state = _state(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车", "persistence": "长期", "impact": "影响通行"},
                 "missing": [], "report_missing": []}],
    )
    _update, _sent, prompt = _run_report(monkeypatch, state, "正文。")
    assert "同一条缺失信息不要承载两次" not in prompt


def test_material_marks_the_a_row_as_carried_by_the_followup(monkeypatch):
    _update, _sent, prompt = _run_report(monkeypatch, _state_with_a_missing(), "正文。")
    line = [ln for ln in prompt.splitlines() if ln.startswith("[仍缺信息]")]
    assert line and "由本轮末尾的那一个追问承载" in line[0]


# ---------------------------------------------------------------- 4. 问句指向核对

def test_question_target_audit_accepts_a_target_inside_the_decision_missing():
    out = ag.question_target_audit(question="这块地方是谁在管呢", target_slot="persistence",
                                   missing_keys=["persistence"], origin="understand",
                                   code="fire_lane_blocked")
    assert out == {"judged": True, "ok": True, "reason": "ok", "target": "persistence"}


def test_question_target_audit_flags_a_target_outside_the_decision_missing(caplog):
    """G1 记录的「问位置」形态：自报的目标槽根本不在 A 类缺失里。"""
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        out = ag.question_target_audit(question="这个井盖大概在哪个路段？",
                                       target_slot="location",
                                       missing_keys=["defect"], origin="ask_slot_question",
                                       code="manhole_damage")
    assert out["judged"] is True and out["ok"] is False
    assert out["reason"] == "target_mismatch"
    hit = [r for r in caplog.records if "question_target_mismatch" in r.getMessage()]
    assert hit and "location" in hit[0].getMessage()


def test_question_target_audit_warns_when_it_cannot_tell(caplog):
    """判不出来就告警、不硬猜（老规划器 / 模型漏填 question_target）。"""
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        out = ag.question_target_audit(question="这块地方是谁在管呢", target_slot="",
                                       missing_keys=["persistence"], origin="understand",
                                       code="fire_lane_blocked")
    assert out["judged"] is False and out["reason"] == "target_unknown"
    assert [r for r in caplog.records if "question_target_unknown" in r.getMessage()]


def test_question_target_audit_is_silent_without_a_question_or_without_missing(caplog):
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        assert ag.question_target_audit(question="", target_slot="", missing_keys=["persistence"],
                                        origin="understand")["reason"] == "no_question"
        assert ag.question_target_audit(question="这块地方是谁在管呢", target_slot="persistence",
                                        missing_keys=[], origin="understand")["reason"] == "no_missing"
    assert not [r for r in caplog.records if "question_target_" in r.getMessage()]


def test_schema_slot_of_text_attributes_a_fixed_string_to_its_slot():
    fixed = ag.schema_question_for_missing(["persistence"], "fire_lane_blocked")
    assert ag._schema_slot_of_text(fixed, ["persistence"], "fire_lane_blocked") == "persistence"
    assert ag._schema_slot_of_text("这块地方是谁在管呢", ["persistence"], "fire_lane_blocked") == ""


def test_slot_question_node_audits_the_delivered_question(monkeypatch, caplog):
    """第 1 级自报正确 → 无 target 告警。"""
    monkeypatch.setattr(ag, "_slot_question_llm",
                        lambda **kw: {"question": "这块地方是谁在管呢", "target_slot": "persistence"})
    state = _state_with_a_missing()
    state.update({"next_action": "ask_critical_question", "clarification_question": ""})
    state.pop("report_mode", None)
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        cmd = ag.ask_slot_question(state)
    assert cmd.update["question_source"] == "ask_slot_question"
    assert not [r for r in caplog.records if "question_target_" in r.getMessage()]


def test_slot_question_node_warns_when_it_cannot_attribute(monkeypatch, caplog):
    """模型没给问句、understand 给的是自有措辞、规划器也没自报目标 → 判不出来 → 告警。"""
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: {})
    state = _state_with_a_missing()
    state.update({"next_action": "ask_critical_question",
                  "clarification_question": "这块地方是谁在管呢",
                  "dialogue_plan": {"question_target": ""}})
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        cmd = ag.ask_slot_question(state)
    assert cmd.update["question_source"] == "understand"
    assert [r for r in caplog.records if "question_target_unknown" in r.getMessage()]


def test_slot_question_node_uses_the_planner_target_for_level_two(monkeypatch, caplog):
    """第 2 级交付的是规划器的自有措辞 → 用规划器自报的 question_target 判。"""
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: {})
    state = _state_with_a_missing()
    state.update({"next_action": "ask_critical_question",
                  "clarification_question": "这个占用大概在哪个路段？",
                  "dialogue_plan": {"question_target": "location"}})
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        ag.ask_slot_question(state)
    assert [r for r in caplog.records if "question_target_mismatch" in r.getMessage()]


def test_understand_defers_the_audit_to_the_node(monkeypatch, caplog):
    """本轮要进 ask_slot_question 时，understand 不自己审 —— 否则同一个问题被报两次。"""
    plan = _plan(
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "私家车"}, "confidence": 0.9}],
        categories=["fire_lane_blocked"],
        category_slots={"fire_lane_blocked": {"blocker": "私家车"}},
        question="这个占用大概在哪个路段？", question_target="location",
    )
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        out = ag.understand({"messages": [HumanMessage(content="消防通道被私家车占了")]})
    assert out["missing"] == ["fire_lane_blocked_persistence"]
    assert out["clarification_question"] == "这个占用大概在哪个路段？"
    # understand 侧静默：交付那一句由节点审
    assert not [r for r in caplog.records if "question_target_" in r.getMessage()]


def test_understand_does_not_flag_the_in_major_enum_question(monkeypatch, caplog):
    """类内枚举问句发生在 missing 必然为空的时候 —— 不能误报成「没有该问的题材」。"""
    plan = _plan(intent="quick_assessment", answer="", question="")
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    state = {"messages": [HumanMessage(content="楼下消防设施有点问题")],
             "locked_major": "fire", "locked_subcategory": ""}
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        out = ag.understand(state)
    assert out["next_action"] == "ask_critical_question"
    assert out["clarification_question"]
    assert not [r for r in caplog.records if "question_target_" in r.getMessage()]


# ---------------------------------------------------------------- 5. 契约

def test_parse_plan_carries_question_target_and_drops_it_without_a_question():
    from core.dialogue_understanding import parse_plan
    parsed = parse_plan(
        "{\"intent\":\"report_hazard\",\"question\":\"这块地方是谁在管呢？\","
        "\"question_target\":\"persistence\",\"answer\":\"\"}")
    assert parsed["question_target"] == "persistence"
    parsed = parse_plan(
        "{\"intent\":\"report_hazard\",\"question\":\"\","
        "\"question_target\":\"persistence\",\"answer\":\"\"}")
    assert parsed["question_target"] == ""


def test_planner_prompt_mentions_question_target():
    from core.dialogue_understanding import build_planner_messages
    messages = build_planner_messages([HumanMessage(content="消防通道被占了")])
    prompt = messages[0]["content"]
    assert "question_target" in prompt
