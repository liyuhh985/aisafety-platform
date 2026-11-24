# Semantic Grounding Verifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual confirmation for valid-quote but non-literal slot values with one batched semantic-verifier call inside `understand`, using four business states and class-specific confidence thresholds.

**Architecture:** Keep the LangGraph topology unchanged. After deterministic evidence validation identifies `weak` slots, `understand` makes at most one independent `temperature=0` verifier call for up to five candidates. High-confidence entailment becomes `grounded_by_model`; high-confidence contradiction becomes `rejected`; all other outcomes become `unavailable`. Unusable slots are removed before missing/report-missing recomputation, so A-class slots are re-asked and B-class slots become conditional report material.

**Tech Stack:** Python 3.11, pytest, existing `Agent`, LangGraph `understand` node, existing slot A/B/C schema.

## Global Constraints

- Do not add a LangGraph node.
- Do not add a user-confirmation turn or confirmation question.
- Only call the semantic verifier when `SLOT_EVIDENCE_MODE=enforce`.
- `off` and `shadow` must preserve existing behavior and make no extra verifier call.
- One verifier call per turn, maximum five candidates, A-class slots before B-class slots.
- Verifier input must not include full conversation history or tools.
- Verifier temperature must be `0.0`.
- Business states are exactly `grounded`, `grounded_by_model`, `rejected`, `unavailable`.
- Detailed reasons remain internal in `reason` and are not exposed to SSE or reports.
- Invalid quote/source, deterministic contradiction, and verifier contradiction are `rejected`.
- Direct quote support is `grounded`; model entailment above threshold is `grounded_by_model`.
- Weak/neutral/verifier failure/echo/missing are `unavailable`.
- A-class threshold is stricter than B-class threshold.
- Evidence fields must remain absent from SSE, interrupt payloads, report prompts, and report text.
- Existing off/shadow behavior, checkpoint compatibility, and Java/MySQL contracts remain unchanged.
- The separate focus/question-policy plan must make question selection scan all active issues. This plan only guarantees that unusable A slots return to `missing`.

---

## File Structure

- Modify: `ai-module/core/agent.py` — optional temperature parameter.
- Create: `ai-module/core/semantic_verifier.py` — candidate collection, verifier prompt, batch parsing, status application.
- Modify: `ai-module/core/uncertainty.py` — business status mapping and enforce-mode uncertainty semantics.
- Modify: `ai-module/core/assistant_graph.py` — call verifier inside `understand`, drop unusable slots, recompute missing/report-missing.
- Modify: `ai-module/config.py` — A/B thresholds and max batch size.
- Modify: `ai-module/.env.example` — verifier configuration.
- Create: `ai-module/tests/test_semantic_verifier.py` — module and integration tests.
- Modify: `ai-module/tests/test_slot_evidence.py` — business-state regressions.
- Modify: `docs/current/agent-orchestration.md` — document the semantic verifier after implementation.

---

### Task 1: Add Optional Temperature To Agent

**Files:**
- Modify: `ai-module/core/agent.py`
- Test: `ai-module/tests/test_semantic_verifier.py`

**Interfaces:**
- Produces: `Agent(..., temperature: float = 0.3)`
- Produces: payload temperature from `self.temperature`

- [ ] **Step 1: Write the failing test**

```python
from core.agent import Agent


def test_agent_honors_temperature_zero():
    agent = Agent(
        name="semantic_verifier",
        system_prompt="VERIFY",
        tools=[],
        base_url="http://example.invalid",
        api_key="k",
        model="m",
        temperature=0.0,
    )
    payload = agent._build_payload([{"role": "user", "content": "q"}], stream=False)
    assert payload["temperature"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_semantic_verifier.py::test_agent_honors_temperature_zero -q`

Expected: FAIL because `Agent` does not accept `temperature`.

- [ ] **Step 3: Implement temperature**

In `Agent.__init__`, add `temperature: float = 0.3` and store `self.temperature = float(temperature)`.

In `_build_payload()`:

```python
payload = {
    "model": self.model,
    "messages": payload_messages,
    "temperature": self.temperature,
}
```

Existing agents keep the current `0.3` default.

- [ ] **Step 4: Run test and existing agent regressions**

Run: `python -m pytest tests/test_semantic_verifier.py::test_agent_honors_temperature_zero tests/test_agent_hardening.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/agent.py ai-module/tests/test_semantic_verifier.py
git commit -m "feat(ai): allow deterministic agent temperature"
```

---

### Task 2: Add Four Business States And Internal Reasons

**Files:**
- Modify: `ai-module/core/uncertainty.py`
- Test: `ai-module/tests/test_slot_evidence.py`

**Interfaces:**
- Produces: `business_status` on every slot evidence audit result.
- Preserves detailed `status` and `reason` internally.

- [ ] **Step 1: Write failing business-state tests**

```python
from core.uncertainty import verify_slot_evidence

SOURCE_MAP = {
    "u1": "消防通道长期堆着杂物",
    "u2": "房子明显往一边斜",
    "a1": "我理解为墙体倾斜",
}


def test_business_status_mapping():
    grounded = verify_slot_evidence(
        "persistence", "长期",
        {"quote": "长期堆着", "source_ref": "u1"},
        SOURCE_MAP, "fire_lane_blocked",
    )
    assert grounded["business_status"] == "grounded"

    weak = verify_slot_evidence(
        "structure", "墙体倾斜",
        {"quote": "房子明显往一边斜", "source_ref": "u2"},
        SOURCE_MAP, "dangerous_building",
    )
    assert weak["business_status"] == "unavailable"

    invalid = verify_slot_evidence(
        "structure", "墙体倾斜",
        {"quote": "墙体倾斜", "source_ref": "u9"},
        SOURCE_MAP, "dangerous_building",
    )
    assert invalid["business_status"] == "rejected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_slot_evidence.py::test_business_status_mapping -q`

Expected: FAIL because `business_status` is missing.

- [ ] **Step 3: Implement mapping**

```python
def business_status_for(result):
    status = str((result or {}).get("status") or "")
    if status in {"grounded", "grounded_by_model"}:
        return status
    if status in {"contradicted", "unverified"}:
        return "rejected"
    if status == "strong" and (result or {}).get("reason") == "legacy":
        return "unavailable"
    return "unavailable"
```

Apply it to every return path of `verify_slot_evidence`, including early returns. In `assess()`, whenever a result is constructed from legacy fallback (`reason="legacy"`), call `business_status_for(result)` before storing it in the audit. Do not change the detailed `status` values yet.

- [ ] **Step 4: Run business-state and legacy tests**

Run: `python -m pytest tests/test_slot_evidence.py tests/test_uncertainty.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/uncertainty.py ai-module/tests/test_slot_evidence.py
git commit -m "feat(ai): add semantic grounding business states"
```

---
### Task 3: Implement Batched Semantic Verifier

**Files:**
- Create: `ai-module/core/semantic_verifier.py`
- Create: `ai-module/tests/test_semantic_verifier.py`

**Interfaces:**
- Produces: `collect_weak_candidates(issues, audit, max_items=5) -> list[dict]`
- Produces: `verify_weak_slots(issues, audit, cancellation=None) -> dict`
- Verifier result keys: `id`, `relation`, `confidence`, `reason`.

- [ ] **Step 1: Write failing verifier tests**

```python
import pytest
from core.semantic_verifier import collect_weak_candidates, verify_weak_slots


def _issue(code="fire_lane_blocked", slots=None):
    return {
        "major_code": "fire",
        "subcategory_code": code,
        "slots": slots or {"blocker": "杂物", "persistence": "长期"},
    }


def _audit(**weak_slots):
    return {"fire_lane_blocked": {
        key: {"status": "weak", "business_status": "unavailable",
              "value": value, "quote": "原文", "source_ref": "u1"}
        for key, value in weak_slots.items()
    }}


def test_collect_candidates_prioritizes_a_and_caps_five(monkeypatch):
    from core import semantic_verifier as sv
    audit = _audit(blocker="杂物", persistence="长期", impact="影响通行")
    issues = [_issue()]
    candidates = collect_weak_candidates(issues, audit)
    assert candidates[0]["value_class"] == "A"
    assert len(candidates) <= 5


def test_verifier_calls_model_once_and_applies_statuses(monkeypatch):
    from core import semantic_verifier as sv
    calls = []

    def fake_llm(messages, cancellation=None):
        calls.append(messages)
        return {"content": '''[
          {"id":"fire_lane_blocked:blocker","relation":"entailed","confidence":0.95},
          {"id":"fire_lane_blocked:persistence","relation":"neutral","confidence":0.5}
        ]'''}

    monkeypatch.setattr(sv._semantic_verifier_agent, "_call_llm", fake_llm)
    audit = _audit(blocker="杂物", persistence="长期")
    result = verify_weak_slots([_issue()], audit)
    assert len(calls) == 1
    assert result["fire_lane_blocked"]["blocker"]["business_status"] == "grounded_by_model"
    assert result["fire_lane_blocked"]["persistence"]["business_status"] == "unavailable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "collect_candidates or calls_model_once"`

Expected: FAIL because the module is missing.

- [ ] **Step 3: Implement candidate collection**

```python
from core.slot_schemas import DECISION_CLASS, get_slot_schema

MAX_SEMANTIC_CANDIDATES = 5


def _slot_question(category, slot_key):
    return next(
        (slot.question for slot in get_slot_schema(category) if slot.key == slot_key),
        "",
    )


def _slot_class(category, slot_key):
    return next(
        (slot.value_class for slot in get_slot_schema(category) if slot.key == slot_key),
        "B",
    )


def collect_weak_candidates(issues, audit, max_items=MAX_SEMANTIC_CANDIDATES):
    candidates = []
    for issue in issues or []:
        code = str(issue.get("subcategory_code") or "")
        for slot_key, value in (issue.get("slots") or {}).items():
            result = ((audit.get(code) or {}).get(slot_key) or {})
            if result.get("status") != "weak":
                continue
            quote = str(result.get("quote") or "")
            source_ref = str(result.get("source_ref") or "")
            if not quote or source_ref[:1] not in {"u", "v"}:
                continue
            value_class = _slot_class(code, slot_key)
            candidates.append({
                "id": f"{code}:{slot_key}",
                "category": code,
                "slot": slot_key,
                "slot_question": _slot_question(code, slot_key),
                "value": str(value),
                "quote": quote,
                "source_ref": source_ref,
                "value_class": value_class,
            })
    candidates.sort(key=lambda item: 0 if item["value_class"] == DECISION_CLASS else 1)
    return candidates[:max_items]
```

- [ ] **Step 4: Implement one-call JSON verifier**

Create an independent small agent:

```python
from config import MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL
from core.agent import Agent

_semantic_verifier_agent = Agent(
    name="semantic_verifier",
    system_prompt="你是槽位证据语义复核器，只判断 quote 是否支持 value。",
    tools=[],
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
    slot="small",
    temperature=0.0,
)
```

Call once with only the candidate list and require:

```json
[
  {"id":"fire_lane_blocked:blocker","relation":"entailed","confidence":0.95}
]
```

Build the prompt with no conversation history:

```python
def _build_verifier_prompt(candidates):
    payload = [
        {
            "id": item["id"],
            "slot": item["slot"],
            "slot_question": item["slot_question"],
            "value": item["value"],
            "quote": item["quote"],
        }
        for item in candidates
    ]
    return (
        "只判断 quote 是否支持 value，不重新抽取事实。"
        "relation 只能是 entailed / contradicted / unknown。"
        "entailed 表示 quote 足以支持 value；contradicted 表示 quote 明确否定 value；"
        "其余情况返回 unknown。confidence 必须在 0 到 1。"
        "只返回 JSON 数组，每项包含 id、relation、confidence。\n"
        + json.dumps(payload, ensure_ascii=False)
    )
```

Parsing must accept only `entailed`, `contradicted`, `unknown`; missing id, duplicate id, non-list response, invalid JSON, or invalid confidence becomes `unavailable`.

- [ ] **Step 5: Apply thresholds and mutate audit**

```python
A_THRESHOLD = 0.90
B_THRESHOLD = 0.82


def _threshold(value_class):
    return A_THRESHOLD if value_class == DECISION_CLASS else B_THRESHOLD


def _apply_one(result, verdict, threshold):
    relation = str(verdict.get("relation") or "unknown")
    confidence = float(verdict.get("confidence") or 0.0)
    result["relation"] = relation
    result["confidence"] = confidence
    if relation == "entailed" and confidence >= threshold:
        result["status"] = "grounded_by_model"
        result["business_status"] = "grounded_by_model"
        result["reason"] = "model_entailed"
    elif relation == "contradicted" and confidence >= threshold:
        result["status"] = "rejected"
        result["business_status"] = "rejected"
        result["reason"] = "model_contradicted"
    else:
        result["status"] = "unavailable"
        result["business_status"] = "unavailable"
        result["reason"] = f"model_{relation}_below_threshold"
```

If the batch call throws or parsing fails, mark every candidate:

```python
result["status"] = "unavailable"
result["business_status"] = "unavailable"
result["reason"] = "verifier_failed"
```

The orchestration entry point is:

```python
def verify_weak_slots(issues, audit, cancellation=None):
    candidates = collect_weak_candidates(
        issues, audit,
        max_items=SEMANTIC_VERIFIER_MAX_ITEMS,
    )
    if not candidates:
        return audit

    try:
        response = _semantic_verifier_agent._call_llm(
            [{"role": "user", "content": _build_verifier_prompt(candidates)}],
            cancellation=cancellation,
        )
        verdicts = _parse_verifier_output((response or {}).get("content") or "")
    except Exception:
        verdicts = {}

    for candidate in candidates:
        result = audit[candidate["category"]][candidate["slot"]]
        verdict = verdicts.get(candidate["id"])
        if verdict is None:
            result["status"] = "unavailable"
            result["business_status"] = "unavailable"
            result["reason"] = "verifier_failed"
            continue
        _apply_one(result, verdict, _threshold(candidate["value_class"]))
    return audit
```

`_parse_verifier_output()` must return a dict keyed by id only after validating list shape, relation enum, confidence range, and duplicate ids:

```python
import json
import re

_RELATIONS = {"entailed", "contradicted", "unknown"}


def _parse_verifier_output(content):
    text = str(content or "").strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return {}
    try:
        rows = json.loads(match.group(0))
    except (TypeError, ValueError):
        return {}
    if not isinstance(rows, list):
        return {}
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("id") or "").strip()
        relation = str(row.get("relation") or "").strip().lower()
        if not item_id or item_id in out or relation not in _RELATIONS:
            continue
        try:
            confidence = float(row.get("confidence"))
        except (TypeError, ValueError):
            continue
        if not 0.0 <= confidence <= 1.0:
            continue
        out[item_id] = {"relation": relation, "confidence": confidence}
    return out
```

- [ ] **Step 6: Run verifier tests**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "collect_candidates or calls_model_once"`

Expected: PASS.

- [ ] **Step 7: Add edge tests**

Add tests for:

```text
entailed A=0.89 -> unavailable
entailed B=0.85 -> grounded_by_model
contradicted A=0.95 -> rejected
unknown=0.99 -> unavailable
timeout / bad JSON -> unavailable
more than five weak slots -> verifier receives only the first five
```

- [ ] **Step 8: Run all semantic verifier tests**

Run: `python -m pytest tests/test_semantic_verifier.py -q`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add ai-module/core/semantic_verifier.py ai-module/tests/test_semantic_verifier.py
git commit -m "feat(ai): add batched semantic grounding verifier"
```

---

### Task 4: Configure A/B Thresholds And Batch Limit

**Files:**
- Modify: `ai-module/config.py`
- Modify: `ai-module/.env.example`
- Modify: `ai-module/core/semantic_verifier.py`
- Test: `ai-module/tests/test_semantic_verifier.py`

**Interfaces:**
- Produces: `SEMANTIC_VERIFIER_A_THRESHOLD`
- Produces: `SEMANTIC_VERIFIER_B_THRESHOLD`
- Produces: `SEMANTIC_VERIFIER_MAX_ITEMS`

- [ ] **Step 1: Write failing config test**

```python
def test_semantic_verifier_threshold_config():
    from config import (
        SEMANTIC_VERIFIER_A_THRESHOLD,
        SEMANTIC_VERIFIER_B_THRESHOLD,
        SEMANTIC_VERIFIER_MAX_ITEMS,
    )
    assert SEMANTIC_VERIFIER_A_THRESHOLD == 0.90
    assert SEMANTIC_VERIFIER_B_THRESHOLD == 0.82
    assert SEMANTIC_VERIFIER_MAX_ITEMS == 5
```

- [ ] **Step 2: Implement config and env**

In `config.py`:

```python
SEMANTIC_VERIFIER_A_THRESHOLD = float(
    os.getenv("SEMANTIC_VERIFIER_A_THRESHOLD", "0.90")
)
SEMANTIC_VERIFIER_B_THRESHOLD = float(
    os.getenv("SEMANTIC_VERIFIER_B_THRESHOLD", "0.82")
)
SEMANTIC_VERIFIER_MAX_ITEMS = int(
    os.getenv("SEMANTIC_VERIFIER_MAX_ITEMS", "5")
)
```

In `.env.example`:

```ini
SEMANTIC_VERIFIER_A_THRESHOLD=0.90
SEMANTIC_VERIFIER_B_THRESHOLD=0.82
SEMANTIC_VERIFIER_MAX_ITEMS=5
```

Make `semantic_verifier.py` read these config values at call time so tests can monkeypatch them.

- [ ] **Step 3: Run config and threshold tests**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "threshold or config"`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add ai-module/config.py ai-module/.env.example ai-module/core/semantic_verifier.py ai-module/tests/test_semantic_verifier.py
git commit -m "feat(ai): configure semantic verifier thresholds"
```

---
### Task 5: Apply Semantic Results Inside understand And Recompute Missing

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Modify: `ai-module/core/uncertainty.py`
- Test: `ai-module/tests/test_semantic_verifier.py`

**Interfaces:**
- Consumes: `slot_evidence_audit` and `business_status`
- Produces: final `issue["slots"]`, `missing`, `report_missing`, `issue["unverified"]`

- [ ] **Step 1: Write failing integration tests**

```python
def test_a_unavailable_slot_returns_to_missing(monkeypatch):
    import core.assistant_graph as ag
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "enforce")
    monkeypatch.setattr(ag, "verify_weak_slots", lambda issues, audit, cancellation=None: _mark(
        audit, "fire_lane_blocked", "blocker", "unavailable"
    ))
    state = {
        "messages": [ag.HumanMessage(content="消防通道有东西堵着")],
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物"}},
        "active_skills": ["fire"],
    }
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "杂物"},
            "evidence": [{"slot": "blocker", "quote": "有东西", "source_ref": "u1"}],
        }],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物"}},
        "question": "", "answer": "", "needs_search": False,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: plan)
    out = ag.understand(state)
    assert "fire_lane_blocked_blocker" in out["missing"]
    assert "请确认" not in (out.get("clarification_question") or "")


def test_b_unavailable_slot_becomes_report_missing(monkeypatch):
    import core.assistant_graph as ag
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "enforce")
    monkeypatch.setattr(ag, "verify_weak_slots", lambda issues, audit, cancellation=None: _mark(
        audit, "fire_lane_blocked", "impact", "unavailable"
    ))
    state = {
        "messages": [ag.HumanMessage(content="消防通道长期被杂物堵住")],
        "category_slots": {"fire_lane_blocked": {
            "blocker": "杂物", "persistence": "长期", "impact": "影响通行"
        }},
        "active_skills": ["fire"],
    }
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "杂物", "persistence": "长期", "impact": "影响通行"},
            "evidence": [{"slot": "impact", "quote": "影响通行", "source_ref": "u1"}],
        }],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {
            "blocker": "杂物", "persistence": "长期", "impact": "影响通行"
        }},
        "question": "", "answer": "", "needs_search": True,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: plan)
    out = ag.understand(state)
    assert "fire_lane_blocked_blocker" not in out["missing"]
    assert "impact" in out["issues"][0]["report_missing"]
```

Helper used by tests:

```python
def _mark(audit, code, slot, business_status):
    audit[code][slot]["status"] = business_status
    audit[code][slot]["business_status"] = business_status
    return audit
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "a_unavailable or b_unavailable"`

Expected: FAIL because unusable slots are not removed and missing is not recomputed.

- [ ] **Step 3: Add helper functions**

```python
def _drop_unusable_slots(issues, category_slots, audit):
    removed = []
    for issue in issues:
        code = issue.get("subcategory_code") or ""
        for slot_key in list((issue.get("slots") or {}).keys()):
            result = ((audit.get(code) or {}).get(slot_key) or {})
            if result.get("business_status") not in {"rejected", "unavailable"}:
                continue
            issue["slots"].pop(slot_key, None)
            category_slots.setdefault(code, {}).pop(slot_key, None)
            removed.append(f"{code}.{slot_key}")
    return removed
```

```python
def _rebuild_issue_missing(issues, category_slots):
    categories = [issue["subcategory_code"] for issue in issues]
    missing = rebuild_missing(categories, category_slots)
    report_missing = rebuild_report_missing(categories, category_slots)
    for issue in issues:
        code = issue["subcategory_code"]
        issue["missing"] = [
            slot.key for slot in get_slot_schema(code)
            if f"{code}_{slot.key}" in missing
        ]
        issue["report_missing"] = [
            slot.key for slot in get_slot_schema(code)
            if f"{code}_{slot.key}" in report_missing
        ]
    return missing
```

- [ ] **Step 4: Call the verifier and drop unusable slots before policy**

Remove the existing early `category_slots / missing / report_missing` block and move it after semantic verification. `assess()` must run on the finalized issue list before missing is rebuilt.

In `understand()`, after `issues = _active_issues(...)` and `plan["issues"] = issues`:

```python
verdict = _apply_evidence_mode(assess(plan, source_messages, vision_summary))
if SLOT_EVIDENCE_MODE == "enforce":
    verdict["slot_evidence_audit"] = verify_weak_slots(
        issues,
        verdict.get("slot_evidence_audit") or {},
        _cancel_token(config),
    )
```

Before `decide_next_action()`:

```python
category_slots = dict(state.get("category_slots") or {})
for issue in issues:
    category_slots[issue["subcategory_code"]] = dict(issue.get("slots") or {})
removed = _drop_unusable_slots(issues, category_slots, verdict.get("slot_evidence_audit") or {})
if removed:
    logger.info("evidence_slots_removed slots=%s", removed)
missing = _rebuild_issue_missing(issues, category_slots)
```

Return the recomputed `missing` and updated `issue["missing"] / issue["report_missing"]`. Do not call the verifier again later in the turn.

- [ ] **Step 5: Make enforce-mode uncertainty question-friendly**

In `uncertainty.assess()`, keep `legacy_uncertainty_level` for shadow/off. For business evidence, do not turn `unavailable` or `rejected` into `cautious`; those slots are converted to `missing` and must remain askable.

Recommended final behavior:

```python
evidence_cautions = bool(plan.get("major_mismatch"))
```

`_apply_evidence_mode()` must still preserve legacy caution in `off` and `shadow`.

- [ ] **Step 6: Set issue unverified based on mode**

In `understand()`:

```python
if SLOT_EVIDENCE_MODE == "enforce":
    issue["unverified"] = []
else:
    issue["unverified"] = unverified.get(issue["subcategory_code"], [])
```

This prevents unusable A/B slots from suppressing the normal missing/report paths. A-class slots have already been moved to `missing`; B-class slots are in `report_missing`.

- [ ] **Step 7: Run focused integration tests**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "a_unavailable or b_unavailable" tests/test_uncertainty.py tests/test_uncertainty_gating.py -q`

Expected: PASS.

- [ ] **Step 8: Add `grounded_by_model` accepted-slot test**

```python
def test_grounded_by_model_remains_usable(monkeypatch):
    import core.assistant_graph as ag
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "enforce")
    monkeypatch.setattr(
        ag,
        "verify_weak_slots",
        lambda issues, audit, cancellation=None: _mark(
            audit, "fire_lane_blocked", "blocker", "grounded_by_model"
        ),
    )
    state = {
        "messages": [ag.HumanMessage(content="消防通道有东西堵着")],
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物"}},
        "active_skills": ["fire"],
    }
    plan = {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "fire", "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "杂物"},
            "evidence": [{"slot": "blocker", "quote": "有东西", "source_ref": "u1"}],
        }],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {"blocker": "杂物"}},
        "question": "", "answer": "", "needs_search": False,
    }
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: plan)
    out = ag.understand(state)
    assert "blocker" in out["issues"][0]["slots"]
    assert "fire_lane_blocked_blocker" not in out["missing"]
```

Add equivalent assertions for `rejected` removal and verifier exception:
- rejected slot is absent from `issue["slots"]`;
- verifier exception leaves weak slots `unavailable` and absent from usable slots;
- no evidence fields appear in public/SSE outputs.

- [ ] **Step 9: Commit**

```bash
git add ai-module/core/assistant_graph.py ai-module/core/uncertainty.py ai-module/tests/test_semantic_verifier.py
git commit -m "feat(ai): apply semantic grounding inside understand"
```

---

### Task 6: Preserve Shadow/Off Behavior And SSE Boundary

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Test: `ai-module/tests/test_semantic_verifier.py`
- Test: `ai-module/tests/test_slot_evidence.py`
- Test: `ai-module/tests/test_task_gate_interrupt.py`

**Interfaces:**
- Guarantees no verifier call and no slot removal outside enforce.

- [ ] **Step 1: Write failing shadow/off tests**

```python
def _shadow_plan():
    return {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "building", "subcategory_code": "dangerous_building",
            "slots": {"structure": "墙体倾斜"},
            "evidence": [{
                "slot": "structure", "quote": "房子明显往一边斜", "source_ref": "u1",
            }],
        }],
        "categories": ["dangerous_building"],
        "category_slots": {"dangerous_building": {"structure": "墙体倾斜"}},
        "question": "", "answer": "", "needs_search": True,
        "perceived_subcategory": "dangerous_building",
    }


def test_shadow_does_not_call_semantic_verifier(monkeypatch):
    import core.assistant_graph as ag
    calls = []
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "shadow")
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _shadow_plan())
    monkeypatch.setattr(ag, "verify_weak_slots", lambda *a, **k: calls.append(1) or {})
    ag.understand({"messages": [ag.HumanMessage(content="房子明显往一边斜")]})
    assert calls == []


def test_off_does_not_call_semantic_verifier(monkeypatch):
    import core.assistant_graph as ag
    calls = []
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "off")
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _shadow_plan())
    monkeypatch.setattr(ag, "verify_weak_slots", lambda *a, **k: calls.append(1) or {})
    ag.understand({"messages": [ag.HumanMessage(content="房子明显往一边斜")]})
    assert calls == []
```

- [ ] **Step 2: Run tests to verify the design**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "shadow_does_not or off_does_not"`

Expected: PASS because the verifier call is gated on `enforce`.

- [ ] **Step 3: Add SSE and interrupt leakage assertions**

```python
def test_semantic_status_does_not_enter_public_issue():
    from core.assistant_graph import _public_issues
    issue = {
        "subcategory_code": "fire_lane_blocked",
        "slot_evidence": {"blocker": {"status": "grounded_by_model"}},
        "evidence": [{"slot": "blocker", "quote": "有杂物", "source_ref": "u1"}],
    }
    public = _public_issues([issue])[0]
    assert "slot_evidence" not in public
    assert "evidence" not in public
```

Keep the existing task-gate interrupt redaction test passing.

- [ ] **Step 4: Run boundary tests**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "shadow_does_not or off_does_not or public_issue" tests/test_task_gate_interrupt.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/assistant_graph.py ai-module/tests/test_semantic_verifier.py ai-module/tests/test_slot_evidence.py ai-module/tests/test_task_gate_interrupt.py
git commit -m "test(ai): preserve shadow and evidence boundaries"
```

---

### Task 7: Documentation And Full Regression

**Files:**
- Modify: `docs/current/agent-orchestration.md`
- Modify: `docs/current/README.md` if the orchestration summary changes
- Test: full `ai-module/tests`

- [ ] **Step 1: Document four business states and the no-confirmation rule**

Add:

```text
grounded -> direct quote
grounded_by_model -> batched semantic verifier above class threshold
rejected -> invalid quote/source or contradiction; slot removed
unavailable -> weak/neutral/failure/echo/missing; slot removed
```

State explicitly:
- no extra user confirmation turn;
- A slots become missing and re-ask original slot;
- B slots become report_missing and are not asserted as facts;
- verifier called once per enforce-mode turn, max five candidates.

- [ ] **Step 2: Run full AI regression excluding external MySQL**

Run: `python -m pytest tests -q --ignore=tests/test_memory_store.py`

Expected: PASS. The pre-existing external MySQL test remains excluded only when the database is unreachable.

- [ ] **Step 3: Run compile check**

Run: `python -m compileall core tests -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/current/agent-orchestration.md docs/current/README.md
git commit -m "docs: document semantic grounding verifier"
```

---

## Threshold Calibration Follow-Up

Do not invent evaluation data in this implementation.

After the verifier path passes tests, build a labeled set with:

```json
{"category":"dangerous_building","slot":"structure","value":"墙体倾斜","quote":"房子明显往一边斜","label":"entailed"}
```

Required metrics at several thresholds:

```text
false accept rate for A-class slots
false accept rate for B-class slots
false reject rate on valid synonyms
neutral/unknown rate
average verifier latency
batch size distribution
```

Keep `A_THRESHOLD >= B_THRESHOLD`. Calibrate only after the implementation is merged.

## Final Acceptance Checklist

- [ ] No new LangGraph node.
- [ ] No confirmation question or extra user turn.
- [ ] One verifier call per enforce turn.
- [ ] At most five candidates, A first.
- [ ] Direct quote support remains `grounded`.
- [ ] High-confidence entailment becomes `grounded_by_model`.
- [ ] High-confidence contradiction or illegal evidence becomes `rejected`.
- [ ] Neutral/failure/weak becomes `unavailable`.
- [ ] A/B thresholds are configurable; A is stricter.
- [ ] A unavailable slots return to `missing` and are asked normally.
- [ ] B unavailable slots enter `report_missing`, not asserted facts.
- [ ] Verifier failure never auto-accepts a slot.
- [ ] Evidence remains absent from SSE, interrupt, report prompt, report text, Java/MySQL.
- [ ] Off/shadow behavior remains unchanged.
- [ ] Full AI regression passes.