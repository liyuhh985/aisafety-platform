# -*- coding: utf-8 -*-
"""Contracts for the single production-LLM runtime semantic verifier."""

import json
from types import SimpleNamespace

import pytest

from langchain_core.messages import HumanMessage

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


def test_runtime_verifier_uses_project_small_model(monkeypatch):
    import core.agent as agent_module
    from core import semantic_verifier as sv

    monkeypatch.setenv("SEMANTIC_LABELER_A_BASE_URL", "http://offline-a")
    monkeypatch.setenv("SEMANTIC_LABELER_A_API_KEY", "offline-key")
    monkeypatch.setenv("SEMANTIC_LABELER_A_MODEL", "minimax")
    prod = SimpleNamespace(
        base_url="http://project-small",
        api_key="project-key",
        model="project-small-model",
        effort="",
    )
    monkeypatch.setattr(sv, "SMALL_MODEL", prod)
    monkeypatch.setattr(agent_module, "SMALL_MODEL", prod)

    agent = sv.build_verifier()
    assert agent._llm_endpoints()[0][:3] == (
        "http://project-small", "project-key", "project-small-model",
    )


def _weak_issue():
    return {
        "major_code": "building",
        "subcategory_code": "dangerous_building",
        "slots": {"structure": "墙体倾斜"},
    }


def _weak_audit(quote="房子明显往一边斜"):
    return {
        "dangerous_building": {
            "structure": {
                "status": "weak",
                "business_status": "unavailable",
                "value": "墙体倾斜",
                "quote": quote,
                "source_ref": "u1",
            }
        }
    }


def test_binary_entailment_is_grounded_by_model(monkeypatch):
    from core import semantic_verifier as sv

    monkeypatch.setattr(sv, "SEMANTIC_VERIFIER_MIN_CONFIDENCE", 0.85)
    monkeypatch.setattr(
        sv, "_call_verifier",
        lambda candidates, cancellation=None: {
            "dangerous_building:structure": {
                "label": "entailed", "confidence": 0.93,
            }
        },
    )
    result = sv.verify_weak_slots([_weak_issue()], _weak_audit())
    assert result["dangerous_building"]["structure"]["business_status"] == (
        "grounded_by_model"
    )


def test_binary_contradiction_is_rejected(monkeypatch):
    from core import semantic_verifier as sv

    monkeypatch.setattr(sv, "SEMANTIC_VERIFIER_MIN_CONFIDENCE", 0.85)
    monkeypatch.setattr(
        sv, "_call_verifier",
        lambda candidates, cancellation=None: {
            "dangerous_building:structure": {
                "label": "contradicted", "confidence": 0.91,
            }
        },
    )
    result = sv.verify_weak_slots(
        [_weak_issue()], _weak_audit("房屋结构稳定，没有倾斜")
    )
    assert result["dangerous_building"]["structure"]["business_status"] == "rejected"


def test_low_confidence_is_unavailable(monkeypatch):
    from core import semantic_verifier as sv

    monkeypatch.setattr(sv, "SEMANTIC_VERIFIER_MIN_CONFIDENCE", 0.85)
    monkeypatch.setattr(
        sv, "_call_verifier",
        lambda candidates, cancellation=None: {
            "dangerous_building:structure": {
                "label": "entailed", "confidence": 0.60,
            }
        },
    )
    result = sv.verify_weak_slots([_weak_issue()], _weak_audit())
    assert result["dangerous_building"]["structure"]["business_status"] == (
        "unavailable"
    )


def test_a_and_b_slots_use_one_batch_call(monkeypatch):
    from core import semantic_verifier as sv

    monkeypatch.setattr(sv, "SEMANTIC_VERIFIER_MIN_CONFIDENCE", 0.85)
    issues = [
        _weak_issue(),
        {
            "major_code": "fire",
            "subcategory_code": "fire_lane_blocked",
            "slots": {"impact": "无法通行"},
        },
    ]
    audit = {
        "dangerous_building": _weak_audit()["dangerous_building"],
        "fire_lane_blocked": {
            "impact": {
                "status": "weak",
                "business_status": "unavailable",
                "value": "无法通行",
                "quote": "消防车无法进入",
                "source_ref": "u2",
            }
        },
    }
    calls = []

    def fake(candidates, cancellation=None):
        calls.append([row["id"] for row in candidates])
        return {
            "dangerous_building:structure": {
                "label": "entailed", "confidence": 0.95,
            },
            "fire_lane_blocked:impact": {
                "label": "entailed", "confidence": 0.94,
            },
        }

    monkeypatch.setattr(sv, "_call_verifier", fake)
    result = sv.verify_weak_slots(issues, audit)
    assert len(calls) == 1
    assert set(calls[0]) == {
        "dangerous_building:structure", "fire_lane_blocked:impact",
    }
    assert result["dangerous_building"]["structure"]["business_status"] == (
        "grounded_by_model"
    )
    assert result["fire_lane_blocked"]["impact"]["business_status"] == (
        "grounded_by_model"
    )


def test_neutral_is_invalid_in_runtime():
    from core import semantic_verifier as sv

    assert sv.parse_batch_response(
        '{"labels":[{"id":"x","label":"neutral","confidence":0.99}]}'
    ) == {}


def test_verifier_exception_makes_candidate_unavailable(monkeypatch):
    from core import semantic_verifier as sv

    monkeypatch.setattr(
        sv, "_call_verifier",
        lambda candidates, cancellation=None: (_ for _ in ()).throw(
            RuntimeError("timeout")
        ),
    )
    result = sv.verify_weak_slots([_weak_issue()], _weak_audit())
    assert result["dangerous_building"]["structure"]["business_status"] == (
        "unavailable"
    )


def test_verifier_propagates_stream_cancellation(monkeypatch):
    from core import semantic_verifier as sv
    from core.cancellation import StreamCancelled

    monkeypatch.setattr(
        sv, "_call_verifier",
        lambda candidates, cancellation=None: (_ for _ in ()).throw(StreamCancelled()),
    )
    with pytest.raises(StreamCancelled):
        sv.verify_weak_slots([_weak_issue()], _weak_audit())


def test_verifier_payload_excludes_audit_and_classes(monkeypatch):
    from core import semantic_verifier as sv

    captured = {}

    def fake_call(messages, cancellation=None):
        captured["payload"] = json.loads(messages[1]["content"])
        return {
            "content": '{"labels":[{"id":"x","label":"entailed","confidence":0.95}]}'
        }

    monkeypatch.setattr(
        sv, "_VERIFIER",
        SimpleNamespace(system_prompt="P", _call_llm=fake_call),
    )
    sv._call_verifier([{
        "id": "x",
        "slot": "structure",
        "slot_question": "房屋是否有裂缝、倾斜或沉降？",
        "value": "墙体倾斜",
        "quote": "房子明显往一边斜",
        "value_class": "A",
        "evidence": "secret",
    }])
    assert set(captured["payload"][0]) == {
        "id", "slot", "slot_question", "value", "quote",
    }


def _weak_plan_for_mode():
    return {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "building", "subcategory_code": "dangerous_building",
            "slots": {"structure": "墙体倾斜"},
            "evidence": [{
                "slot": "structure",
                "quote": "房子明显往一边斜",
                "source_ref": "u1",
            }],
        }],
        "categories": ["dangerous_building"],
        "category_slots": {"dangerous_building": {"structure": "墙体倾斜"}},
        "question": "", "answer": "", "needs_search": True,
        "perceived_subcategory": "dangerous_building",
    }


def test_shadow_does_not_call_runtime_verifier(monkeypatch):
    import core.assistant_graph as ag

    calls = []
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "shadow")
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _weak_plan_for_mode())
    monkeypatch.setattr(
        ag, "verify_weak_slots",
        lambda *a, **k: calls.append(1) or {},
    )
    ag.understand({"messages": [ag.HumanMessage(content="房子明显往一边斜")]})
    assert calls == []


def test_off_does_not_call_runtime_verifier(monkeypatch):
    import core.assistant_graph as ag

    calls = []
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "off")
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _weak_plan_for_mode())
    monkeypatch.setattr(
        ag, "verify_weak_slots",
        lambda *a, **k: calls.append(1) or {},
    )
    ag.understand({"messages": [ag.HumanMessage(content="房子明显往一边斜")]})
    assert calls == []


def test_public_issue_strips_semantic_audit():
    from core.assistant_graph import _public_issues

    issue = {
        "subcategory_code": "dangerous_building",
        "evidence": [{
            "slot": "structure", "quote": "往一边斜", "source_ref": "u1",
        }],
        "slot_evidence": {
            "structure": {
                "status": "grounded_by_model",
                "business_status": "grounded_by_model",
            },
        },
    }
    public = _public_issues([issue])[0]
    assert "evidence" not in public
    assert "slot_evidence" not in public


def _mark(audit, code, slot, business_status):
    result = audit[code][slot]
    result["status"] = business_status
    result["business_status"] = business_status
    return audit


def test_a_unavailable_returns_to_missing(monkeypatch):
    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "enforce")
    monkeypatch.setattr(
        ag, "verify_weak_slots",
        lambda issues, audit, cancellation=None: _mark(
            audit, "fire_lane_blocked", "blocker", "unavailable"
        ),
    )
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "fire", "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "杂物"},
            "evidence": [{
                "slot": "blocker", "quote": "有东西", "source_ref": "u1",
            }],
        }],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物"}},
        "question": "", "answer": "", "needs_search": False,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: plan)
    out = ag.understand({
        "messages": [ag.HumanMessage(content="消防通道有东西堵着")],
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物"}},
        "active_skills": ["fire"],
    })
    assert "fire_lane_blocked_blocker" in out["missing"]
    assert out["issues"][0]["slots"] == {}
    assert out["next_action"] == "ask_critical_question"
    assert "请确认" not in (out.get("clarification_question") or "")


def test_b_unavailable_becomes_report_missing(monkeypatch):
    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "enforce")
    monkeypatch.setattr(
        ag, "verify_weak_slots",
        lambda issues, audit, cancellation=None: _mark(
            audit, "fire_lane_blocked", "impact", "unavailable"
        ),
    )
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "fire", "subcategory_code": "fire_lane_blocked",
            "slots": {
                "blocker": "杂物", "persistence": "长期", "impact": "影响通行",
            },
            "evidence": [{
                "slot": "impact", "quote": "影响通行", "source_ref": "u1",
            }],
        }],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {
            "blocker": "杂物", "persistence": "长期", "impact": "影响通行",
        }},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: plan)
    out = ag.understand({
        "messages": [ag.HumanMessage(content="消防通道长期被杂物堵住，影响通行")],
        "active_skills": ["fire"],
    })
    assert "fire_lane_blocked_blocker" not in out["missing"]
    assert "impact" in out["issues"][0]["report_missing"]
    assert "impact" not in out["issues"][0]["slots"]
    assert out["issues"][0]["unverified"] == []
