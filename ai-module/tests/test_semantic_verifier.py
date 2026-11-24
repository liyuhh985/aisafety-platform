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


def _mark(audit, code, slot, business_status):
    result = audit[code][slot]
    result["status"] = business_status
    result["business_status"] = business_status
    if business_status == "unavailable":
        result["reason"] = "model_indeterminate_or_failed"
    elif business_status == "rejected":
        result["reason"] = "model_consensus_contradicted"
    else:
        result["reason"] = "model_consensus_entailed"
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


def test_grounded_by_model_keeps_slot_and_clears_caution(monkeypatch):
    import core.assistant_graph as ag

    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "enforce")
    monkeypatch.setattr(
        ag, "verify_weak_slots",
        lambda issues, audit, cancellation=None: _mark(
            audit, "dangerous_building", "structure", "grounded_by_model"
        ),
    )
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "building",
            "subcategory_code": "dangerous_building",
            "slots": {"structure": "墙体倾斜", "occupancy": "有人居住"},
            "evidence": [{
                "slot": "structure", "quote": "房子明显往一边斜", "source_ref": "u1",
            }],
        }],
        "categories": ["dangerous_building"],
        "category_slots": {"dangerous_building": {
            "structure": "墙体倾斜", "occupancy": "有人居住",
        }},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: plan)
    out = ag.understand({
        "messages": [ag.HumanMessage(
            content="房子明显往一边斜，而且现在有人居住"
        )],
        "active_skills": ["building"],
    })
    assert out["issues"][0]["slots"]["structure"] == "墙体倾斜"
    assert out["issues"][0]["unverified"] == []
    assert out["issues"][0]["slot_evidence"]["structure"]["status"] == (
        "grounded_by_model"
    )


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


def test_shadow_does_not_call_labelers(monkeypatch):
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


def test_off_does_not_call_labelers(monkeypatch):
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


def test_labeler_prompt_declares_batch_input_and_output_schema():
    from core.semantic_verifier import SEMANTIC_LABELER_PROMPT

    assert "JSON 数组" in SEMANTIC_LABELER_PROMPT
    assert '"labels"' in SEMANTIC_LABELER_PROMPT
    assert '"id"' in SEMANTIC_LABELER_PROMPT
    assert "每个输入 id" in SEMANTIC_LABELER_PROMPT


def test_parse_batch_response_reads_labels_envelope():
    from core.semantic_verifier import parse_batch_response

    result = parse_batch_response(
        '{"labels":[{"id":"fire:blocker","label":"entailed","confidence":0.93},'
        '{"id":"fire:persistence","label":"neutral","confidence":0.82}]}'
    )
    assert result == {
        "fire:blocker": {"label": "entailed", "confidence": 0.93},
        "fire:persistence": {"label": "neutral", "confidence": 0.82},
    }


def test_runtime_call_labeler_uses_batch_envelope(monkeypatch):
    import json
    from types import SimpleNamespace
    from core import semantic_verifier as sv

    captured = {}

    def fake_call(messages, cancellation=None):
        captured["payload"] = json.loads(messages[1]["content"])
        return {
            "content": '{"labels":[{"id":"fire:blocker",'
                       '"label":"entailed","confidence":0.95}]}'
        }

    fake = SimpleNamespace(
        system_prompt="BATCH_PROMPT",
        _call_llm=fake_call,
    )
    monkeypatch.setitem(sv._LABELERS, "A", fake)
    result = sv._call_labeler("A", [{
        "id": "fire:blocker",
        "slot": "blocker",
        "slot_question": "被什么东西占用了？",
        "value": "杂物",
        "quote": "消防通道被杂物堵住",
    }])
    assert isinstance(captured["payload"], list)
    assert set(captured["payload"][0]) == {
        "id", "slot", "slot_question", "value", "quote",
    }
    assert result["fire:blocker"] == {"label": "entailed", "confidence": 0.95}
