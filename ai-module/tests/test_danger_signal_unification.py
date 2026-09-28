"""danger_veto 必须吸收 planner 的 scope=emergency。

原因：删掉 direct_reply 的 emergency_reply 分支后，「危险词表没命中 + immediate_danger 没给 +
planner 只说 scope=emergency」这条输入会走到 plan.ok，而 danger_veto=False 就不会前置任何指引
-> 危险输入一句指引都没有。所以三个信号必须先归一到同一个 danger_veto。
"""
from langchain_core.messages import HumanMessage

from core.uncertainty import assess

DANGER_TEXT = "\u697c\u9053\u91cc\u5168\u662f\u6d53\u70df"
NEUTRAL_TEXT = "\u697c\u9053\u91cc\u5806\u4e86\u5f88\u591a\u7eb8\u7bb1"


def _messages(text):
    return [HumanMessage(content=text)]


def _plan(**overrides):
    plan = {"issues": [], "immediate_danger": False}
    plan.update(overrides)
    return plan


def test_planner_emergency_scope_alone_sets_danger_veto():
    verdict = assess(_plan(scope="emergency"), _messages(NEUTRAL_TEXT))
    assert verdict["danger_veto"] is True


def test_model_immediate_danger_sets_veto():
    verdict = assess(_plan(scope="hazard", immediate_danger=True), _messages(NEUTRAL_TEXT))
    assert verdict["danger_veto"] is True


def test_danger_word_list_sets_veto():
    verdict = assess(_plan(scope="hazard"), _messages(DANGER_TEXT))
    assert verdict["danger_veto"] is True


def test_no_signal_means_no_veto():
    verdict = assess(_plan(scope="hazard"), _messages(NEUTRAL_TEXT))
    assert verdict["danger_veto"] is False


def test_out_of_scope_does_not_trigger_veto():
    verdict = assess(_plan(scope="out_of_scope"), _messages(NEUTRAL_TEXT))
    assert verdict["danger_veto"] is False


def test_emergency_scope_is_recorded_in_signals():
    verdict = assess(_plan(scope="emergency"), _messages(NEUTRAL_TEXT))
    joined = " ".join(verdict["uncertainty_signals"])
    assert "emergency" in joined


def test_scope_guard_short_circuits_on_planner_emergency():
    """归一之后，scope_guard 必须把这条输入也当作 emergency（不再依赖 scope_policy 的兜底）。"""
    from core import assistant_graph as ag

    verdict = assess(_plan(scope="emergency"), _messages(NEUTRAL_TEXT))
    decision = ag.scope_guard({**_plan(scope="emergency"), **verdict,
                               "messages": _messages(NEUTRAL_TEXT)})
    assert decision.get("scope") == "emergency"
