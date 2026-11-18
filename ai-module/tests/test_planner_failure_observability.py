# -*- coding: utf-8 -*-
"""规划器失败要留痕：以前这条兜底路径是静默的，出问题只能靠猜。

先补可观测性（有频率再谈加重试），所以这里只断言"记了一条 warning"和"原因分得清"，
不断言任何行为变化 —— 规划器失败时的兜底行为本来就有测试不变式（不分类、不记录）。
"""
import logging

from langchain_core.messages import HumanMessage

import core.assistant_graph as ag

STATE = {"messages": [HumanMessage(content="楼下井盖破了")]}


def _run(monkeypatch, plan, caplog):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: plan)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: (lambda *a: None))
    with caplog.at_level(logging.WARNING, logger="core.assistant_graph"):
        return ag.understand(dict(STATE))


def test_a_planner_error_is_logged_as_no_plan(monkeypatch, caplog):
    out = _run(monkeypatch, {}, caplog)          # 调用抛异常时 _understand_plan 给的就是 {}
    hits = [r.getMessage() for r in caplog.records if "planner_failed" in r.getMessage()]
    assert len(hits) == 1
    assert "reason=no_plan" in hits[0]
    assert out["policy_reason"] == "planner_failed"


def test_an_unparsable_plan_is_logged_separately(monkeypatch, caplog):
    out = _run(monkeypatch, {"ok": False}, caplog)
    hits = [r.getMessage() for r in caplog.records if "planner_failed" in r.getMessage()]
    assert len(hits) == 1
    assert "reason=unparsable" in hits[0]
    assert out["policy_reason"] == "planner_failed"


def test_a_normal_plan_does_not_log_it(monkeypatch, caplog):
    _run(monkeypatch, {"ok": True, "intent": "report_hazard", "risk_level": "high",
                       "issues": [{"major_code": "municipal",
                                   "subcategory_code": "manhole_damage", "slots": {}}],
                       "categories": ["manhole_damage"],
                       "category_slots": {"manhole_damage": {}}, "question": "",
                       "answer": "", "needs_search": False, "major_mismatch": False,
                       "perceived_major": "municipal"}, caplog)
    assert not [r for r in caplog.records if "planner_failed" in r.getMessage()]
