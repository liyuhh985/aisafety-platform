# Final Runtime Semantic Verifier Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the semantic-verifier architecture so runtime uses one project LLM with a binary `entailed / contradicted` contract, offline MiniMax/GLM labelers are fully isolated to evaluation, and the decorative C slot class is removed.

**Supersedes:** `docs/superpowers/plans/2026-11-24-dual-model-semantic-verifier.md` for the runtime path. The offline labeling tools remain available, but runtime dual-model consensus is removed.

**Architecture:** Keep deterministic evidence checks as the first gate. Weak evidence is sent in one batch to a zero-temperature verifier backed by the project `LLM_SMALL` model. `entailed` above one global confidence threshold becomes `grounded_by_model`; `contradicted` above that threshold becomes `rejected`; everything invalid, low-confidence, or failed becomes `unavailable`. MiniMax/GLM are never imported by runtime code and remain offline-only pseudo-labelers.

**Tech Stack:** Python, LangGraph, OpenAI-compatible Agent wrapper, pytest

## Global Constraints

- Work from `E:\java\newProject` on branch `codex/opendesign-model-switch`.
- Do not push, merge, rebase, reset, or squash.
- Do not touch Java, MySQL schema, frontend, RabbitMQ, MinIO, or unrelated vision-evaluation files.
- Do not use `git add -A`; stage only the exact files named in each task.
- Runtime must never read `SEMANTIC_LABELER_A_*` or `SEMANTIC_LABELER_B_*`.
- Runtime labels are exactly `entailed` and `contradicted`; `neutral` is forbidden in runtime.
- `entailed` means the quote sufficiently supports the slot value. A same-topic but insufficient quote is `contradicted`, not `entailed`.
- One global runtime threshold applies to both A-class and B-class slots; A/B still control questioning and report eligibility only.
- Remove the decorative `C` slot class, but keep A-class and B-class business behavior unchanged.
- Keep `SLOT_EVIDENCE_MODE=shadow`; do not enable `enforce`.
- Do not regenerate, edit, tune against, or unfreeze the existing `qv-pseudo-v1` test set.
- Evidence, model confidence, verifier labels, and audit reasons must not enter SSE, report prompts, report text, Java DTOs, or `task_gate` interrupt payloads.
- The existing MySQL-dependent `tests/test_memory_store.py` is excluded because it requires external infrastructure.
- Existing unrelated dirty files must remain untouched, including `ai-module/eval/vision/v2/*`, `ai-module/scratch/*`, `tmp/*`, and the modified `docs/current/*` files not listed below.

## Scope Boundary

This plan corrects the runtime architecture and removes the obsolete C class. It does not create a new binary offline pseudo-label dataset.

The current `qv-pseudo-v1` evaluation remains a legacy, failed, tri-label offline experiment:

```text
overall_agreement = 0.7436
cohen_kappa = 0.5149
validation_status = failed_quality_gate
```

Those numbers must not be described as runtime accuracy or as evidence that the binary runtime verifier works. A future, separate plan must create `qv-pseudo-v2` with binary labels and validate the production verifier independently.

## File Structure

- `ai-module/core/slot_schemas.py` — owns A/B slot definitions and selectors; remove decorative C slots.
- `ai-module/core/semantic_verifier.py` — owns the single production-LLM runtime verifier and binary parser.
- `ai-module/config.py` — owns runtime confidence/max-item settings and offline labeler credentials.
- `ai-module/eval/semantic_grounding/labeler_config.py` — owns offline MiniMax/GLM construction and the offline prompt.
- `ai-module/eval/semantic_grounding/batch_smoke.py` — imports offline labeler helpers from the offline module.
- `ai-module/eval/semantic_grounding/protocol.py` — remove obsolete C-class entries; keep legacy tri-label constants for the frozen experiment.
- `ai-module/eval/semantic_grounding/consensus.py` — aggregate agreement only by A/B slot classes.
- `ai-module/eval/semantic_grounding/calibrate_thresholds.py` — rename the contradiction threshold away from `threshold_c`.
- `ai-module/tests/test_slot_value_classes.py` — locks A/B-only schema behavior and C removal.
- `ai-module/tests/test_semantic_grounding_labelers.py` — proves offline labelers are independent of runtime.
- `ai-module/tests/test_semantic_verifier.py` — locks the single-call production-model binary verifier.
- `ai-module/tests/test_semantic_grounding_calibration.py` — locks `threshold_reject`.
- `ai-module/tests/test_semantic_grounding_freeze.py` — locks the new offline threshold key.
- `ai-module/eval/semantic_grounding/report.py` — renders explicit quality-gate status.
- `ai-module/eval/semantic_grounding/evaluate_test.py` — records quality-gate status in metrics.
- `ai-module/.env.example` — documents that runtime uses `LLM_SMALL_*`, not labeler credentials.
- `docs/current/agent-orchestration.md` — current truth for runtime architecture.
- `docs/current/README.md` — replace the stale A/B/C label with A/B.

---

## Task 1: Remove the C Slot Class

**Files:**
- Modify: `ai-module/core/slot_schemas.py`
- Modify: `ai-module/eval/semantic_grounding/protocol.py`
- Modify: `ai-module/eval/semantic_grounding/consensus.py`
- Modify: `ai-module/eval/semantic_grounding/calibrate_thresholds.py`
- Test: `ai-module/tests/test_slot_value_classes.py`
- Test: `ai-module/tests/test_semantic_grounding_calibration.py`
- Test: `ai-module/tests/test_semantic_grounding_freeze.py`

**Interfaces:**
- Consumes: existing `Slot`, `get_slot_schema()`, `missing_decision_slots()`, `missing_report_slots()`.
- Produces: `VALUE_CLASSES == ("A", "B")`; no schema contains `value_class == "C"`.

- [ ] **Step 1: Write the failing schema tests**

Replace the C-related assertions in `ai-module/tests/test_slot_value_classes.py` with the block below. Delete the old `test_decorative_class_is_not_selected_by_either_selector` test because the class no longer exists.

```python
def test_only_a_and_b_value_classes_exist():
    from core.slot_schemas import VALUE_CLASSES
    assert VALUE_CLASSES == ("A", "B")


def test_decorative_c_slots_are_removed():
    dangerous = {slot.key for slot in get_slot_schema("dangerous_building")}
    electrical = {slot.key for slot in get_slot_schema("exposed_wire")}
    assert "risk" not in dangerous
    assert "risk" not in electrical


def test_unknown_value_class_is_rejected_loudly():
    with pytest.raises(ValueError):
        Slot("x", "问句", "C")
```

Keep the existing distribution snapshot because removing two C slots does not change the A-count distribution:

```python
assert counts == {1: 21, 2: 11}
assert max_a == 2
```

- [ ] **Step 2: Run the schema tests to verify they fail**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_slot_value_classes.py -q
```

Expected: FAIL because `VALUE_CLASSES` still includes `"C"` and both `risk` slots still exist.

- [ ] **Step 3: Remove C from the schema**

In `ai-module/core/slot_schemas.py`, change the constants to:

```python
DECISION_CLASS = "A"
REPORT_CLASS = "B"
VALUE_CLASSES = (DECISION_CLASS, REPORT_CLASS)
REPORT_CLASSES = (DECISION_CLASS, REPORT_CLASS)
```

Delete these two slot definitions:

```python
Slot("risk", "有没有明显的即时坍塌风险？", DECORATIVE_CLASS),
Slot("risk", "有没有冒烟或火花等迹象？", DECORATIVE_CLASS),
```

Delete `DECORATIVE_CLASS`. Update the module docstring from A/B/C to A/B and remove the decorative-class explanation.

- [ ] **Step 4: Remove C from offline class aggregation**

In `ai-module/eval/semantic_grounding/protocol.py`, change:

```python
SLOT_CLASSES = ("A", "B")
PRECISION_TARGETS = {"A": 0.98, "B": 0.95, "reject": 0.95}
```

Keep `LABELS = ("entailed", "neutral", "contradicted")` unchanged in this task because the old frozen offline experiment is not being rerun.

In `ai-module/eval/semantic_grounding/consensus.py`, change the class-agreement loop from A/B/C to A/B:

```python
for slot_class in ("A", "B"):
```

In `ai-module/eval/semantic_grounding/calibrate_thresholds.py`, change the rejection target and output key:

```python
scan_reject = scan_rejection_threshold(rows, PRECISION_TARGETS["reject"])
thresholds = {
    "threshold_a": scan_a["threshold"],
    "threshold_b": scan_b["threshold"],
    "threshold_reject": scan_reject["threshold"],
    "dataset": BASE_DATASET,
    "notice": ICD_CALIBRATION_NOTICE,
}
```

Also rename the local variable `scan_c` to `scan_reject` and the artifact name from `threshold_scan_c.json` to `threshold_scan_reject.json`.

- [ ] **Step 5: Update the offline threshold tests**

In `ai-module/tests/test_semantic_grounding_calibration.py`, replace every `threshold_c` assertion with `threshold_reject`. Keep the function name `scan_rejection_threshold`; only the output key changes.

In `ai-module/tests/test_semantic_grounding_freeze.py`, replace test fixture keys:

```python
thresholds={
    "threshold_a": 0.91,
    "threshold_b": 0.84,
    "threshold_reject": 0.90,
}
```

- [ ] **Step 6: Run the focused tests**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_slot_value_classes.py tests/test_semantic_grounding_calibration.py tests/test_semantic_grounding_freeze.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
cd E:\java\newProject
git add ai-module/core/slot_schemas.py ai-module/eval/semantic_grounding/protocol.py ai-module/eval/semantic_grounding/consensus.py ai-module/eval/semantic_grounding/calibrate_thresholds.py ai-module/tests/test_slot_value_classes.py ai-module/tests/test_semantic_grounding_calibration.py ai-module/tests/test_semantic_grounding_freeze.py
git commit -m "refactor(ai): remove decorative slot class"
```

---

## Task 2: Make Offline Labelers Independent from Runtime

**Files:**
- Modify: `ai-module/eval/semantic_grounding/labeler_config.py`
- Modify: `ai-module/eval/semantic_grounding/batch_smoke.py`
- Test: `ai-module/tests/test_semantic_grounding_labelers.py`

**Interfaces:**
- Consumes: `Agent`, `SEMANTIC_LABELER_A_*`, `SEMANTIC_LABELER_B_*`.
- Produces: `OFFLINE_LABELER_PROMPT: str`, `build_labeler(key: str) -> Agent`, `call_labeler(key: str, candidates: list[dict], cancellation=None) -> dict`.

- [ ] **Step 1: Write the failing isolation test**

Append to `ai-module/tests/test_semantic_grounding_labelers.py`:

```python
def test_offline_labelers_do_not_import_runtime_verifier():
    import inspect
    from eval.semantic_grounding import labeler_config

    source = inspect.getsource(labeler_config)
    assert "core.semantic_verifier" not in source
```

- [ ] **Step 2: Run the isolation test to verify it fails**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_semantic_grounding_labelers.py::test_offline_labelers_do_not_import_runtime_verifier -q
```

Expected: FAIL because `labeler_config.py` currently imports from `core.semantic_verifier`.

- [ ] **Step 3: Move the offline prompt and labeler helpers**

Replace the body of `ai-module/eval/semantic_grounding/labeler_config.py` with:

```python
# -*- coding: utf-8 -*-
"""Offline MiniMax/GLM pseudo-labelers; never imported by runtime code."""

import json
import os

from core.agent import Agent

OFFLINE_LABELER_PROMPT = (
    "你是离线伪标签标注器。只判断 quote 是否支持 value。"
    "relation 只能是 entailed / neutral / contradicted。"
    "entailed 表示 quote 直接支持 value；contradicted 表示 quote 与 value 冲突；"
    "neutral 表示 quote 既不能支持也不能否定 value。"
    "不重新抽取事实，不参考对话，不使用工具。"
    "输入是一个 JSON 数组，每个元素包含 id、slot、slot_question、value、quote。"
    '只输出一个 JSON 对象：{"labels":[{"id":"...","label":"...","confidence":0.0}]}。'
    "每个输入 id 必须恰好返回一次，不添加其他字段。"
)

_LABELERS = {}


def build_labeler(key: str):
    normalized = str(key or "").upper()
    if normalized not in {"A", "B"}:
        raise ValueError("labeler key must be A or B")
    base = os.getenv(f"SEMANTIC_LABELER_{normalized}_BASE_URL", "").strip()
    api_key = os.getenv(f"SEMANTIC_LABELER_{normalized}_API_KEY", "").strip()
    model = os.getenv(f"SEMANTIC_LABELER_{normalized}_MODEL", "").strip()
    if not base or not api_key or not model:
        raise RuntimeError(f"semantic labeler {normalized} is not configured")
    return Agent(
        name=f"semantic_labeler_{normalized.lower()}",
        system_prompt=OFFLINE_LABELER_PROMPT,
        tools=[],
        base_url=base,
        api_key=api_key,
        model=model,
        temperature=0.0,
        use_configured_slot=False,
        allow_fallback=False,
    )


def _configured_labeler(key: str):
    if key not in _LABELERS:
        _LABELERS[key] = build_labeler(key)
    return _LABELERS[key]


def _normalize_label(value):
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    confidence = value.get("confidence")
    if label not in {"entailed", "neutral", "contradicted"}:
        return None
    if (not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0.0 <= float(confidence) <= 1.0):
        return None
    return {"label": label, "confidence": float(confidence)}


def parse_batch_response(text) -> dict:
    raw = str(text or "").strip()
    if raw.startswith("`" * 3):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(payload, dict) and "labels" in payload:
        payload = payload.get("labels")
    result = {}
    if isinstance(payload, dict):
        for identifier, value in payload.items():
            normalized = _normalize_label(value)
            if normalized is not None:
                result[str(identifier)] = normalized
    elif isinstance(payload, list):
        for value in payload:
            if not isinstance(value, dict) or not value.get("id"):
                continue
            normalized = _normalize_label(value)
            if normalized is not None:
                result[str(value["id"])] = normalized
    return result


def call_labeler(key, candidates, cancellation=None) -> dict:
    labeler = _configured_labeler(key)
    visible = [
        {field: row.get(field, "") for field in (
            "id", "slot", "slot_question", "value", "quote",
        )}
        for row in candidates
    ]
    messages = [
        {"role": "system", "content": labeler.system_prompt},
        {"role": "user", "content": json.dumps(
            visible, ensure_ascii=False, sort_keys=True
        )},
    ]
    response = labeler._call_llm(messages, cancellation=cancellation)
    return parse_batch_response((response or {}).get("content"))
```

Append this compatibility alias at the end of `labeler_config.py`:

```python
_call_labeler = call_labeler
```

- [ ] **Step 4: Update the offline smoke import**

In `ai-module/eval/semantic_grounding/batch_smoke.py`, change:

```python
from core.semantic_verifier import SEMANTIC_LABELER_PROMPT, _call_labeler
```

to:

```python
from eval.semantic_grounding.labeler_config import (
    OFFLINE_LABELER_PROMPT, call_labeler,
)
```

Then change `SEMANTIC_LABELER_PROMPT` to `OFFLINE_LABELER_PROMPT` and `_call_labeler` to `call_labeler`.

- [ ] **Step 5: Run the offline labeler tests**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_semantic_grounding_labelers.py -q
```

Expected: PASS. Do not run the real API smoke unless labeler endpoints and keys are already configured.

- [ ] **Step 6: Commit**

```powershell
cd E:\java\newProject
git add ai-module/eval/semantic_grounding/labeler_config.py ai-module/eval/semantic_grounding/batch_smoke.py ai-module/tests/test_semantic_grounding_labelers.py
git commit -m "refactor(eval): isolate offline labelers from runtime"
```

---

## Task 3: Replace the Runtime Dual-Model Verifier with One Production-Model Verifier

**Files:**
- Modify: `ai-module/config.py`
- Modify: `ai-module/core/semantic_verifier.py`
- Test: `ai-module/tests/test_semantic_verifier.py`

**Interfaces:**
- Consumes: `SMALL_MODEL`, `Agent`, `SEMANTIC_VERIFIER_MIN_CONFIDENCE`, `SEMANTIC_VERIFIER_MAX_ITEMS`.
- Produces: `RUNTIME_VERIFIER_PROMPT: str`, `build_verifier() -> Agent`, `parse_batch_response(text) -> dict`, `verify_weak_slots(issues, audit, cancellation=None) -> dict`.

- [ ] **Step 1: Write the failing runtime tests**

Replace the obsolete dual-model tests in `ai-module/tests/test_semantic_verifier.py` with tests covering these exact behaviors:

```python
def test_runtime_verifier_uses_project_small_model(monkeypatch):
    from types import SimpleNamespace
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


def test_binary_entailment_is_grounded_by_model(monkeypatch):
    from core import semantic_verifier as sv
    monkeypatch.setattr(sv, "SEMANTIC_VERIFIER_MIN_CONFIDENCE", 0.85)


    issue = {
        "major_code": "building",
        "subcategory_code": "dangerous_building",
        "slots": {"structure": "墙体倾斜"},
    }
    audit = {
        "dangerous_building": {
            "structure": {
                "status": "weak",
                "business_status": "unavailable",
                "value": "墙体倾斜",
                "quote": "房子明显往一边斜",
                "source_ref": "u1",
            }
        }
    }
    monkeypatch.setattr(
        sv, "_call_verifier",
        lambda candidates, cancellation=None: {
            "dangerous_building:structure": {
                "label": "entailed", "confidence": 0.93,
            }
        },
    )
    result = sv.verify_weak_slots([issue], audit)
    assert result["dangerous_building"]["structure"]["business_status"] == (
        "grounded_by_model"
    )


def test_binary_contradiction_is_rejected(monkeypatch):
    from core import semantic_verifier as sv
    monkeypatch.setattr(sv, "SEMANTIC_VERIFIER_MIN_CONFIDENCE", 0.85)


    issue = {
        "major_code": "building",
        "subcategory_code": "dangerous_building",
        "slots": {"structure": "墙体倾斜"},
    }
    audit = {
        "dangerous_building": {
            "structure": {
                "status": "weak",
                "business_status": "unavailable",
                "value": "墙体倾斜",
                "quote": "房屋结构稳定，没有倾斜",
                "source_ref": "u1",
            }
        }
    }
    monkeypatch.setattr(
        sv, "_call_verifier",
        lambda candidates, cancellation=None: {
            "dangerous_building:structure": {
                "label": "contradicted", "confidence": 0.91,
            }
        },
    )
    result = sv.verify_weak_slots([issue], audit)
    assert result["dangerous_building"]["structure"]["business_status"] == "rejected"


def test_low_confidence_is_unavailable(monkeypatch):
    from core import semantic_verifier as sv
    monkeypatch.setattr(sv, "SEMANTIC_VERIFIER_MIN_CONFIDENCE", 0.85)


    issue = {
        "major_code": "fire",
        "subcategory_code": "fire_lane_blocked",
        "slots": {"impact": "无法通行"},
    }
    audit = {
        "fire_lane_blocked": {
            "impact": {
                "status": "weak",
                "business_status": "unavailable",
                "value": "无法通行",
                "quote": "消防车勉强通过",
                "source_ref": "u1",
            }
        }
    }
    monkeypatch.setattr(
        sv, "_call_verifier",
        lambda candidates, cancellation=None: {
            "fire_lane_blocked:impact": {
                "label": "entailed", "confidence": 0.60,
            }
        },
    )
    result = sv.verify_weak_slots([issue], audit)
    assert result["fire_lane_blocked"]["impact"]["business_status"] == "unavailable"


def test_a_and_b_slots_use_one_batch_call(monkeypatch):
    from core import semantic_verifier as sv
    monkeypatch.setattr(sv, "SEMANTIC_VERIFIER_MIN_CONFIDENCE", 0.85)


    issues = [
        {
            "major_code": "building",
            "subcategory_code": "dangerous_building",
            "slots": {"structure": "墙体倾斜"},
        },
        {
            "major_code": "fire",
            "subcategory_code": "fire_lane_blocked",
            "slots": {"impact": "无法通行"},
        },
    ]
    audit = {
        "dangerous_building": {
            "structure": {
                "status": "weak", "business_status": "unavailable",
                "value": "墙体倾斜", "quote": "房子往一边歪", "source_ref": "u1",
            }
        },
        "fire_lane_blocked": {
            "impact": {
                "status": "weak", "business_status": "unavailable",
                "value": "无法通行", "quote": "消防车无法进入", "source_ref": "u2",
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


def test_neutral_is_invalid_in_runtime(monkeypatch):
    from core import semantic_verifier as sv

    assert sv.parse_batch_response(
        '{"labels":[{"id":"x","label":"neutral","confidence":0.99}]}'
    ) == {}
```

Keep the existing `test_shadow_does_not_call_labelers` and `test_off_does_not_call_labelers` integration tests, but rename them to say `runtime_verifier`.

- [ ] **Step 2: Run the runtime verifier tests to verify they fail**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_semantic_verifier.py -q
```

Expected: FAIL because runtime still imports MiniMax/GLM labelers, expects dual-model agreement, and accepts `neutral`.

- [ ] **Step 3: Replace the runtime configuration**

In `ai-module/config.py`, delete:

```python
SEMANTIC_VERIFIER_A_THRESHOLD
SEMANTIC_VERIFIER_B_THRESHOLD
SEMANTIC_VERIFIER_C_THRESHOLD
```

Add:

```python
# One global runtime threshold; A/B classes do not change model confidence policy.
SEMANTIC_VERIFIER_MIN_CONFIDENCE = float(
    os.getenv("SEMANTIC_VERIFIER_MIN_CONFIDENCE", "0.85")
)
SEMANTIC_VERIFIER_MAX_ITEMS = int(
    os.getenv("SEMANTIC_VERIFIER_MAX_ITEMS", "5")
)
```

Keep the `SEMANTIC_LABELER_A_*` and `SEMANTIC_LABELER_B_*` constants, but change the comment to:

```python
# Offline pseudo-labelers only. Runtime never imports these credentials.
```

- [ ] **Step 4: Replace `ai-module/core/semantic_verifier.py`**

Use this implementation as the complete runtime module:

```python
# -*- coding: utf-8 -*-
"""Single production-model verifier for weak slot evidence."""

import json
from typing import Optional

from config import (
    SEMANTIC_VERIFIER_MAX_ITEMS,
    SEMANTIC_VERIFIER_MIN_CONFIDENCE,
    SMALL_MODEL,
)
from core.agent import Agent
from core.slot_schemas import get_slot_schema

RUNTIME_VERIFIER_PROMPT = (
    "你是槽位证据复核器。只判断 quote 是否支持 value，label 只能是 "
    "entailed / contradicted。"
    "entailed 表示 quote 直接陈述、同义改写或语义蕴含足以支持 value。"
    "contradicted 表示 quote 不支持 value，包括信息不足、仅同主题、无关、"
    "明确否定或数字冲突。"
    "不重新抽取事实，不判断风险等级，不参考完整对话，不使用工具。"
    "输入是一个 JSON 数组，每个元素包含 id、slot、slot_question、value、quote。"
    '只输出一个 JSON 对象：{"labels":[{"id":"...","label":"...","confidence":0.0}]}。'
    "每个输入 id 必须恰好返回一次，不添加其他字段。"
)

_VERIFIER = None


def build_verifier():
    return Agent(
        name="semantic_verifier",
        system_prompt=RUNTIME_VERIFIER_PROMPT,
        tools=[],
        base_url=SMALL_MODEL.base_url,
        api_key=SMALL_MODEL.api_key,
        model=SMALL_MODEL.model,
        slot="small",
        temperature=0.0,
        use_configured_slot=True,
        allow_fallback=True,
    )


def _configured_verifier():
    global _VERIFIER
    if _VERIFIER is None:
        _VERIFIER = build_verifier()
    return _VERIFIER


def _slot_schema(code: str, slot_key: str):
    for slot in get_slot_schema(code):
        if slot.key == slot_key:
            return slot
    return None


def _slot_question(code: str, slot_key: str) -> str:
    slot = _slot_schema(code, slot_key)
    return slot.question if slot else ""


def _slot_class(code: str, slot_key: str) -> str:
    slot = _slot_schema(code, slot_key)
    return slot.value_class if slot else "B"


def collect_weak_candidates(issues, audit, max_items=5) -> list[dict]:
    candidates = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("subcategory_code") or "")
        if not code:
            continue
        for slot, value in (issue.get("slots") or {}).items():
            result = ((audit.get(code) or {}).get(slot) or {})
            if result.get("status") != "weak":
                continue
            quote = str(result.get("quote") or "")
            source_ref = str(result.get("source_ref") or "")
            if not quote or source_ref[:1] not in {"u", "v"}:
                continue
            candidates.append({
                "id": f"{code}:{slot}",
                "category": code,
                "slot": slot,
                "slot_question": _slot_question(code, slot),
                "value": str(value),
                "quote": quote,
                "value_class": _slot_class(code, slot),
            })
    rank = {"A": 0, "B": 1}
    candidates.sort(key=lambda row: rank.get(row["value_class"], 2))
    return candidates[:max(1, int(max_items or 5))]


def _normalize_label(value) -> Optional[dict]:
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    confidence = value.get("confidence")
    if label not in {"entailed", "contradicted"}:
        return None
    if (not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0.0 <= float(confidence) <= 1.0):
        return None
    return {"label": label, "confidence": float(confidence)}


def parse_batch_response(text) -> dict:
    raw = str(text or "").strip()
    if raw.startswith("`" * 3):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(payload, dict) and "labels" in payload:
        payload = payload.get("labels")
    result = {}
    if isinstance(payload, dict):
        for identifier, value in payload.items():
            normalized = _normalize_label(value)
            if normalized is not None:
                result[str(identifier)] = normalized
    elif isinstance(payload, list):
        for value in payload:
            if not isinstance(value, dict) or not value.get("id"):
                continue
            normalized = _normalize_label(value)
            if normalized is not None:
                result[str(value["id"])] = normalized
    return result


def _call_verifier(candidates, cancellation=None) -> dict:
    verifier = _configured_verifier()
    visible = [
        {field: row.get(field, "") for field in (
            "id", "slot", "slot_question", "value", "quote",
        )}
        for row in candidates
    ]
    messages = [
        {"role": "system", "content": verifier.system_prompt},
        {"role": "user", "content": json.dumps(
            visible, ensure_ascii=False, sort_keys=True
        )},
    ]
    response = verifier._call_llm(messages, cancellation=cancellation)
    return parse_batch_response((response or {}).get("content"))


def _apply_status(result, status, label=None, confidence=None) -> None:
    result["status"] = status
    result["business_status"] = status
    if status == "grounded_by_model":
        result["reason"] = "runtime_verifier_entailed"
    elif status == "rejected":
        result["reason"] = "runtime_verifier_contradicted"
    else:
        result["reason"] = "runtime_verifier_low_confidence_or_invalid"
    if label is not None:
        result["verifier_label"] = label
    if confidence is not None:
        result["verifier_confidence"] = confidence


def verify_weak_slots(issues, audit, cancellation=None) -> dict:
    audit = audit if isinstance(audit, dict) else {}
    candidates = collect_weak_candidates(
        issues, audit, max_items=SEMANTIC_VERIFIER_MAX_ITEMS
    )
    if not candidates:
        return audit
    try:
        labels = _call_verifier(candidates, cancellation=cancellation)
    except Exception:
        labels = {}

    for candidate in candidates:
        code = candidate["category"]
        slot = candidate["slot"]
        result = ((audit.get(code) or {}).get(slot) or {})
        if not result:
            continue
        verdict = labels.get(candidate["id"])
        if verdict is None:
            _apply_status(result, "unavailable")
            continue
        confidence = verdict["confidence"]
        if confidence < SEMANTIC_VERIFIER_MIN_CONFIDENCE:
            _apply_status(result, "unavailable", verdict["label"], confidence)
            continue
        status = (
            "grounded_by_model"
            if verdict["label"] == "entailed"
            else "rejected"
        )
        _apply_status(result, status, verdict["label"], confidence)
    return audit
```

Do not import or reference any `SEMANTIC_LABELER_*` name in this file.

- [ ] **Step 5: Run the focused runtime tests**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_semantic_verifier.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
cd E:\java\newProject
git add ai-module/config.py ai-module/core/semantic_verifier.py ai-module/tests/test_semantic_verifier.py
git commit -m "refactor(ai): use one production model for slot verification"
```

---

## Task 4: Wire Integration Behavior and Fail-Closed Tests

**Files:**
- Test: `ai-module/tests/test_semantic_verifier.py`
- Test: `ai-module/tests/test_slot_evidence.py`
- Modify if required: `ai-module/core/assistant_graph.py`

**Interfaces:**
- Consumes: `verify_weak_slots()`, `_drop_unusable_slots()`, `_rebuild_issue_missing()`.
- Produces: no runtime behavior in `off` or `shadow`; `enforce` calls exactly one verifier batch and applies `grounded_by_model / rejected / unavailable`.

- [ ] **Step 1: Add fail-closed integration tests**

Add:

```python
def test_verifier_exception_makes_candidate_unavailable(monkeypatch):
    from core import semantic_verifier as sv

    issue = {
        "major_code": "building",
        "subcategory_code": "dangerous_building",
        "slots": {"structure": "墙体倾斜"},
    }
    audit = {
        "dangerous_building": {
            "structure": {
                "status": "weak", "business_status": "unavailable",
                "value": "墙体倾斜", "quote": "房子往一边歪", "source_ref": "u1",
            }
        }
    }
    monkeypatch.setattr(
        sv, "_call_verifier",
        lambda candidates, cancellation=None: (_ for _ in ()).throw(RuntimeError("timeout")),
    )
    result = sv.verify_weak_slots([issue], audit)
    assert result["dangerous_building"]["structure"]["business_status"] == "unavailable"


def test_verifier_payload_excludes_audit_and_classes(monkeypatch):
    from types import SimpleNamespace
    import json
    from core import semantic_verifier as sv

    captured = {}

    def fake_call(messages, cancellation=None):
        captured["payload"] = json.loads(messages[1]["content"])
        return {"content": '{"labels":[{"id":"x","label":"entailed","confidence":0.95}]}'}

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
```

- [ ] **Step 2: Run integration-focused tests**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_semantic_verifier.py tests/test_slot_evidence.py tests/test_slot_value_classes.py -q
```

Expected: PASS. Existing `off` and `shadow` tests must still show zero verifier calls.

If `_drop_unusable_slots()` no longer maps the new statuses correctly, change only the mapping in `ai-module/core/assistant_graph.py`; do not change route policy or report wording in this task.

- [ ] **Step 3: Commit**

```powershell
cd E:\java\newProject
git add ai-module/tests/test_semantic_verifier.py ai-module/tests/test_slot_evidence.py ai-module/core/assistant_graph.py
git commit -m "test(ai): lock fail-closed runtime verification"
```

If `assistant_graph.py` required no changes, omit it from `git add`; never stage an unchanged file.

---

## Task 5: Record the Failed Offline Gate and Update Current Documentation

**Files:**
- Modify: `ai-module/eval/semantic_grounding/report.py`
- Modify: `ai-module/eval/semantic_grounding/evaluate_test.py`
- Modify: `ai-module/.env.example`
- Modify: `docs/current/agent-orchestration.md`
- Modify: `docs/current/README.md`
- Test: `ai-module/tests/test_semantic_grounding_freeze.py`

**Interfaces:**
- Consumes: `OVERALL_AGREEMENT_GATE`, `COHEN_KAPPA_GATE`, existing `test_metrics.json`.
- Produces: report text beginning with an explicit `VALIDATION STATUS`; metrics containing `quality_gate_passed` and `validation_status`.

- [ ] **Step 1: Write the failing report-status test**

Append to `ai-module/tests/test_semantic_grounding_freeze.py`:

```python
def test_report_marks_failed_quality_gate_explicitly():
    text = render_report({
        "overall_agreement": 0.70,
        "cohen_kappa": 0.50,
        "thresholds": {},
        "auto_accept": {},
    })
    assert "VALIDATION STATUS: FAILED QUALITY GATE" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_semantic_grounding_freeze.py -q
```

Expected: FAIL because the report only prints metrics and has no status line.

- [ ] **Step 3: Add the quality-gate status to the report**

In `ai-module/eval/semantic_grounding/report.py`, import the gates:

```python
from eval.semantic_grounding.protocol import (
    COHEN_KAPPA_GATE,
    OVERALL_AGREEMENT_GATE,
)
```

Add:

```python
def quality_gate_passed(metrics: dict) -> bool:
    metrics = metrics or {}
    return (
        float(metrics.get("overall_agreement") or 0.0) >= OVERALL_AGREEMENT_GATE
        and float(metrics.get("cohen_kappa") or 0.0) >= COHEN_KAPPA_GATE
    )
```

At the top of `render_report()` output, add after the title:

```python
status = (
    "PASSED"
    if quality_gate_passed(metrics)
    else "FAILED QUALITY GATE"
)
lines.extend([
    f"**VALIDATION STATUS: {status}**",
    "",
])
```

- [ ] **Step 4: Record status in new test metrics**

In `ai-module/eval/semantic_grounding/evaluate_test.py`, import the gates:

```python
from eval.semantic_grounding.protocol import COHEN_KAPPA_GATE, OVERALL_AGREEMENT_GATE
```

Then change the metrics dict to include:

```python
quality_gate_passed = (
    float(consensus["summary"]["overall_agreement"]) >= OVERALL_AGREEMENT_GATE
    and float(consensus["summary"]["cohen_kappa"]) >= COHEN_KAPPA_GATE
)
metrics = {
    # Keep every existing metric here.
    "quality_gate_passed": quality_gate_passed,
    "validation_status": (
        "passed" if quality_gate_passed else "failed_quality_gate"
    ),
}
```

- [ ] **Step 5: Regenerate the existing report without rerunning models**

Run:

```powershell
cd E:\java\newProject\ai-module
python -c "import json; from pathlib import Path; from eval.semantic_grounding.report import render_report; p=Path('eval/semantic_grounding/evaluation/test_metrics.json'); m=json.loads(p.read_text(encoding='utf-8')); m['quality_gate_passed'] = bool(m.get('overall_agreement',0)>=0.75 and m.get('cohen_kappa',0)>=0.60); m['validation_status'] = 'passed' if m['quality_gate_passed'] else 'failed_quality_gate'; p.write_text(json.dumps(m, ensure_ascii=False, indent=2)+chr(10), encoding='utf-8'); (p.parent/'REPORT.md').write_text(render_report(m), encoding='utf-8')"
```

Expected: the existing `REPORT.md` starts with `VALIDATION STATUS: FAILED QUALITY GATE`. No model is called.

- [ ] **Step 6: Update `.env.example`**

Replace the three threshold lines with:

```ini
# Runtime verifier uses the project LLM_SMALL_* endpoint.
# MiniMax/GLM keys below are for offline pseudo-labeling only.
SEMANTIC_VERIFIER_MIN_CONFIDENCE=0.85
SEMANTIC_VERIFIER_MAX_ITEMS=5
```

Keep the `SEMANTIC_LABELER_A_*` and `SEMANTIC_LABELER_B_*` lines, and add this comment above them:

```ini
# Offline evaluation only. Runtime code must never read these values.
```

- [ ] **Step 7: Update current truth documentation**

In `docs/current/agent-orchestration.md`, replace the dual-model evidence bullets with:

```markdown
- `enforce` 下，确定性校验后的灰区 `weak` 槽位最多取 5 个，A 类优先；随后用一次批量调用交给项目 `LLM_SMALL` 零温度复核。
- 运行时语义标签只有 `entailed / contradicted`：`entailed` 表示 quote 足以支持槽位值，包含直接陈述、同义改写和明确语义蕴含；`contradicted` 表示 quote 不支持该值，包括信息不足、仅同主题、无关、明确否定和数字冲突。
- A/B 槽位共用同一个 `SEMANTIC_VERIFIER_MIN_CONFIDENCE`；A/B 只决定追问和报告门禁，不改变语义复核阈值。
- `entailed` 达到阈值 -> `grounded_by_model`；`contradicted` 达到阈值 -> `rejected`；低置信度、超时、非法 JSON 或不合法标签 -> `unavailable`。
- `unavailable / rejected` 槽位会在 `understand` 内被删除并重算：A 类回到 `missing` 继续追问，B 类进入 `report_missing`，只写条件分支，不能当成确定事实。
- `off` / `shadow` 不调用运行时语义复核；当前默认 `shadow`，禁止在本计划中切换 `enforce`。
- MiniMax/GLM 只用于离线伪标签实验，运行时不得导入或调用 `SEMANTIC_LABELER_A_*` / `SEMANTIC_LABELER_B_*`。
- 当前 `qv-pseudo-v1` 三分类实验未通过质量门禁，其 agreement/kappa 不是运行时准确率，也不能作为生产验证证据。
- C 类装饰槽位已删除；槽位 schema 只保留 A/B。A 类缺失继续追问并阻止报告，B 类缺失不追问但进入报告条件分支。
```

In the module list near the end, change:

```text
core/slot_schemas.py         槽位 A/B/C
```

to:

```text
core/slot_schemas.py         槽位 A/B
```

In `docs/current/README.md`, change the `agent-orchestration.md` row text:

```markdown
| [agent-orchestration.md](./agent-orchestration.md) | LangGraph 20 节点、状态通道、两级分类、槽位 A/B、证据链灰度、Skill 路由、范围/不确定性、检索重试、建单闸门 |
```

Do not update `docs/current/README.md` timestamps unless the whole document has been rechecked.

- [ ] **Step 8: Run the documentation and report tests**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_semantic_grounding_freeze.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
cd E:\java\newProject
git add ai-module/eval/semantic_grounding/report.py ai-module/eval/semantic_grounding/evaluate_test.py ai-module/eval/semantic_grounding/evaluation/test_metrics.json ai-module/eval/semantic_grounding/evaluation/REPORT.md ai-module/.env.example docs/current/agent-orchestration.md docs/current/README.md ai-module/tests/test_semantic_grounding_freeze.py
git commit -m "docs: document binary runtime verification boundary"
```

If `docs/current/README.md` has unrelated pre-existing modifications, do not stage or commit it; update only `agent-orchestration.md` and report this conflict.

---

## Task 6: Full Regression and Final Verification

**Files:**
- No source edits expected unless a test exposes a real defect.
- Do not edit frozen test datasets to make tests pass.

- [ ] **Step 1: Run the focused semantic and slot suite**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests/test_slot_value_classes.py tests/test_semantic_verifier.py tests/test_semantic_grounding_labelers.py tests/test_semantic_grounding_calibration.py tests/test_semantic_grounding_freeze.py tests/test_slot_evidence.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full AI regression**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m pytest tests -q --ignore=tests/test_memory_store.py
```

Expected: PASS. Record exact passed/skipped counts.

- [ ] **Step 3: Run compilation**

Run:

```powershell
cd E:\java\newProject\ai-module
python -m compileall core eval tools tests
```

Expected: exit code 0.

- [ ] **Step 4: Prove runtime has no offline labeler dependency**

Run:

```powershell
cd E:\java\newProject\ai-module
rg -n "SEMANTIC_LABELER|minimax|glm" core/semantic_verifier.py
```

Expected: no matches.

- [ ] **Step 5: Prove C class is gone from runtime schemas**

Run:

```powershell
cd E:\java\newProject\ai-module
rg -n "DECORATIVE_CLASS|value_class=\"C\"|value_class='C'" core tests
```

Expected: no matches in runtime schema or tests. Historical offline artifacts may still contain old data and must not be rewritten.

- [ ] **Step 6: Inspect git state**

Run:

```powershell
cd E:\java\newProject
git status --short
git log -6 --oneline
```

Expected: only the intended new commits and pre-existing unrelated dirty files. Do not push.

---

## Review Checklist

- [ ] Runtime reads only `SMALL_MODEL` / `LLM_SMALL_*`, never MiniMax/GLM credentials.
- [ ] Runtime has exactly one verifier call per batch.
- [ ] Runtime parser accepts only `entailed` and `contradicted`.
- [ ] Low confidence, timeout, invalid JSON, invalid label, and backend exceptions fail closed to `unavailable`.
- [ ] A and B slots use the same semantic threshold.
- [ ] A/B still control follow-up and report behavior.
- [ ] Every C slot definition and runtime C-class branch is removed.
- [ ] `off` and `shadow` keep legacy behavior and make zero verifier calls.
- [ ] Evidence and verifier internals remain absent from public output.
- [ ] Existing frozen test data is unchanged.
- [ ] Existing failed quality-gate status is visible in `REPORT.md`.
- [ ] No Java, MySQL, frontend, RabbitMQ, MinIO, or unrelated vision files changed.
- [ ] No push or merge occurred.
