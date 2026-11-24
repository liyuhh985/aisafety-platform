import core.assistant_graph as ag


def test_skill_route_reuses_locked_majors(monkeypatch):
    monkeypatch.setattr(
        ag, "_skill_route_llm",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called")),
    )
    out = ag.skill_route({
        "messages": [],
        "locked_majors": ["fire", "utility"],
        "selected_major_codes": [],
        "vision_summary": "",
    })
    assert out["active_skills"] == ["fire", "utility"]
    assert out["skill_route_source"] == "locked"
    assert set(out["skill_versions"]) == {"fire", "utility"}


def test_skill_route_caps_frontend_selection():
    out = ag.skill_route({
        "messages": [],
        "locked_majors": [],
        "selected_major_codes": ["fire", "utility", "municipal", "traffic"],
        "vision_summary": "",
    })
    assert out["active_skills"] == ["fire", "utility", "municipal"]
    assert out["skill_route_source"] == "frontend"


def test_skill_route_extracts_vision_major_codes():
    assert ag._vision_major_codes("视觉结果：消防安全，另有燃气泄漏") == [
        "fire", "utility",
    ]


def test_skill_route_is_between_begin_turn_and_understand():
    graph = ag.build_graph().get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}
    assert ("begin_turn", "skill_route") in edges
    assert ("skill_route", "understand") in edges
def test_retrieval_uses_only_allowed_tools(monkeypatch):
    monkeypatch.setattr(ag._skill_registry, "resolve_tools", lambda skills: ["search_regulation"])
    state = {
        "categories": ["fire_lane_blocked"],
        "category_slots": {},
        "retrieval_keyword_override": {},
        "active_skills": ["fire"],
    }
    sends = ag.plan_retrieval(state)
    assert {send.arg["tool"] for send in sends} == {"search_regulation"}


def test_retrieval_falls_back_when_no_skill_is_active(monkeypatch):
    monkeypatch.setattr(ag._skill_registry, "resolve_tools", lambda skills: [])
    state = {
        "categories": ["fire_lane_blocked"],
        "category_slots": {},
        "retrieval_keyword_override": {},
        "active_skills": [],
    }
    sends = ag.plan_retrieval(state)
    assert {send.arg["tool"] for send in sends} == {"search_regulation", "search_cases"}


def test_report_includes_only_active_skill_report_sections(monkeypatch):
    captured = {}

    def fake_section(code, heading):
        assert heading == "报告约束"
        return f"{code} report rule"

    monkeypatch.setattr(ag._skill_registry, "load_section", fake_section)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)

    def fake_stream(messages, cancellation=None):
        captured["prompt"] = messages[-1]["content"]
        yield ("chunk", "BODY")

    monkeypatch.setattr(ag, "can_offer_task_creation", lambda state: False)
    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    state = {
        "messages": [],
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "杂物", "persistence": "长期"},
            "missing": [],
            "evidence": [{
                "slot": "blocker", "quote": "通道里有杂物", "source_ref": "u1",
            }],
            "slot_evidence": {
                "blocker": {"status": "grounded", "quote": "通道里有杂物", "source_ref": "u1"},
            },
        }],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物", "persistence": "长期"}},
        "missing": [],
        "report_mode": "full",
        "active_skills": ["fire"],
    }
    ag.report(state)
    assert "fire report rule" in captured["prompt"]
    assert "utility report rule" not in captured["prompt"]
    assert "allowed_tools" not in captured["prompt"]
    assert "通道里有杂物" not in captured["prompt"]
    assert "slot_evidence" not in captured["prompt"]
def test_understand_realigns_active_skills_to_final_locked_majors(monkeypatch):
    def fake_plan(messages, vision, selected_major_code="", **kwargs):
        return {
            "ok": True,
            "intent": "report_hazard",
            "risk_level": "high",
            "issues": [{
                "major_code": "utility",
                "subcategory_code": "gas_leak",
                "slots": {"source": "燃气泄漏"},
            }],
            "categories": ["gas_leak"],
            "category_slots": {"gas_leak": {"source": "燃气泄漏"}},
            "perceived_major": "utility",
            "perceived_subcategory": "gas_leak",
            "question": "",
            "answer": "",
            "needs_search": True,
        }

    monkeypatch.setattr(ag, "_understand_plan", fake_plan)
    out = ag.understand({
        "messages": [ag.HumanMessage(content="楼道里有燃气味")],
        "active_skills": ["fire"],
        "skill_route_source": "keyword",
    })
    assert out["locked_majors"] == ["utility"]
    assert out["active_skills"] == ["utility"]
    assert out["skill_route_source"] == "locked"
    assert out["skill_versions"] == {"utility": "1"}