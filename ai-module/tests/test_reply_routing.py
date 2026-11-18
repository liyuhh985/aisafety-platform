"""回复分发：route 由二值映射变成多出口，这里锁住分发优先级与节点行为。

优先级必须与重构前 direct_reply 的分支顺序逐条一致：
边界模板（direct_mode）> 模型回答（plan.ok）> 寒暄（smalltalk）> 兜底。
"""
from langchain_core.messages import HumanMessage

from core import assistant_graph as ag
from core.scope_policy import AMBIGUOUS_RESPONSE, OUT_OF_SCOPE_RESPONSE

REPLY_NODES = ("boundary_reply", "smalltalk_reply", "answer_reply", "fallback_reply")


def _state(**overrides):
    state = {"messages": [HumanMessage(content="\u697c\u9053\u91cc\u5806\u4e86\u7eb8\u7bb1")]}
    state.update(overrides)
    return state


# ---------- 分发优先级 ----------

def test_boundary_mode_wins_over_model_answer():
    dest = ag._reply_destination(_state(direct_mode="out_of_scope",
                                        dialogue_plan={"ok": True, "answer": "x"}))
    assert dest == "boundary_reply"


def test_anchor_domain_also_routes_to_boundary():
    assert ag._reply_destination(_state(direct_mode="anchor_domain")) == "boundary_reply"


def test_model_answer_used_when_no_direct_mode():
    dest = ag._reply_destination(_state(direct_mode="", dialogue_plan={"ok": True}))
    assert dest == "answer_reply"


def test_smalltalk_only_when_no_model_answer():
    assert ag._reply_destination(_state(direct_mode="smalltalk", dialogue_plan={})) == "smalltalk_reply"
    # 模型已经给了回答时，寒暄模板不该抢走
    assert ag._reply_destination(
        _state(direct_mode="smalltalk", dialogue_plan={"ok": True})) == "answer_reply"


def test_fallback_is_last_resort():
    assert ag._reply_destination(_state(direct_mode="", dialogue_plan={})) == "fallback_reply"


# ---------- route 出口 ----------

def test_route_sends_report_actions_to_search():
    assert ag.route(_state(next_action="report_full")).goto == "search"
    assert ag.route(_state(next_action="report_preliminary")).goto == "search"


def test_route_sends_plain_answers_to_reply_nodes():
    assert ag.route(_state(next_action="answer_now",
                           direct_mode="", dialogue_plan={"ok": True})).goto == "answer_reply"
    assert ag.route(_state(next_action="answer_now",
                           direct_mode="smalltalk")).goto == "smalltalk_reply"


# ---------- 节点行为 ----------

def test_boundary_reply_prefers_scope_response():
    out = ag.boundary_reply(_state(direct_mode="out_of_scope", scope_response="\u8d8a\u754c\u4e86"))
    assert out["messages"][-1].content == "\u8d8a\u754c\u4e86"


def test_boundary_reply_falls_back_to_templates():
    assert ag.boundary_reply(_state(direct_mode="out_of_scope"))["messages"][-1].content \
        == OUT_OF_SCOPE_RESPONSE
    assert ag.boundary_reply(_state(direct_mode="anchor_domain"))["messages"][-1].content \
        == AMBIGUOUS_RESPONSE


def test_smalltalk_reply_templates():
    assert "不客气" in ag.smalltalk_reply(
        _state(messages=[HumanMessage(content="\u8c22\u8c22")]))["messages"][-1].content
    assert ag.smalltalk_reply(
        _state(messages=[HumanMessage(content="\u5728\u5417")]))["messages"][-1].content == "\u5728\u7684\uff0c\u4f60\u8bf4\u8bf4\u770b\u3002"


def test_answer_reply_joins_answer_and_question():
    out = ag.answer_reply(_state(
        direct_mode="", next_action="ask_critical_question",
        clarification_question="\u5177\u4f53\u662f\u54ea\u4e00\u7c7b\uff1f",
        dialogue_plan={"ok": True, "answer": "\u5c5e\u4e8e\u8f83\u9ad8\u98ce\u9669\u3002"},
    ))
    content = out["messages"][-1].content
    assert "\u5c5e\u4e8e\u8f83\u9ad8\u98ce\u9669\u3002" in content
    assert "\u5177\u4f53\u662f\u54ea\u4e00\u7c7b\uff1f" in content


def test_answer_reply_hides_question_for_non_question_actions():
    out = ag.answer_reply(_state(
        direct_mode="", next_action="answer_now",
        clarification_question="\u4e0d\u8be5\u95ee\u7684\u95ee\u9898",
        dialogue_plan={"ok": True, "answer": "\u7b54\u6848"},
    ))
    assert "\u4e0d\u8be5\u95ee\u7684\u95ee\u9898" not in out["messages"][-1].content


def test_answer_reply_never_empty():
    out = ag.answer_reply(_state(direct_mode="", next_action="answer_now",
                                 dialogue_plan={"ok": True, "answer": ""}))
    assert out["messages"][-1].content.strip()


# ---------- 图接线 ----------

def test_graph_wires_four_reply_nodes_to_end():
    g = ag.build_graph()
    nodes = set(g.get_graph().nodes)
    for name in REPLY_NODES:
        assert name in nodes, name
    assert "direct_reply" not in nodes
    edges = {(e.source, e.target) for e in g.get_graph().edges}
    for name in REPLY_NODES:
        assert (name, "__end__") in edges, name
