"""C2: retrieval fans out with Send and converges through a dict reducer."""
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from core.assistant_graph import plan_retrieval, retrieve, search
from core.langgraph_state import merge_category_results


def test_merge_category_results_deep_merges_partial_branches():
    left = {"fire_equipment_fault": {"regulation": "R1"}}
    right = {"fire_equipment_fault": {"case": "C1"}}
    assert merge_category_results(left, right) == {
        "fire_equipment_fault": {"regulation": "R1", "case": "C1"}
    }


def test_merge_category_results_keeps_untouched_categories():
    left = {"road_occupancy": {"regulation": "R", "case": "C"}}
    right = {"fire_equipment_fault": {"case": "C1"}}
    merged = merge_category_results(left, right)
    assert merged["road_occupancy"] == {"regulation": "R", "case": "C"}
    assert merged["fire_equipment_fault"] == {"case": "C1"}


def test_merge_category_results_none_clears_category():
    left = {"fire_equipment_fault": {"regulation": "old", "case": "old"}}
    assert merge_category_results(left, {"fire_equipment_fault": None}) == {
        "fire_equipment_fault": {}
    }


def test_merge_category_results_handles_empty_sides():
    assert merge_category_results({}, {"a": {"case": "C"}}) == {"a": {"case": "C"}}
    assert merge_category_results({"a": {"case": "C"}}, {}) == {"a": {"case": "C"}}
    assert merge_category_results(None, None) == {}


def test_plan_retrieval_fans_out_one_send_per_tool_for_the_single_hazard():
    """一条会话只有一个活跃隐患：一个类别 × 两个工具 = 两条并行分支。"""
    state = {
        "categories": ["fire_equipment_fault"],
        "category_slots": {"fire_equipment_fault": {"facility_type": "消火栓"}},
    }
    sends = plan_retrieval(state)
    assert len(sends) == 2
    assert all(isinstance(send, Send) for send in sends)
    assert {send.node for send in sends} == {"retrieve"}
    assert sorted(send.arg["tool"] for send in sends) == [
        "search_cases", "search_regulation",
    ]
    assert {send.arg["category"] for send in sends} == {"fire_equipment_fault"}


def test_plan_retrieval_is_empty_without_categories():
    assert plan_retrieval({"categories": []}) == []


def test_retrieve_writes_only_its_own_field(monkeypatch):
    monkeypatch.setattr(
        "core.assistant_graph._run_tool", lambda name, keyword, cancellation=None: f"{name}:{keyword}"
    )
    update = retrieve({
        "category": "road_occupancy", "tool": "search_cases", "keyword": "占道",
    })
    assert update == {
        "category_results": {"road_occupancy": {"case": "search_cases:占道"}}
    }


def test_retrieve_maps_regulation_tool_to_regulation_field(monkeypatch):
    monkeypatch.setattr("core.assistant_graph._run_tool", lambda name, keyword, cancellation=None: "R")
    update = retrieve({
        "category": "road_occupancy", "tool": "search_regulation", "keyword": "占道",
    })
    assert update == {"category_results": {"road_occupancy": {"regulation": "R"}}}


def test_retrieval_branches_run_concurrently(monkeypatch):
    """4 条分支各 0.3s：串行要 1.2s，并行必须显著低于此。"""

    def slow_run_tool(name, keyword, cancellation=None):
        time.sleep(0.3)
        return f"{name}:{keyword}"

    monkeypatch.setattr("core.assistant_graph._run_tool", slow_run_tool)

    class S(TypedDict, total=False):
        categories: list
        category_slots: dict
        category_results: Annotated[dict, merge_category_results]

    graph = StateGraph(S)
    graph.add_node("search", search)
    graph.add_node("retrieve", retrieve)
    graph.add_edge(START, "search")
    graph.add_conditional_edges("search", plan_retrieval)
    graph.add_edge("retrieve", END)
    app = graph.compile()

    started = time.monotonic()
    values = app.invoke({
        "categories": ["fire_equipment_fault", "road_occupancy"],
        "category_slots": {},
    })
    elapsed = time.monotonic() - started

    assert elapsed < 0.9, f"branches appear serial: {elapsed:.2f}s"
    assert set(values["category_results"]) == {"fire_equipment_fault", "road_occupancy"}
    assert set(values["category_results"]["road_occupancy"]) == {"regulation", "case"}
    assert set(values["category_results"]["fire_equipment_fault"]) == {"regulation", "case"}


def test_search_barrier_clears_only_current_categories():
    update = search({"categories": ["road_occupancy"], "category_slots": {}})
    assert update == {"category_results": {"road_occupancy": None}}


def test_real_graph_fans_out_and_joins_into_report(monkeypatch):
    """真实图：search 扇出 2 条分支，汇聚后 report 拿到两个字段。"""
    from langchain_core.messages import HumanMessage

    import core.assistant_graph as ag

    plan = {
        "ok": True, "intent": "report_hazard", "answer": "", "question": "",
        "needs_search": True, "risk_level": "high",
        "issues": [{
            "major_code": "fire", "subcategory_code": "fire_equipment_fault",
            "slots": {"facility_type": "消火栓", "condition": "损坏"}, "missing": [],
        }],
        "categories": ["fire/fire_equipment_fault"],
        "category_slots": {"fire/fire_equipment_fault": {
            "facility_type": "消火栓", "condition": "损坏"}},
        "selected_major_code": "fire",
    }
    monkeypatch.setattr(
        ag, "_understand_plan",
        lambda messages, vision_summary="", selected_major_code="": dict(plan),
    )
    monkeypatch.setattr(ag, "_run_tool", lambda name, keyword, cancellation=None: f"{name}:{keyword}")
    monkeypatch.setattr(
        ag._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation=None: iter([("chunk", "REPORT-BODY")]),
    )

    app = ag.build_graph()
    config = {"configurable": {"thread_id": "fanout-join-1"}}
    node_runs = []
    for mode, item in app.stream(
        {"session_id": "s", "messages": [HumanMessage(content="楼下消火栓坏了")]},
        config, stream_mode=["updates", "custom"],
    ):
        if mode == "updates":
            node_runs.extend(item.keys())

    values = app.get_state(config).values
    assert node_runs.count("retrieve") == 2
    assert node_runs.index("search") < node_runs.index("report")
    results = values["category_results"]["fire_equipment_fault"]
    assert results["regulation"].startswith("search_regulation:")
    assert results["case"].startswith("search_cases:")
    # 法规与案例用同一个关键词，说明两条分支共享同一份槽位合成结果
    assert results["regulation"].split(":", 1)[1] == results["case"].split(":", 1)[1]
    assert "REPORT-BODY" in values["draft_report"]
