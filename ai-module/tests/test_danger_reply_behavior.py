"""危险输入的行为不变式：有指引、不追问、不被越界拒绝。

这几条在删掉 emergency_reply 分支后必须仍然成立 —— 它们由 dialogue_policy 与
prepend_guidance 保证，而不是由那条被删的分支保证。
"""
from langchain_core.messages import HumanMessage

from core import assistant_graph as ag

DANGER = "\u697c\u9053\u91cc\u5168\u662f\u6d53\u70df\uff0c\u4eba\u90fd\u51fa\u4e0d\u6765"
QUESTION_ACTIONS = {"ask_critical_question", "answer_with_optional_question"}


def _plan(**overrides):
    plan = {
        "ok": True,
        "scope": "emergency",
        "intent": "new",
        "answer": "\u8bf7\u7acb\u5373\u64a4\u79bb\u5230\u5ba4\u5916\u5b89\u5168\u5904\u3002",
        "question": "",
        "issues": [],
        "immediate_danger": False,
        "premises_scope": "public",
    }
    plan.update(overrides)
    return plan


def _state(monkeypatch, plan):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: plan)
    return ag.understand({"messages": [HumanMessage(content=DANGER)]})


def test_danger_never_asks_a_question(monkeypatch):
    out = _state(monkeypatch, _plan())
    assert out["danger_veto"] is True
    assert out["next_action"] not in QUESTION_ACTIONS
    assert out["question"] if "question" in out else True


def test_danger_marks_guidance_emitted(monkeypatch):
    out = _state(monkeypatch, _plan())
    assert out["guidance_emitted"] is True
    assert out["clarification_question"] == ""


def test_planner_emergency_is_not_downgraded_to_out_of_scope(monkeypatch):
    out = _state(monkeypatch, _plan())
    decision = ag.scope_guard({**out, "messages": [HumanMessage(content=DANGER)]})
    assert decision.get("scope") == "emergency"


def test_danger_word_alone_is_enough(monkeypatch):
    out = _state(monkeypatch, _plan(scope="hazard", answer="\u5efa\u8bae\u5148\u907f\u5f00\u3002"))
    assert out["danger_veto"] is True
    assert out["next_action"] not in QUESTION_ACTIONS


def test_neutral_input_is_not_treated_as_danger(monkeypatch):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _plan(scope="hazard"))
    out = ag.understand({"messages": [HumanMessage(content="\u697c\u9053\u91cc\u5806\u4e86\u5f88\u591a\u7eb8\u7bb1")]})
    assert out["danger_veto"] is False
    assert out["guidance_emitted"] is False
