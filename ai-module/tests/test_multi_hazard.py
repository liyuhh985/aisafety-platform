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

def test_cross_slot_map_has_blocked_to_impact():
    assert ag.CROSS_SLOT_MAP.get(("占道", "blocked")) == ("消防通道", "impact")


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

def test_relocate_redirects_not_drops():
    cats = ["占道", "消防通道"]
    cs = {"占道": {"blocked": "消防通道被堵"}, "消防通道": {}}
    out = ag._relocate("消防通道被堵", "占道", "blocked", cats, cs)
    assert "消防通道" in out["categories"]
    assert out["category_slots"]["消防通道"].get("impact") is not None
    assert "blocked" not in out["category_slots"].get("占道", {})
