# Evidence-Grounded Slot Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add evidence quotes and deterministic source validation to slot extraction while preserving Java/MySQL/SSE contracts.

**Architecture:** Extend the planner with per-slot evidence, assign backend-owned source refs, validate quotes deterministically, persist evidence inside `issues`, and default to shadow mode.

**Tech Stack:** Python 3.11, pytest, existing LangGraph checkpoint and OpenAI-compatible planner.

## Global Constraints

- `SLOT_EVIDENCE_MODE` accepts `off`, `shadow`, `enforce`; default `shadow`.
- Evidence never enters SSE, report text, Java DTO, or frontend state.
- Only user and vision sources may ground facts; assistant sources are rejected.
- Source refs are backend-owned (`uN`, `vN`, `aN`), never invented by the model.
- Old checkpoints without evidence use the current `slot_status()` fallback.
- `echo` remains separate from `unverified`.
- No Skill or multi-hazard policy changes are included.

---

## File Structure

- Modify: `ai-module/config.py`
- Modify: `ai-module/core/dialogue_understanding.py`
- Modify: `ai-module/core/uncertainty.py`
- Modify: `ai-module/core/assistant_graph.py`
- Create: `ai-module/tests/test_slot_evidence.py`
- Modify: `ai-module/tests/test_graph_state_persistence.py`

---

### Task 1: Add Evidence Mode Configuration

**Files:**
- Modify: `ai-module/config.py`
- Test: `ai-module/tests/test_slot_evidence.py`

**Interfaces:**
- Produces: `config.SLOT_EVIDENCE_MODE: str`

- [ ] **Step 1: Write the failing test**

```python
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
    with pytest.raises(ValueError):
        importlib.reload(config)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_slot_evidence.py::test_slot_evidence_mode_defaults_to_shadow -q`

Expected: FAIL because the config constant is missing.

- [ ] **Step 3: Implement config**

```python
SLOT_EVIDENCE_MODE = os.getenv("SLOT_EVIDENCE_MODE", "shadow").strip().lower()
if SLOT_EVIDENCE_MODE not in {"off", "shadow", "enforce"}:
    raise ValueError(
        f"Unsupported SLOT_EVIDENCE_MODE={SLOT_EVIDENCE_MODE!r}; "
        "expected 'off', 'shadow', or 'enforce'"
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_slot_evidence.py -q -k evidence_mode`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/config.py ai-module/tests/test_slot_evidence.py
git commit -m "feat(ai): add slot evidence mode config"
```

---

### Task 2: Parse Evidence Contract

**Files:**
- Modify: `ai-module/core/dialogue_understanding.py`
- Test: `ai-module/tests/test_slot_evidence.py`

**Interfaces:**
- Consumes: `issues[].evidence` list
- Produces: each issue contains `evidence: list[dict]`

- [ ] **Step 1: Write the failing parser test**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_slot_evidence.py -q -k "parse_plan"`

Expected: FAIL because evidence is discarded.

- [ ] **Step 3: Implement evidence cleaning in `_issue_from_values`**

```python
def _clean_evidence(raw_evidence, allowed_slots, clean_slots):
    out = []
    for item in raw_evidence or []:
        if not isinstance(item, dict):
            continue
        slot = str(item.get("slot") or "").strip()
        quote = str(item.get("quote") or "").strip()
        source_ref = str(item.get("source_ref") or "").strip()
        if slot not in allowed_slots or slot not in clean_slots:
            continue
        if not quote or not source_ref:
            continue
        out.append({"slot": slot, "quote": quote, "source_ref": source_ref})
    return out[:len(allowed_slots)]
```

Pass `raw_evidence=item.get("evidence")` from `_issues_from_plan_items()` and include `"evidence": clean_evidence(...)` in the issue.

- [ ] **Step 4: Run parser tests**

Run: `python -m pytest tests/test_slot_evidence.py -q -k parse_plan`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/dialogue_understanding.py ai-module/tests/test_slot_evidence.py
git commit -m "feat(ai): parse slot evidence contract"
```

---
### Task 3: Assign Stable Source Refs

**Files:**
- Modify: `ai-module/core/dialogue_understanding.py`
- Test: `ai-module/tests/test_slot_evidence.py`

**Interfaces:**
- Produces: `build_source_map(messages, vision_summary) -> dict[str, str]`
- Produces: planner messages prefixed with `[uN]`, `[vN]`, `[aN]`

- [ ] **Step 1: Write failing source-ref tests**

```python
from langchain_core.messages import AIMessage, HumanMessage
from core.dialogue_understanding import build_source_map, build_planner_messages


def test_source_map_prefixes():
    messages = [HumanMessage(content="红色"), AIMessage(content="收到"), HumanMessage(content="配电箱冒火花")]
    source_map = build_source_map(messages, "[视觉分析] 配电箱外观破损")
    assert source_map["u1"] == "红色"
    assert source_map["a1"] == "收到"
    assert source_map["u2"] == "配电箱冒火花"
    assert source_map["v1"] == "[视觉分析] 配电箱外观破损"


def test_planner_messages_expose_refs():
    built = build_planner_messages([HumanMessage(content="房子往一边斜")], "[视觉分析] 外墙裂缝")
    combined = "\n".join(item["content"] for item in built)
    assert "[u1] 房子往一边斜" in combined
    assert "[v1] [视觉分析] 外墙裂缝" in combined
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_slot_evidence.py -q -k "source_map or planner_messages"`

Expected: FAIL because refs are absent.

- [ ] **Step 3: Implement source refs**

```python
def build_source_map(messages, vision_summary=""):
    source_map = {}
    user_index = assistant_index = 0
    for message in messages or []:
        role = getattr(message, "type", "")
        content = getattr(message, "content", str(message))
        if role == "human":
            user_index += 1
            source_map[f"u{user_index}"] = str(content)
        elif role == "ai":
            assistant_index += 1
            source_map[f"a{assistant_index}"] = str(content)
    if vision_summary:
        source_map["v1"] = str(vision_summary)
    return source_map
```

`build_planner_messages()` must prefix each appended user/assistant message with its source ref and prefix the vision system message with `[v1]`.

- [ ] **Step 4: Run source-ref and planner regressions**

Run: `python -m pytest tests/test_slot_evidence.py -q -k "source_map or planner_messages" tests/test_semantic_dialogue.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/dialogue_understanding.py ai-module/tests/test_slot_evidence.py
git commit -m "feat(ai): assign planner evidence source refs"
```

---

### Task 4: Implement Deterministic Evidence Verifier

**Files:**
- Modify: `ai-module/core/uncertainty.py`
- Test: `ai-module/tests/test_slot_evidence.py`

**Interfaces:**
- Produces: `verify_slot_evidence(slot_key, value, evidence, source_map, category) -> dict`

- [ ] **Step 1: Write failing verifier tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_slot_evidence.py -q -k "quote_support or invalid_and_assistant"`

Expected: FAIL because verifier is missing.

- [ ] **Step 3: Implement verifier**

```python
def verify_slot_evidence(slot_key, value, evidence, source_map, category):
    value = str(value or "").strip()
    if not value:
        return {"status": "missing", "reason": "empty_value"}

    evidence = evidence if isinstance(evidence, dict) else {}
    quote = str(evidence.get("quote") or "").strip()
    source_ref = str(evidence.get("source_ref") or "").strip()
    if not quote:
        return {"status": "unverified", "reason": "no_evidence"}
    if source_ref not in source_map:
        return {"status": "unverified", "reason": "invalid_source_ref"}
    if source_ref.startswith("a"):
        return {"status": "unverified", "reason": "assistant_source"}

    source = source_map[source_ref]
    quote_norm = normalize_text(quote)
    source_norm = normalize_text(source)
    if not quote_norm or quote_norm not in source_norm:
        return {"status": "unverified", "reason": "quote_not_found",
                "quote": quote, "source_ref": source_ref}
    if not _digits_preserved(value, quote):
        return {"status": "unverified", "reason": "numeric_mismatch",
                "quote": quote, "source_ref": source_ref}

    value_norm = normalize_text(value)
    if value_norm and value_norm in quote_norm:
        return {"status": "grounded", "reason": "", "value": value,
                "quote": quote, "source_ref": source_ref}
    return {"status": "weak", "reason": "value_not_in_quote", "value": value,
            "quote": quote, "source_ref": source_ref}
```

- [ ] **Step 4: Run verifier tests**

Run: `python -m pytest tests/test_slot_evidence.py -q -k "quote_support or invalid_and_assistant"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/uncertainty.py ai-module/tests/test_slot_evidence.py
git commit -m "feat(ai): add deterministic evidence verifier"
```

---
### Task 5: Integrate Verification Into assess()

**Files:**
- Modify: `ai-module/core/uncertainty.py`
- Test: `ai-module/tests/test_slot_evidence.py`

**Interfaces:**
- Consumes: issue-level `evidence`
- Produces: `slot_evidence_audit`, `ungrounded_slots`, `grounding_ratio`

- [ ] **Step 1: Write failing assess tests**

```python
from core.uncertainty import assess


def test_assess_uses_evidence_and_legacy_fallback():
    plan = {
        "ok": True,
        "issues": [{
            "subcategory_code": "dangerous_building",
            "slots": {"structure": "墙体倾斜"},
            "evidence": [{"slot": "structure", "quote": "房子明显往一边斜", "source_ref": "u1"}],
        }],
    }
    result = assess(plan, [{"role": "user", "content": "房子明显往一边斜"}])
    audit = result["slot_evidence_audit"]["dangerous_building"]["structure"]
    assert audit["status"] == "weak"
    assert result["uncertainty_level"] == "ok"

    legacy = assess(
        {"ok": True, "issues": [{"subcategory_code": "fire_lane_blocked", "slots": {"persistence": "持续中"}}]},
        [{"role": "user", "content": "楼道里全是浓烟"}],
    )
    assert legacy["ungrounded_slots"] == ["fire_lane_blocked.persistence=持续中"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_slot_evidence.py::test_assess_uses_evidence_and_legacy_fallback -q`

Expected: FAIL because `assess()` does not consume evidence.

- [ ] **Step 3: Integrate evidence path**

```python
def assess(plan, messages, vision_summary=""):
    source_map = build_source_map(messages, vision_summary)
    source_map["__joined__"] = " ".join(
        value for key, value in source_map.items() if key.startswith("u")
    ) + (" " + vision_summary if vision_summary else "")
    evidence_audit = {}
    ungrounded = []
    for issue in plan.get("issues") or []:
        code = issue.get("subcategory_code") or ""
        evidence_by_slot = {
            item.get("slot"): item
            for item in (issue.get("evidence") or [])
            if isinstance(item, dict)
        }
        for key, value in (issue.get("slots") or {}).items():
            if not str(value or "").strip():
                continue
            typed = evidence_by_slot.get(key)
            if typed:
                result = verify_slot_evidence(key, value, typed, source_map, code)
            else:
                result = {"status": slot_status(value, source_map["__joined__"]), "reason": "legacy"}
            evidence_audit.setdefault(code, {})[key] = result
            if result["status"] == "unverified":
                ungrounded.append(f"{code}.{key}={value}")
    # Retain existing danger, major_mismatch, signals, and ratio computation.
```

- [ ] **Step 4: Run evidence and uncertainty regressions**

Run: `python -m pytest tests/test_slot_evidence.py tests/test_uncertainty.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/uncertainty.py ai-module/tests/test_slot_evidence.py
git commit -m "feat(ai): consume slot evidence in uncertainty assessment"
```

---

### Task 6: Persist Evidence And Preserve Legacy Checkpoints

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Test: `ai-module/tests/test_graph_state_persistence.py`
- Test: `ai-module/tests/test_slot_evidence.py`

**Interfaces:**
- Consumes: `verdict["slot_evidence_audit"]`
- Produces: `issue["evidence"]` and `issue["slot_evidence"]`

- [ ] **Step 1: Write failing evidence persistence test**

```python
def test_slot_evidence_survives_issue_merge():
    from core.assistant_graph import _merge_persisted_slots
    issues = [{
        "subcategory_code": "dangerous_building",
        "slots": {"structure": "墙体倾斜"},
        "evidence": [{"slot": "structure", "quote": "往一边斜", "source_ref": "u1"}],
    }]
    merged = _merge_persisted_slots(issues, {"dangerous_building": {}})
    assert merged[0]["evidence"][0]["source_ref"] == "u1"
```

- [ ] **Step 2: Run test**

Run: `python -m pytest tests/test_slot_evidence.py::test_slot_evidence_survives_issue_merge -q`

Expected: PASS only after evidence survives `_merge_persisted_slots()`.

- [ ] **Step 3: Preserve evidence and write audit**

`_merge_persisted_slots()` must keep the issue's `evidence` list. In `understand()`, after per-issue `unverified` assignment:

```python
audit_by_issue = verdict.get("slot_evidence_audit") or {}
for issue in issues:
    code = issue["subcategory_code"]
    issue["slot_evidence"] = dict(audit_by_issue.get(code) or {})
```

When `echo_slots()` removes a slot, remove its corresponding evidence entry too.

- [ ] **Step 4: Run persistence tests**

Run: `python -m pytest tests/test_graph_state_persistence.py tests/test_slot_evidence.py::test_slot_evidence_survives_issue_merge -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/assistant_graph.py ai-module/tests/test_graph_state_persistence.py ai-module/tests/test_slot_evidence.py
git commit -m "feat(ai): persist slot evidence in issue state"
```

---

### Task 7: Shadow/Enforce Rollout And Leakage Checks

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Test: `ai-module/tests/test_slot_evidence.py`

**Interfaces:**
- Consumes: `config.SLOT_EVIDENCE_MODE`
- Produces: behavior-preserving shadow mode and evidence-driven enforce mode

- [ ] **Step 1: Write failing rollout test**

```python
def test_shadow_mode_preserves_legacy_unverified(monkeypatch):
    import core.assistant_graph as ag
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "shadow")
    verdict = {
        "ungrounded_slots": ["fire_lane_blocked.persistence=持续中"],
        "slot_evidence_audit": {"fire_lane_blocked": {"persistence": {"status": "unverified"}}},
    }
    assert ag._effective_ungrounded_slots(verdict) == ["fire_lane_blocked.persistence=持续中"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_slot_evidence.py::test_shadow_mode_preserves_legacy_unverified -q`

Expected: FAIL because the helper does not exist.

- [ ] **Step 3: Implement rollout gate and log audit**

```python
def _effective_ungrounded_slots(verdict):
    from config import SLOT_EVIDENCE_MODE
    legacy = list(verdict.get("ungrounded_slots") or [])
    if SLOT_EVIDENCE_MODE in {"off", "shadow"}:
        return legacy
    audit = verdict.get("slot_evidence_audit") or {}
    effective = [
        f"{code}.{slot}={result.get('value', '')}"
        for code, slots in audit.items()
        for slot, result in slots.items()
        if result.get("status") == "unverified"
    ]
    return effective or legacy
```

Use `logger.info("slot_evidence_audit=%s", audit)` only in shadow mode; never add audit to SSE.

- [ ] **Step 4: Run evidence and critical regressions**

Run: `python -m pytest tests/test_slot_evidence.py tests/test_uncertainty.py tests/test_uncertainty_gating.py tests/test_echo_slots.py tests/test_graph_state_persistence.py tests/test_task_gate_interrupt.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/assistant_graph.py ai-module/tests/test_slot_evidence.py
git commit -m "feat(ai): gate slot evidence rollout"
```

---

## Self-Review Checklist

- [ ] Config default and invalid value are tested.
- [ ] Evidence parsing and source-ref assignment are tested.
- [ ] Verifier covers grounded, weak, unverified, invalid source, assistant source, and numeric mismatch.
- [ ] `assess()` keeps legacy fallback without evidence.
- [ ] Evidence survives issue merge and checkpoint persistence.
- [ ] Shadow mode preserves current behavior.
- [ ] Evidence is not sent in SSE or report text.
- [ ] No Skill or multi-hazard policy changes are included.