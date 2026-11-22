from langchain_core.messages import HumanMessage

from core.dialogue_understanding import build_planner_messages


def test_prompt_contains_only_active_skill_body():
    built = build_planner_messages(
        [HumanMessage(content="消防通道被占，旁边配电箱冒火花")],
        skill_bodies={"fire": "FIRE BODY", "utility": "UTILITY BODY"},
    )
    combined = "\n".join(item["content"] for item in built)
    assert "FIRE BODY" in combined
    assert "UTILITY BODY" in combined
    assert "MUNICIPAL BODY" not in combined
    assert "allowed_tools" not in combined
    assert "routing_keywords" not in combined
    assert "version:" not in combined


def test_understand_loads_bodies_locally_and_does_not_return_them(monkeypatch):
    import core.assistant_graph as ag
    captured = {}

    def fake_registry(code):
        return f"{code} BODY SECRET"

    def fake_plan(messages, vision, selected_major_code="", **kwargs):
        captured.update(kwargs)
        return {
            "ok": True, "intent": "quick_assessment",
            "issues": [{
                "major_code": "fire",
                "subcategory_code": "fire_equipment_fault",
                "slots": {"condition": "老旧"},
            }],
            "categories": ["fire_equipment_fault"],
            "category_slots": {"fire_equipment_fault": {"condition": "老旧"}},
            "question": "", "answer": "", "needs_search": False,
        }

    monkeypatch.setattr(ag._skill_registry, "load_body", fake_registry)
    monkeypatch.setattr(ag, "_understand_plan", fake_plan)
    out = ag.understand({
        "messages": [ag.HumanMessage(content="消防设施老旧")],
        "active_skills": ["fire"],
    })
    assert captured["skill_bodies"] == {"fire": "fire BODY SECRET"}
    assert captured["active_skill_codes"] == ["fire"]
    assert "skill_bodies" not in out
    assert all("SECRET" not in str(value) for value in out.values())
def test_understand_falls_back_when_skill_body_load_fails(monkeypatch):
    import core.assistant_graph as ag
    captured = {}

    def broken_registry(code):
        raise OSError("missing body")

    def fake_plan(messages, vision, selected_major_code="", **kwargs):
        captured.update(kwargs)
        return {
            "ok": True, "intent": "quick_assessment",
            "issues": [], "categories": [], "category_slots": {},
            "question": "", "answer": "", "needs_search": False,
        }

    monkeypatch.setattr(ag._skill_registry, "load_body", broken_registry)
    monkeypatch.setattr(ag, "_understand_plan", fake_plan)
    out = ag.understand({
        "messages": [ag.HumanMessage(content="消防设施老旧")],
        "active_skills": ["fire"],
    })
    assert out["dialogue_plan"]["ok"] is True
    assert "skill_bodies" not in captured
    assert captured["active_skill_codes"] == ["fire"]
def test_skill_pruned_planner_prompt_excludes_inactive_subcategories():
    from core.dialogue_understanding import _planner_system_prompt
    pruned = _planner_system_prompt(active_skill_codes=["fire", "utility"])
    full = _planner_system_prompt()
    assert "fire_equipment_fault" in pruned
    assert "gas_leak" in pruned
    assert "elevator_trapped" not in pruned
    assert "elevator_special" not in pruned
    assert len(pruned) < len(full)


def test_build_planner_messages_adds_compact_all_major_index():
    built = build_planner_messages(
        [HumanMessage(content="消防通道被占，旁边配电箱冒火花")],
        skill_bodies={"fire": "FIRE BODY", "utility": "UTILITY BODY"},
        active_skill_codes=["fire", "utility"],
    )
    combined = "\n".join(item["content"] for item in built)
    assert "elevator_special" in combined
    assert "elevator_trapped" not in combined