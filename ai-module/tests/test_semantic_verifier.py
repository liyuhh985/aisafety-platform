# -*- coding: utf-8 -*-
"""Runtime semantic verification contracts (tasks added in TDD order)."""

from core.agent import Agent


def test_semantic_agent_temperature_is_zero():
    agent = Agent(
        name="semantic_labeler_a",
        system_prompt="VERIFY",
        tools=[],
        base_url="http://example.invalid",
        api_key="k",
        model="m",
        temperature=0.0,
        use_configured_slot=False,
        allow_fallback=False,
    )
    payload = agent._build_payload([{"role": "user", "content": "q"}], stream=False)
    assert payload["temperature"] == 0.0


def test_dedicated_agent_ignores_global_slot_and_fallback(monkeypatch):
    from types import SimpleNamespace
    import core.agent as agent_module

    monkeypatch.setattr(
        agent_module,
        "SMALL_MODEL",
        SimpleNamespace(base_url="http://global", api_key="g", model="global", effort=""),
    )
    monkeypatch.setattr(agent_module, "FALLBACK_LLM_BASE_URL", "http://fallback")
    monkeypatch.setattr(agent_module, "FALLBACK_LLM_API_KEY", "f")
    monkeypatch.setattr(agent_module, "FALLBACK_LLM_MODEL", "fallback-model")
    agent = Agent(
        name="semantic_labeler_a",
        system_prompt="VERIFY",
        tools=[],
        base_url="http://dedicated",
        api_key="d",
        model="minimax-m3.1-flash",
        slot="small",
        use_configured_slot=False,
        allow_fallback=False,
    )
    assert agent._llm_endpoints() == [
        ("http://dedicated", "d", "minimax-m3.1-flash", None)
    ]


from core import semantic_verifier as sv


def _issue(code, major, slots):
    return {
        "major_code": major,
        "subcategory_code": code,
        "slots": slots,
    }


def _audit(code, slot, value, quote="有东西", source_ref="u1"):
    return {
        "status": "weak",
        "business_status": "unavailable",
        "value": value,
        "quote": quote,
        "source_ref": source_ref,
    }


def _result(prefix, label, confidence):
    return {prefix: {"label": label, "confidence": confidence}}


def test_a_class_dual_entailed_is_grounded_by_model(monkeypatch):
    issue = _issue("fire_lane_blocked", "fire", {"blocker": "杂物"})
    audit = {"fire_lane_blocked": {"blocker": _audit(
        "fire_lane_blocked", "blocker", "杂物")}}
    seen = []

    def fake(key, candidates, cancellation=None):
        seen.append((key, len(candidates)))
        return {
            "fire_lane_blocked:blocker": {
                "label": "entailed", "confidence": 0.95,
            }
        }

    monkeypatch.setattr(sv, "_call_labeler", fake)
    result = sv.verify_weak_slots([issue], audit)
    assert result["fire_lane_blocked"]["blocker"]["business_status"] == (
        "grounded_by_model"
    )
    assert [key for key, _count in seen] == ["A", "B"]


def test_a_class_requires_both_models_to_entail(monkeypatch):
    issue = _issue("fire_lane_blocked", "fire", {"blocker": "杂物"})
    audit = {"fire_lane_blocked": {"blocker": _audit(
        "fire_lane_blocked", "blocker", "杂物")}}

    def fake(key, candidates, cancellation=None):
        if key == "A":
            return {"fire_lane_blocked:blocker": {
                "label": "entailed", "confidence": 0.95,
            }}
        return {"fire_lane_blocked:blocker": {
            "label": "neutral", "confidence": 0.80,
        }}

    monkeypatch.setattr(sv, "_call_labeler", fake)
    result = sv.verify_weak_slots([issue], audit)
    assert result["fire_lane_blocked"]["blocker"]["business_status"] == (
        "unavailable"
    )


def test_a_class_dual_contradicted_is_rejected(monkeypatch):
    issue = _issue("dangerous_building", "building", {"structure": "倾斜"})
    audit = {"dangerous_building": {"structure": _audit(
        "dangerous_building", "structure", "倾斜")}}

    def fake(key, candidates, cancellation=None):
        return {"dangerous_building:structure": {
            "label": "contradicted", "confidence": 0.95,
        }}

    monkeypatch.setattr(sv, "_call_labeler", fake)
    result = sv.verify_weak_slots([issue], audit)
    assert result["dangerous_building"]["structure"]["business_status"] == "rejected"


def test_b_class_entailment_uses_one_high_confidence_model(monkeypatch):
    issue = _issue("fire_lane_blocked", "fire", {"impact": "无法通行"})
    audit = {"fire_lane_blocked": {"impact": _audit(
        "fire_lane_blocked", "impact", "无法通行")}}
    calls = []

    def fake(key, candidates, cancellation=None):
        calls.append(key)
        return {"fire_lane_blocked:impact": {
            "label": "entailed", "confidence": 0.90,
        }}

    monkeypatch.setattr(sv, "_call_labeler", fake)
    result = sv.verify_weak_slots([issue], audit)
    assert result["fire_lane_blocked"]["impact"]["business_status"] == (
        "grounded_by_model"
    )
    assert calls == ["A"]


def test_b_class_contradiction_requires_b_confirmation(monkeypatch):
    issue = _issue("fire_lane_blocked", "fire", {"impact": "无法通行"})
    audit = {"fire_lane_blocked": {"impact": _audit(
        "fire_lane_blocked", "impact", "无法通行")}}

    def fake(key, candidates, cancellation=None):
        return {"fire_lane_blocked:impact": {
            "label": "contradicted", "confidence": 0.95,
        }}

    monkeypatch.setattr(sv, "_call_labeler", fake)
    result = sv.verify_weak_slots([issue], audit)
    assert result["fire_lane_blocked"]["impact"]["business_status"] == "rejected"


def test_b_class_unconfirmed_contradiction_is_unavailable(monkeypatch):
    issue = _issue("fire_lane_blocked", "fire", {"impact": "无法通行"})
    audit = {"fire_lane_blocked": {"impact": _audit(
        "fire_lane_blocked", "impact", "无法通行")}}

    def fake(key, candidates, cancellation=None):
        if key == "A":
            return {"fire_lane_blocked:impact": {
                "label": "contradicted", "confidence": 0.95,
            }}
        return {"fire_lane_blocked:impact": {
            "label": "neutral", "confidence": 0.90,
        }}

    monkeypatch.setattr(sv, "_call_labeler", fake)
    result = sv.verify_weak_slots([issue], audit)
    assert result["fire_lane_blocked"]["impact"]["business_status"] == (
        "unavailable"
    )


def test_labeler_exception_becomes_unavailable(monkeypatch):
    issue = _issue("fire_lane_blocked", "fire", {"blocker": "杂物"})
    audit = {"fire_lane_blocked": {"blocker": _audit(
        "fire_lane_blocked", "blocker", "杂物")}}

    def fake(key, candidates, cancellation=None):
        raise TimeoutError("timeout")

    monkeypatch.setattr(sv, "_call_labeler", fake)
    result = sv.verify_weak_slots([issue], audit)
    assert result["fire_lane_blocked"]["blocker"]["business_status"] == (
        "unavailable"
    )


def test_candidate_cap_prioritizes_a_class_and_sends_five(monkeypatch):
    issue = _issue("dangerous_building", "building", {
        "risk": "有风险", "occupancy": "有人", "structure": "倾斜",
    })
    issue_two = _issue("fire_lane_blocked", "fire", {
        "impact": "影响", "persistence": "长期", "blocker": "杂物",
    })
    audit = {
        "dangerous_building": {
            "risk": _audit("dangerous_building", "risk", "有风险"),
            "occupancy": _audit("dangerous_building", "occupancy", "有人"),
            "structure": _audit("dangerous_building", "structure", "倾斜"),
        },
        "fire_lane_blocked": {
            "impact": _audit("fire_lane_blocked", "impact", "影响"),
            "persistence": _audit("fire_lane_blocked", "persistence", "长期"),
            "blocker": _audit("fire_lane_blocked", "blocker", "杂物"),
        },
    }
    seen = []

    def fake(key, candidates, cancellation=None):
        seen.append((key, candidates))
        return {}

    monkeypatch.setattr(sv, "_call_labeler", fake)
    sv.verify_weak_slots([issue, issue_two], audit)
    assert len(seen[0][1]) == 5
    assert all(row["value_class"] in {"A", "B"} for row in seen[0][1])
    assert seen[0][0] == "A"
