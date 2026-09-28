"""C1：结构化事实随图状态跨轮保留；图状态不再每轮被清空重抽。"""
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from core.assistant_graph import build_turn_input, seed_messages
from core.langgraph_state import MAX_THREAD_MESSAGES, append_messages


def test_append_messages_caps_the_thread():
    existing = [HumanMessage(content=f"m{i}") for i in range(MAX_THREAD_MESSAGES + 10)]
    result = append_messages(existing, [HumanMessage(content="new")])
    assert len(result) == MAX_THREAD_MESSAGES
    assert result[-1].content == "new"


def test_append_messages_handles_empty_sides():
    assert append_messages([], [HumanMessage(content="a")])[0].content == "a"
    assert append_messages([HumanMessage(content="a")], [])[0].content == "a"
    assert append_messages(None, None) == []


def test_build_turn_input_carries_only_the_new_turn():
    payload = build_turn_input("s1", "楼下消防栓坏了", "", "fire")
    assert set(payload) == {"session_id", "messages", "vision_summary", "selected_major_code"}
    assert len(payload["messages"]) == 1
    assert payload["messages"][0].content == "楼下消防栓坏了"
    for wiped in ("categories", "category_slots", "missing", "issues", "dialogue_plan"):
        assert wiped not in payload


def test_seed_messages_maps_roles():
    seeded = seed_messages([
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
        {"role": "system", "content": "s"},
    ])
    assert [type(m).__name__ for m in seeded] == [
        "HumanMessage", "AIMessage", "SystemMessage",
    ]
    assert [m.content for m in seeded] == ["u", "a", "s"]


def test_seed_messages_skips_unknown_roles():
    assert seed_messages([{"role": "tool", "content": "x"}]) == []


def test_structured_state_survives_a_second_turn_with_real_reducers():
    """G1 回归：第二轮不再传空 categories，结构化事实必须活下来。"""

    class S(TypedDict, total=False):
        messages: Annotated[list, append_messages]
        issues: list
        categories: list

    def first(state):
        return {"issues": [{"subcategory_code": "fire_equipment_fault"}],
                "categories": ["fire_equipment_fault"]}

    def second(state):
        return {}

    graph = StateGraph(S)
    graph.add_node("first", first)
    graph.add_node("second", second)
    graph.add_edge(START, "first")
    graph.add_edge("first", "second")
    graph.add_edge("second", END)
    app = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "persist-1"}}

    app.invoke(build_turn_input("persist-1", "u1", "", ""), config)
    app.invoke(build_turn_input("persist-1", "u2", "", ""), config)

    values = app.get_state(config).values
    assert [m.content for m in values["messages"]] == ["u1", "u2"]
    assert values["issues"] == [{"subcategory_code": "fire_equipment_fault"}]
    assert values["categories"] == ["fire_equipment_fault"]


def test_begin_turn_resets_only_per_turn_flags():
    from core.assistant_graph import begin_turn

    update = begin_turn({"task_offered": True, "asked_question_last_turn": True,
                         "issues": [{"subcategory_code": "x"}]})
    assert update == {"task_offered": False, "asked_question_last_turn": False}
    # guidance_emitted 故意不复位：它是"这次危险事件已提醒过"，由 understand 收尾
    assert "guidance_emitted" not in update


def test_graph_entry_is_begin_turn():
    import core.assistant_graph as ag

    nodes = set(ag.build_graph().get_graph().nodes.keys())
    assert "begin_turn" in nodes
