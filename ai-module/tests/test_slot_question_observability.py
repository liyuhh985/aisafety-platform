# -*- coding: utf-8 -*-
"""阶段 5：三级降级链的可观测性。

端到端实测（20 条输入，12 条分流）：交付问句 12/12 来自第 1 级，
第 3 级触发 0 次、且没有任何一条交付问句等于固定串 —— 所以结论是**保留**第 3 级，
把它降级成「几乎永不出现的最后一格」，换成可观测。

为什么判据不是 source == "slot_schema"：
dialogue_policy._question_for_missing 在规划器没给问句时也会退回固定串，
所以**第 2 级的文本可能就是固定串**（实测见过：「是长期还是临时？」）。
只盯 source 会漏掉这种「穿着 understand 外衣的第 3 级」。
所以真正要记的是「交付问句是否等于固定串」。
"""
import copy
import logging

import core.assistant_graph as ag

FIXED = "井盖是缺失、破损还是松动？"      # manhole_damage / defect 的 schema 固定串

STATE = {
    "messages": [],
    "locked_major": "traffic",
    "locked_subcategory": "manhole_damage",
    "category_slots": {"manhole_damage": {}},
    "missing": ["manhole_damage_defect"],
    "issues": [{"major_code": "traffic", "subcategory_code": "manhole_damage",
                "slots": {}, "missing": ["defect"]}],
    "next_action": "ask_critical_question",
    "clarification_question": "",
}


def _state(**overrides):
    state = copy.deepcopy(STATE)
    state.update(overrides)
    return state


def test_fixed_string_from_level3_is_logged_as_a_warning(monkeypatch, caplog):
    """第 1、2 级都空 → 落到 schema 固定串，必须留痕（它是「越权」的那一格）。"""
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: {})
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        cmd = ag.ask_slot_question(_state())
    assert cmd.update["question_source"] == "slot_schema"
    assert cmd.update["clarification_question"] == FIXED
    assert any("slot_question_fixed_string" in r.getMessage() for r in caplog.records)


def test_level3_warning_records_the_missing_slot(monkeypatch, caplog):
    """告警要能定位：带上 missing 槽位，便于用真实流量统计。"""
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: {})
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        ag.ask_slot_question(_state())
    hit = [r for r in caplog.records if "slot_question_fixed_string" in r.getMessage()]
    assert hit and "defect" in hit[0].getMessage()


def test_level1_does_not_trigger_the_fixed_string_warning(monkeypatch, caplog):
    """主路径（模型措辞）不该产生告警 —— 否则告警会被淹没。"""
    monkeypatch.setattr(ag, "_slot_question_llm",
                        lambda **kw: {"question": "井盖是没了，还是还盖着但已经裂了？",
                                      "target_slot": "defect"})
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        cmd = ag.ask_slot_question(_state())
    assert cmd.update["question_source"] == "ask_slot_question"
    assert not any("slot_question_fixed_string" in r.getMessage() for r in caplog.records)


def test_level2_that_equals_the_fixed_string_is_still_anomalous(monkeypatch, caplog):
    """「穿着 understand 外衣的第 3 级」：source 是 understand，但文本就是固定串。

    这是端到端实测见过的真形态（understand 问「是长期还是临时？」），
    只盯 source 会漏报，所以判据取文本。
    """
    monkeypatch.setattr(ag, "_slot_question_llm",
                        lambda **kw: {"question": "这个井盖在哪个小区？", "target_slot": "location"})
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        cmd = ag.ask_slot_question(_state(clarification_question=FIXED))
    assert cmd.update["question_source"] == "understand"
    assert cmd.update["clarification_question"] == FIXED
    assert any("slot_question_fixed_string" in r.getMessage() for r in caplog.records)


def test_level2_with_its_own_wording_is_not_anomalous(monkeypatch, caplog):
    """第 2 级的自有措辞（不等于固定串）不算异常 —— 不当告警。"""
    monkeypatch.setattr(ag, "_slot_question_llm", lambda **kw: {})
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        cmd = ag.ask_slot_question(_state(clarification_question="这个井盖是彻底没有了吗？"))
    assert cmd.update["question_source"] == "understand"
    assert not any("slot_question_fixed_string" in r.getMessage() for r in caplog.records)
