from core.langgraph_state import AssistantState

def test_state_has_multi_hazard_fields():
    s: AssistantState = {
        "categories": ["消防通道", "占道"],
        "active_category": "消防通道",
        "category_index": 0,
        "category_slots": {"消防通道": {}, "占道": {}},
        "category_results": {},
        "missing": ["消防通道_blocker", "占道_blocked"],
        "relationship": "add",
        "clarify_count": 0,
        "clarify_stopped": False,
    }
    assert s["categories"][0] == "消防通道"
    assert s["missing"][0] == "消防通道_blocker"
import core.assistant_graph as ag

def test_infer_categories_two_hits_no_llm(monkeypatch):
    monkeypatch.setattr(ag, "_llm_classify", lambda t: (_ for _ in ()).throw(AssertionError("双命中不该调 LLM")))
    cats = ag._infer_categories("消防被堵，长期占道")
    assert "消防通道" in cats and "占道" in cats
    assert cats.index("消防通道") < cats.index("占道")

def test_merge_categories_dedupe_and_sort():
    merged = ag._merge_categories(["占道", "消防通道"], ["占道", "危房"])
    assert merged[0] == "危房"
    assert merged.count("占道") == 1
    assert merged[-1] == "占道"

def test_critical_flag_present():
    slots = ag.SLOT_SCHEMAS["高空坠物"]
    d = {s.key: s.critical for s in slots}
    assert d["source"] is True and d["target"] is False and d["exposure"] is False

def test_rebuild_missing_only_critical_and_empty():
    slots = {"消防通道": {"blocker": "杂物"}}
    miss = ag.rebuild_missing(["消防通道"], slots)
    assert "消防通道_persistence" in miss
    assert "消防通道_blocker" not in miss
    assert "消防通道_impact" not in miss

def test_add_category_slots_merges_per_cat():
    state_cats = ["消防通道", "占道"]
    cs = {"消防通道": {}, "占道": {}}
    extracted = {"消防通道": {"impact": "影响通行"}, "占道": {"persistence": "长期"}}
    out = ag.add_category_slots(state_cats, cs, extracted)
    assert out["消防通道"]["impact"] == "影响通行"
    assert out["占道"]["persistence"] == "长期"

def test_relocate_registers_cat_not_transfer():
    # 简化版：只登记"串台"到的类别，不转发填槽、不删源
    cats = ["占道"]
    cs = {"占道": {"blocked": "消防通道被堵"}}
    out = ag._relocate("消防通道被堵", "占道", "blocked", cats, cs)
    assert "消防通道" in out["categories"]     # 登记了新类别
    assert out["category_slots"]["占道"]["blocked"] == "消防通道被堵"  # 源没删
    assert "impact" not in out["category_slots"].get("消防通道", {})  # 没转发填槽

def test_route_multi_hazard_extract_and_rebuild(monkeypatch):
    monkeypatch.setattr(ag, "_infer_categories", lambda t, v="": ["消防通道", "占道"])
    monkeypatch.setattr(ag, "_llm_extract_slots",
        lambda msg, cats, keys: {"消防通道": {"impact": "影响通行"}, "占道": {"persistence": "长期"}})
    st = {"messages": [ag.HumanMessage(content="消防被堵，长期占道")],
          "categories": ["消防通道", "占道"],
          "active_category": "消防通道", "category_index": 0,
          "category_slots": {"消防通道": {}, "占道": {}},
          "missing": ["消防通道_blocker", "消防通道_persistence", "占道_blocked"],
          "clarify_count": 0, "clarify_stopped": False, "vision_summary": ""}
    up = ag.route(st)
    assert up["category_slots"]["占道"]["persistence"] == "长期"
    assert "占道_persistence" not in up["missing"]
    assert "占道_blocked" in up["missing"]

def test_route_can_search_when_missing_empty(monkeypatch):
    monkeypatch.setattr(ag, "_infer_categories", lambda t, v="": ["占道"])
    monkeypatch.setattr(ag, "_llm_extract_slots",
        lambda msg, cats, keys: {"占道": {"behavior": "占道", "persistence": "长期", "blocked": "完全堵死"}})
    st = {"messages": [ag.HumanMessage(content="长期占着盲道完全堵死")],
          "categories": ["占道"], "active_category": "占道", "category_index": 0,
          "category_slots": {}, "missing": ["占道_behavior","占道_persistence","占道_blocked"],
          "clarify_count": 0, "clarify_stopped": False, "vision_summary": ""}
    up = ag.route(st)
    assert up["missing"] == []
    assert up["route_decision"] == "search"

def test_route_can_search_at_limit(monkeypatch):
    monkeypatch.setattr(ag, "_infer_categories", lambda t, v="": ["占道"])
    monkeypatch.setattr(ag, "_llm_extract_slots", lambda msg, cats, keys: {})
    st = {"messages": [ag.HumanMessage(content="占道")], "categories": ["占道"],
          "active_category": "占道", "category_index": 0, "category_slots": {},
          "missing": ["占道_behavior"], "clarify_count": 3, "clarify_stopped": False,
          "vision_summary": ""}
    up = ag.route(st)
    assert up["route_decision"] == "search"

def test_clarify_chooses_top_slots_and_phrases(monkeypatch):
    monkeypatch.setattr(ag, "_llm_phrase", lambda slots, ctx: "消防通道是被什么东西堵的？")
    st = {"messages": [ag.HumanMessage(content="消防被堵")],
          "missing": ["消防通道_blocker", "消防通道_persistence", "占道_blocked"],
          "categories": ["消防通道", "占道"], "active_category": "消防通道",
          "category_index": 0, "category_slots": {"消防通道": {}, "占道": {}},
          "relationship": "", "clarify_count": 1, "clarify_stopped": False}
    up = ag.clarify(st)
    assert up["messages"][-1].content == "消防通道是被什么东西堵的？"
    assert up["relationship"] == ""

def test_meta_clarify_add(monkeypatch):
    monkeypatch.setattr(ag, "_llm_phrase", lambda slots, ctx: "这些是同一个地方的问题，还是另外单独一条？")
    st = {"messages": [ag.HumanMessage(content="那消防被堵呢")],
          "missing": ["消防通道_blocker"], "categories": ["占道"],
          "active_category": "占道", "category_index": 0,
          "category_slots": {}, "relationship": "", "clarify_count": 0, "clarify_stopped": False}
    up = ag.meta_clarify(st)
    assert up["messages"][-1].content == "这些是同一个地方的问题，还是另外单独一条？"

def test_search_loops_categories(monkeypatch):
    monkeypatch.setattr(ag, "_run_tool", lambda name, kw: f"[{name}] {kw}")
    st = {"categories": ["消防通道", "占道"], "category_index": 1,
          "category_slots": {"消防通道": {"blocker": "杂物"}, "占道": {"blocked": "完全堵死"}},
          "category_results": {}, "messages": []}
    up = ag.search(st)
    assert set(up["category_results"].keys()) == {"消防通道", "占道"}
    assert "完全堵死" in up["category_results"]["占道"]["case"]

def test_graph_builds_with_meta_clarify():
    g = ag.build_graph()
    nodes = set(g.get_graph().nodes.keys())
    assert "meta_clarify" in nodes
    assert {"route", "clarify", "search", "report"} <= nodes

def test_infer_categories_merges_vision_and_text(monkeypatch):
    # 图判占道经营 -> 占道；文本提到消防 -> 占道 + 消防通道 两个都保留（不再图覆盖文）
    monkeypatch.setattr(ag, "_llm_classify", lambda t: (_ for _ in ()).throw(AssertionError("有命中不该调 LLM")))
    cats = ag._infer_categories("旁边的消防通道也被堵了", vision_category="占道经营")
    assert "占道" in cats and "消防通道" in cats
    # 优先级：消防(1) < 占道(5)，消防应排前
    assert cats.index("消防通道") < cats.index("占道")

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

def test_find_negated_zhandao():
    # "不是占道" → 找出被否定的类别 ["占道"]
    assert ag._find_negated("不是占道，是消防通道被堵") == ["占道"]

def test_find_negated_returns_empty_when_no_negation():
    assert ag._find_negated("消防通道被杂物堵死") == []

def test_route_negation_removes_old_category(monkeypatch):
    # 旧状态有占道+消防，用户说"不是占道，是消防通道" → 只留消防
    monkeypatch.setattr(ag, "_llm_extract_slots", lambda msg, cats, keys: {"消防通道": {"blocker": "杂物"}})
    st = {"messages": [ag.HumanMessage(content="不是占道，是消防通道被堵")],
          "categories": ["占道", "消防通道"],
          "active_category": "占道", "category_index": 0,
          "category_slots": {"占道": {"behavior": "摆摊"}, "消防通道": {}},
          "category_results": {}, "missing": ["占道_blocked"],
          "relationship": "", "clarify_count": 0, "clarify_stopped": False,
          "vision_summary": ""}
    up = ag.route(st)
    assert up["categories"] == ["消防通道"]      # 占道被删
    assert "占道" not in up["category_slots"]     # 占道的槽也被清

def test_route_fresh_category_sets_pending(monkeypatch):
    # 跨轮首次发现新类别：只登记待定，本轮不并入
    monkeypatch.setattr(ag, "_llm_extract_slots", lambda msg, cats, keys: {})
    st = {"messages": [ag.HumanMessage(content="消防通道也被杂物堵了")],
          "categories": ["占道"],
          "active_category": "占道", "category_index": 0,
          "category_slots": {"占道": {"behavior": "摆摊"}},
          "category_results": {}, "missing": ["占道_blocked"],
          "relationship": "", "clarify_count": 0, "clarify_stopped": False,
          "vision_summary": ""}
    up = ag.route(st)
    assert up["pending_categories"] == ["消防通道"]
    assert up["relationship"] == "pending"
    assert up["categories"] == ["占道"]


def test_route_pending_same_place_adds(monkeypatch):
    # 待定 + “同一处” → ADD 并入
    monkeypatch.setattr(ag, "_infer_categories", lambda text, vision_category="": [])
    monkeypatch.setattr(ag, "_llm_extract_slots", lambda msg, cats, keys: {})
    st = {"messages": [ag.HumanMessage(content="是同一处")],
          "categories": ["占道"],
          "pending_categories": ["消防通道"],
          "active_category": "占道", "category_index": 0,
          "category_slots": {"占道": {"behavior": "摆摊"}},
          "category_results": {}, "missing": ["占道_blocked"],
          "relationship": "pending", "clarify_count": 0, "clarify_stopped": False,
          "vision_summary": ""}
    up = ag.route(st)
    assert up["pending_categories"] == []
    assert up["relationship"] == "add"
    assert up["categories"] == ["消防通道", "占道"]


def test_route_pending_separate_switches(monkeypatch):
    # 待定 + “单独一条” → SWITCH 切到待定，旧槽清理
    monkeypatch.setattr(ag, "_infer_categories", lambda text, vision_category="": [])
    monkeypatch.setattr(ag, "_llm_extract_slots", lambda msg, cats, keys: {})
    st = {"messages": [ag.HumanMessage(content="单独一条")],
          "categories": ["占道"],
          "pending_categories": ["消防通道"],
          "active_category": "占道", "category_index": 0,
          "category_slots": {"占道": {"behavior": "摆摊"}},
          "category_results": {}, "missing": ["占道_blocked"],
          "relationship": "pending", "clarify_count": 0, "clarify_stopped": False,
          "vision_summary": ""}
    up = ag.route(st)
    assert up["pending_categories"] == []
    assert up["relationship"] == "switch"
    assert up["categories"] == ["消防通道"]
    assert "占道" not in up["category_slots"]


def test_meta_clarify_includes_pending(monkeypatch):
    seen = {}
    def fake(slots, ctx):
        seen["ctx"] = ctx
        return "这些是同一个地方的问题，还是另外单独一条？"
    monkeypatch.setattr(ag, "_llm_phrase", fake)
    st = {"messages": [ag.HumanMessage(content="那消防被堵呢")],
          "missing": ["消防通道_blocker"], "categories": ["占道", "消防通道"],
          "pending_categories": ["消防通道"],
          "active_category": "占道", "category_index": 0,
          "category_slots": {}, "relationship": "", "clarify_count": 0, "clarify_stopped": False}
    up = ag.meta_clarify(st)
    assert "占道" in seen["ctx"] and "消防通道" in seen["ctx"]
    assert up["relationship"] == "pending"


def test_route_decider_pending_goes_meta():
    st = {"pending_categories": ["消防通道"], "missing": [],
          "relationship": "", "clarify_count": 0, "clarify_stopped": False}
    assert ag.route_decider(st) == "meta_clarify"


def test_find_negated_cat_first_negation_after():
    # "占道不是问题" —— 类别在前，否定在后（B 方案）
    assert ag._find_negated("占道不是问题") == ["占道"]

def test_find_negated_cat_does_not_exist():
    # "占道不存在" —— 类别 + 否定在后
    assert ag._find_negated("占道不存在") == ["占道"]

def test_find_negated_various_forms():
    # 多种否定句式都能识别
    assert ag._find_negated("占道不对") == ["占道"]
    assert ag._find_negated("不是占道，是消防通道") == ["占道"]
    assert ag._find_negated("消防通道根本不是问题") == ["消防通道"]

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
    assert sent == [{"chunk": "## "}, {"chunk": "占道"}, {"chunk": "被堵"}]

def test_bridge_custom_chunk_from_report(monkeypatch):
    import asyncio
    import core.assistant_graph as ag
    from langchain_core.messages import HumanMessage
    # monkeypatch _report_llm 流式返回 token
    class FakeStream:
        def _call_llm_stream_events(self, msgs, cancellation=None):
            for t in ["#", "报告", "正文"]:
                yield ("chunk", t)
    ag._report_llm = FakeStream()
    monkeypatch.setattr(ag, "_infer_categories", lambda t, v="": ["占道"])
    # 信息齐全：占道三槽全填 -> missing 空 -> 走 search -> report
    monkeypatch.setattr(ag, "_llm_extract_slots", lambda msg, cats, keys: {"占道": {"behavior":"摆摊","persistence":"长期","blocked":"完全堵死"}})
    monkeypatch.setattr(ag, "_llm_phrase", lambda slots, ctx: "占道是完全堵死吗？")
    monkeypatch.setattr(ag, "_llm_classify", lambda t: "占道")
    monkeypatch.setattr(ag, "_run_tool", lambda name, kw: f"[{name}] {kw}")
    async def run():
        out = []
        async for kind, text in ag.run_stream_events(
            message="长期占着盲道完全堵死", history=[], slots={}, vision_summary="", session_id="t", max_rounds=3):
            out.append((kind, text))
        return out
    out = asyncio.run(run())
    # 应收到来自 report 的 custom chunk（逐 token，出现"报告"/"正文"）
    assert any(k == "chunk" and "正文" in t for k, t in out)
    # 应收到多个 chunk 而不是一整块
    chunks = [t for k, t in out if k == "chunk"]
    assert len([c for c in chunks if c in ("#", "报告", "正文")]) == 3

