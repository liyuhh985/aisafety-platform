"""Evidence-grounded slot verification: contract, verifier, rollout and leakage."""
import importlib

import pytest


def test_slot_evidence_mode_defaults_to_shadow(monkeypatch):
    monkeypatch.delenv("SLOT_EVIDENCE_MODE", raising=False)
    import config
    importlib.reload(config)
    assert config.SLOT_EVIDENCE_MODE == "shadow"


def test_slot_evidence_mode_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("SLOT_EVIDENCE_MODE", "strict")
    import config
    with pytest.raises(ValueError, match="SLOT_EVIDENCE_MODE"):
        importlib.reload(config)
from core.dialogue_understanding import parse_plan


def test_parse_plan_preserves_valid_evidence():
    raw = '''{
      "intent": "report_hazard",
      "issues": [{
        "major_code": "building",
        "subcategory_code": "dangerous_building",
        "slots": {"structure": "墙体倾斜"},
        "evidence": [{
          "slot": "structure",
          "quote": "房子明显往一边斜",
          "source_ref": "u2"
        }]
      }]
    }'''
    issue = parse_plan(raw)["issues"][0]
    assert issue["evidence"] == [{
        "slot": "structure",
        "quote": "房子明显往一边斜",
        "source_ref": "u2",
    }]


def test_parse_plan_drops_evidence_for_unknown_slot():
    raw = '''{
      "intent": "report_hazard",
      "issues": [{
        "major_code": "fire",
        "subcategory_code": "fire_lane_blocked",
        "slots": {"blocker": "杂物"},
        "evidence": [{"slot": "unknown", "quote": "杂物", "source_ref": "u1"}]
      }]
    }'''
    issue = parse_plan(raw)["issues"][0]
    assert issue["evidence"] == []
from langchain_core.messages import AIMessage, HumanMessage
from core.dialogue_understanding import build_planner_messages, build_source_map


def test_source_map_prefixes():
    messages = [
        HumanMessage(content="红色"),
        AIMessage(content="收到"),
        HumanMessage(content="配电箱冒火花"),
    ]
    source_map = build_source_map(messages, "[视觉分析] 配电箱外观破损")
    assert source_map["u1"] == "红色"
    assert source_map["a1"] == "收到"
    assert source_map["u2"] == "配电箱冒火花"
    assert source_map["v1"] == "[视觉分析] 配电箱外观破损"


def test_planner_messages_expose_refs_for_visible_history_only():
    from config import PLANNER_HISTORY_MESSAGES
    messages = [HumanMessage(content=f"m{i}") for i in range(PLANNER_HISTORY_MESSAGES + 5)]
    built = build_planner_messages(messages, "[视觉分析] 外墙裂缝")
    combined = "\n".join(item["content"] for item in built)
    assert f"[u{PLANNER_HISTORY_MESSAGES + 5}] m{PLANNER_HISTORY_MESSAGES + 4}" in combined
    assert "[u1] m0" not in combined
    assert "[v1] [视觉分析] 外墙裂缝" in combined
from core.uncertainty import verify_slot_evidence

SOURCE_MAP = {
    "u1": "消防通道长期堆着杂物",
    "u2": "房子明显往一边斜",
    "a1": "我理解为墙体倾斜",
}


def test_quote_support_classification():
    weak = verify_slot_evidence(
        "structure", "墙体倾斜",
        {"quote": "房子明显往一边斜", "source_ref": "u2"},
        SOURCE_MAP, "dangerous_building",
    )
    assert weak["status"] == "weak"
    assert weak["reason"] == "value_not_in_quote"

    grounded = verify_slot_evidence(
        "persistence", "长期",
        {"quote": "长期堆着", "source_ref": "u1"},
        SOURCE_MAP, "fire_lane_blocked",
    )
    assert grounded["status"] == "grounded"


def test_invalid_and_assistant_sources_are_unverified():
    assert verify_slot_evidence(
        "structure", "墙体倾斜",
        {"quote": "墙体倾斜", "source_ref": "u9"},
        SOURCE_MAP, "dangerous_building",
    )["reason"] == "invalid_source_ref"
    assert verify_slot_evidence(
        "structure", "墙体倾斜",
        {"quote": "墙体倾斜", "source_ref": "a1"},
        SOURCE_MAP, "dangerous_building",
    )["reason"] == "assistant_source"
def test_quote_missing_and_no_evidence_are_unverified():
    assert verify_slot_evidence(
        "structure", "墙体倾斜", None, SOURCE_MAP, "dangerous_building",
    )["reason"] == "no_evidence"
    assert verify_slot_evidence(
        "structure", "墙体倾斜",
        {"quote": "墙体倒塌", "source_ref": "u2"},
        SOURCE_MAP, "dangerous_building",
    )["reason"] == "quote_not_found"


def test_numeric_mismatch_is_unverified():
    result = verify_slot_evidence(
        "persistence", "持续2个月",
        {"quote": "只持续1个月", "source_ref": "u3"},
        {**SOURCE_MAP, "u3": "楼道占用只持续1个月"},
        "fire_lane_blocked",
    )
    assert result["status"] == "unverified"
    assert result["reason"] == "numeric_mismatch"


def test_negated_quote_is_contradicted():
    result = verify_slot_evidence(
        "risk", "冒烟",
        {"quote": "没有冒烟", "source_ref": "u4"},
        {**SOURCE_MAP, "u4": "配电箱没有冒烟"},
        "exposed_wire",
    )
    assert result["status"] == "contradicted"
    assert result["reason"] == "negation_conflict"


def test_echo_is_not_unverified():
    result = verify_slot_evidence(
        "structure", "危房", None, SOURCE_MAP, "dangerous_building",
    )
    assert result["status"] == "echo"
from core.uncertainty import assess


def test_assess_uses_evidence_and_keeps_legacy_result():
    plan = {
        "ok": True,
        "issues": [{
            "subcategory_code": "dangerous_building",
            "slots": {"structure": "墙体倾斜"},
            "evidence": [{
                "slot": "structure",
                "quote": "房子明显往一边斜",
                "source_ref": "u1",
            }],
        }],
    }
    result = assess(plan, [{"role": "user", "content": "房子明显往一边斜"}])
    audit = result["slot_evidence_audit"]["dangerous_building"]["structure"]
    assert audit["status"] == "weak"
    assert result["uncertainty_level"] == "ok"
    assert result["legacy_uncertainty_level"] == "cautious"
    assert result["legacy_ungrounded_slots"] == ["dangerous_building.structure=墙体倾斜"]

    legacy = assess(
        {"ok": True, "issues": [{
            "subcategory_code": "fire_lane_blocked",
            "slots": {"persistence": "长期占用"},
        }]},
        [{"role": "user", "content": "楼道里全是浓烟"}],
    )
    assert legacy["ungrounded_slots"] == ["fire_lane_blocked.persistence=长期占用"]
def test_slot_evidence_survives_issue_merge():
    from core.assistant_graph import _merge_persisted_slots
    issues = [{
        "subcategory_code": "dangerous_building",
        "slots": {"structure": "墙体倾斜"},
        "evidence": [{"slot": "structure", "quote": "往一边斜", "source_ref": "u1"}],
    }]
    merged = _merge_persisted_slots(issues, {"dangerous_building": {}})
    assert merged[0]["evidence"][0]["source_ref"] == "u1"


def test_merge_carries_persisted_evidence_for_untouched_slots():
    from core.assistant_graph import _merge_persisted_slots
    previous = [{
        "subcategory_code": "dangerous_building",
        "slots": {"occupancy": "有人居住"},
        "evidence": [{"slot": "occupancy", "quote": "里面有人住", "source_ref": "u1"}],
    }]
    incoming = [{
        "subcategory_code": "dangerous_building",
        "slots": {"structure": "墙体倾斜"},
        "evidence": [{"slot": "structure", "quote": "往一边斜", "source_ref": "u2"}],
    }]
    merged = _merge_persisted_slots(
        incoming,
        {"dangerous_building": {"occupancy": "有人居住"}},
        previous,
    )
    evidence = {item["slot"]: item for item in merged[0]["evidence"]}
    assert evidence["structure"]["source_ref"] == "u2"
    assert evidence["occupancy"]["source_ref"] == "u1"
def test_understand_attaches_internal_slot_evidence_audit(monkeypatch):
    import core.assistant_graph as ag

    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "building",
            "subcategory_code": "dangerous_building",
            "slots": {"structure": "墙体倾斜"},
            "evidence": [{
                "slot": "structure", "quote": "墙体倾斜", "source_ref": "u1",
            }],
        }],
        "categories": ["dangerous_building"],
        "category_slots": {"dangerous_building": {"structure": "墙体倾斜"}},
        "question": "", "answer": "", "needs_search": True,
        "perceived_subcategory": "dangerous_building",
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    out = ag.understand({"messages": [ag.HumanMessage(content="墙体倾斜")]})
    issue = out["issues"][0]
    assert issue["evidence"][0]["source_ref"] == "u1"
    assert issue["slot_evidence"]["structure"]["status"] == "grounded"
def test_shadow_mode_preserves_legacy_unverified(monkeypatch):
    import core.assistant_graph as ag
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "shadow")
    verdict = {
        "ungrounded_slots": ["fire_lane_blocked.persistence=持续中"],
        "legacy_ungrounded_slots": ["fire_lane_blocked.persistence=持续中"],
        "evidence_ungrounded_slots": [],
    }
    assert ag._effective_ungrounded_slots(verdict) == [
        "fire_lane_blocked.persistence=持续中"
    ]


def test_enforce_mode_uses_evidence_unverified(monkeypatch):
    import core.assistant_graph as ag
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "enforce")
    verdict = {
        "legacy_ungrounded_slots": ["fire_lane_blocked.persistence=持续中"],
        "evidence_ungrounded_slots": ["dangerous_building.structure=墙体倾斜"],
        "slot_evidence_audit": {
            "dangerous_building": {"structure": {"status": "unverified"}},
        },
    }
    assert ag._effective_ungrounded_slots(verdict) == [
        "dangerous_building.structure=墙体倾斜"
    ]


def test_enforce_mode_falls_back_for_old_checkpoint_slots(monkeypatch):
    import core.assistant_graph as ag
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "enforce")
    verdict = {
        "legacy_ungrounded_slots": ["fire_lane_blocked.persistence=长期占用"],
        "evidence_ungrounded_slots": [],
    }
    assert ag._effective_ungrounded_slots(verdict) == [
        "fire_lane_blocked.persistence=长期占用"
    ]


def test_public_issues_strip_internal_evidence_fields():
    from core.assistant_graph import _public_issues
    raw = [{
        "subcategory_code": "dangerous_building",
        "slots": {"structure": "墙体倾斜"},
        "evidence": [{"slot": "structure", "quote": "往一边斜", "source_ref": "u1"}],
        "slot_evidence": {
            "structure": {"status": "weak", "quote": "往一边斜", "source_ref": "u1"},
        },
    }]
    public = _public_issues(raw)
    assert public[0]["slots"] == {"structure": "墙体倾斜"}
    assert "evidence" not in public[0]
    assert "slot_evidence" not in public[0]
def _weak_evidence_plan():
    return {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "building",
            "subcategory_code": "dangerous_building",
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


def test_understand_shadow_mode_keeps_legacy_uncertainty(monkeypatch):
    import core.assistant_graph as ag
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "shadow")
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _weak_evidence_plan())
    out = ag.understand({"messages": [ag.HumanMessage(content="房子明显往一边斜")]})
    assert out["uncertainty_level"] == "cautious"
    assert out["ungrounded_slots"] == ["dangerous_building.structure=墙体倾斜"]


def test_understand_enforce_mode_removes_unavailable_runtime_evidence(monkeypatch):
    import core.assistant_graph as ag
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "enforce")
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _weak_evidence_plan())
    out = ag.understand({"messages": [ag.HumanMessage(content="房子明显往一边斜")]})
    assert out["uncertainty_level"] == "ok"
    assert out["ungrounded_slots"] == []
    result = out["issues"][0]["slot_evidence"]["structure"]
    assert result["status"] == "unavailable"
    assert result["business_status"] == "unavailable"
    assert "dangerous_building_structure" in out["missing"]
def test_planner_prompt_requires_quote_and_source_ref():
    built = build_planner_messages([HumanMessage(content="房子往一边斜")])
    system_prompt = built[0]["content"]
    assert '"evidence"' in system_prompt
    assert "source_ref" in system_prompt
    assert "原样" in system_prompt
    assert "assistant" in system_prompt

BUSINESS_SOURCE_MAP = {
    "u1": "消防通道长期堆着杂物",
    "u2": "房子明显往一边斜",
}


def test_business_status_mapping():
    from core.uncertainty import verify_slot_evidence

    grounded = verify_slot_evidence(
        "persistence", "长期",
        {"quote": "长期堆着", "source_ref": "u1"},
        BUSINESS_SOURCE_MAP, "fire_lane_blocked",
    )
    assert grounded["business_status"] == "grounded"

    weak = verify_slot_evidence(
        "structure", "墙体倾斜",
        {"quote": "房子明显往一边斜", "source_ref": "u2"},
        BUSINESS_SOURCE_MAP, "dangerous_building",
    )
    assert weak["business_status"] == "unavailable"

    invalid = verify_slot_evidence(
        "structure", "墙体倾斜",
        {"quote": "墙体倾斜", "source_ref": "u9"},
        BUSINESS_SOURCE_MAP, "dangerous_building",
    )
    assert invalid["business_status"] == "rejected"


def test_wufa_is_not_misread_as_plain_negation():
    from core.uncertainty import verify_slot_evidence

    result = verify_slot_evidence(
        "impact", "无法进入",
        {"quote": "无法进入", "source_ref": "u1"},
        {"u1": "消防车无法进入小区"},
        "fire_lane_blocked",
    )
    assert result["status"] == "grounded"
