import core.assistant_graph as ag
from core.langgraph_state import AssistantState

def test_state_has_graph_state_fields():
    """C1：结构化事实随图状态跨轮保留，旧的 pending/clarify 计数器已删除。"""
    s: AssistantState = {
        "category_slots": {"fire_equipment_fault": {}},
        "category_results": {},
        "missing": ["fire_equipment_fault_facility_type"],
        "next_action": "ask_critical_question",
        "asked_question_last_turn": True,
        "offer_task": False,
        "task_offered": False,
        "task_phase": "",
        "address_text": "",
    }
    assert s["next_action"] == "ask_critical_question"
    assert s["missing"][0] == "fire_equipment_fault_facility_type"
    for gone in ("pending_categories", "relationship", "clarify_count",
                 "clarify_stopped", "active_category", "category_index"):
        assert gone not in AssistantState.__annotations__


def test_critical_flag_present():
    from core.slot_schemas import get_slot_schema

    d = {s.key: s.critical for s in get_slot_schema("falling_object")}
    assert d["source"] is True and d["target"] is False and d["exposure"] is False


def test_rebuild_missing_only_critical_and_empty():
    slots = {"消防通道": {"blocker": "杂物"}}
    miss = ag.rebuild_missing(["消防通道"], slots)
    assert "消防通道_persistence" in miss
    assert "消防通道_blocker" not in miss
    assert "消防通道_impact" not in miss

def test_understand_complete_facts_go_to_search(monkeypatch):
    """信息齐全 → understand 定 report_full；route 只负责映射到 search。"""
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "road", "subcategory_code": "road_occupancy",
            "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"},
        }],
        "categories": ["road/road_occupancy"],
        "category_slots": {"road/road_occupancy": {
            "behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [ag.HumanMessage(content="长期摆摊占着盲道，完全堵死")]})
    assert out["missing"] == []
    assert out["next_action"] == "report_full"
    assert ag.route(out).goto == "search"


def test_search_fans_out_then_merges_results(monkeypatch):
    """C2：search 只做扇出栅栏，检索由并行的 retrieve 分支完成，再经 reducer 汇聚。"""
    from core.langgraph_state import merge_category_results

    monkeypatch.setattr(ag, "_run_tool", lambda name, kw, cancellation=None: f"[{name}] {kw}")
    # 一条会话只有一个活跃隐患：一个类别 → 两条分支（法规 + 案例）
    st = {"categories": ["消防通道"],
          "category_slots": {"消防通道": {"blocker": "杂物"}},
          "messages": []}
    assert ag.search(st) == {"category_results": {"消防通道": None}}

    sends = ag.plan_retrieval(st)
    assert len(sends) == 2
    merged = {}
    for send in sends:
        update = ag.retrieve({**st, **send.arg})
        merged = merge_category_results(merged, update["category_results"])
    assert set(merged) == {"消防通道"}
    assert set(merged["消防通道"]) == {"regulation", "case"}

def test_graph_builds_with_intended_nodes():
    nodes = set(ag.build_graph().get_graph().nodes.keys())
    assert {"understand", "scope_guard", "route", "answer_reply",
            "search", "retrieve", "report"} <= nodes
    for gone in ("clarify", "meta_clarify", "route_decider"):
        assert gone not in nodes


def test_latest_user_text_only_uses_last_user_msg():
    # messages: 历史含"占道"，最新一句是"消防通道被堵" → 识别只出消防通道，不捞回占道
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    msgs = [
        SystemMessage(content="系统提示"),
        HumanMessage(content="占道长期摆摊"),
        AIMessage(content="占道是完全堵死还是部分占用？"),
        HumanMessage(content="不是占道，是消防通道被堵"),
    ]
    latest = ag._latest_user_text({"messages": msgs})
    assert latest == "不是占道，是消防通道被堵"

def test_report_writes_custom_chunks(monkeypatch):
    import core.assistant_graph as ag
    from langchain_core.messages import HumanMessage
    class FakeStream:
        def _call_llm_stream_events(self, msgs, cancellation=None):
            for t in ["## ", "占道", "被堵"]:
                yield ("chunk", t)
    sent = []
    monkeypatch.setattr("core.assistant_graph.get_stream_writer", lambda: (lambda d: sent.append(d)))
    ag._report_llm = FakeStream()
    st = {"messages": [HumanMessage(content="占道被堵")],
          "categories": ["占道"],
          "category_results": {"占道": {"regulation": "法", "case": "案例"}},
          "vision_summary": "", "category": "", "category_index": 0, "active_category": "占道"}
    up = ag.report(st)
    assert up["draft_report"] == "## 占道被堵"
    # 旧不变式「完整报告逐 token 原样流出」已作废（决策 2）：问号是句级特征，
    # 必须在流上按句判定，而项目原则是「同一个约束不要两套判定」——
    # 所以完整报告也走同一套逐句执行器，不再为它单开 token 粒度的旁路。
    # 新不变式：逐句写出（一整句一块），且拼接等于落库文本。
    assert sent == [{"chunk": "## 占道被堵"}]
    assert "".join(item["chunk"] for item in sent) == up["draft_report"]

def test_bridge_custom_chunk_from_report(monkeypatch):
    import asyncio

    class FakeStream:
        def _call_llm_stream_events(self, msgs, cancellation=None):
            for token in ["#", "报告", "正文"]:
                yield ("chunk", token)

    monkeypatch.setattr(ag, "_report_llm", FakeStream())
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "road", "subcategory_code": "road_occupancy",
            "slots": {"behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"},
        }],
        "categories": ["road/road_occupancy"],
        "category_slots": {"road/road_occupancy": {
            "behavior": "摆摊", "persistence": "长期", "blocked": "完全堵死"}},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    monkeypatch.setattr(ag, "_run_tool", lambda name, kw, cancellation=None: f"[{name}] {kw}")
    # after_report 会预抽取地址；测试不打真模型
    monkeypatch.setattr("tools.hazard_submit.extract_location", lambda history, latest: "")

    async def run():
        out = []
        async for kind, text in ag.run_stream_events(
            message="长期摆摊占着盲道，完全堵死", history=[], slots={},
            vision_summary="", session_id="t", max_rounds=3):
            out.append((kind, text))
        return out

    out = asyncio.run(run())
    chunks = [text for kind, text in out if kind == "chunk"]
    # 旧不变式「report 走 custom 流逐 token 写出」已作废（决策 2：完整报告也走逐句执行器）。
    # 新不变式：正文仍然只经 custom 流到达前端（不是整块塞进 updates），且内容完整不重复。
    assert any("正文" in c for c in chunks)
    assert "".join(chunks).count("报告正文") == 1


