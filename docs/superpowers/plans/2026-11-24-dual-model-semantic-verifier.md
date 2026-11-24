# Dual-Model Semantic Grounding Pseudo-Label Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dual-model pseudo-labeling and threshold-calibration pipeline for semantic slot grounding, then use dual-model consensus at runtime without adding any user-confirmation turn.

**Architecture:** Keep deterministic quote validation first. Send only valid grey-zone `weak` samples to two independent zero-temperature models for offline pseudo-labeling. Calibrate class-specific thresholds on dev consensus, freeze the test set once, and implement runtime semantic verification inside `understand` with A-class dual consensus, B-class single-model acceptance plus dual contradiction confirmation. Unusable slots are removed before missing/report-missing recomputation.

**Tech Stack:** Python 3.11, pytest, existing `Agent`, JSONL artifacts, LangGraph `understand`, existing `slot_schemas.py`.

> **Supersedes:** `docs/superpowers/plans/2026-11-24-semantic-grounding-verifier.md`. Execute this plan instead of the earlier single-model plan.

## Global Constraints

- Offline labels are pseudo-labels, not human gold labels.
- Reports must say thresholds were calibrated on dual-model consensus, with no human review.
- Labelers are `minimax-m3.1-flash` and `glm-5.3-flash`, configured through environment variables; no API key is stored in Git.
- Each labeler is called independently, does not see the other result, receives no full conversation and no tools, and uses `temperature=0.0`.
- Allowed labels only: `entailed`, `contradicted`, `neutral`.
- Exact disagreement becomes `ambiguous` and is excluded from threshold calibration.
- Base calibration dataset: 150 items, 50 per label, split 90 dev / 60 test by `source_group_id`.
- Extra 20–30 boundary items live in `boundary.jsonl` and are diagnostic only, not threshold-selection data.
- No similar paraphrase from the same source group may appear in both dev and test.
- Deterministic rules run before any labeler call.
- Agreement gates: `overall_agreement >= 0.75` and `Cohen_kappa >= 0.60`; failing either gate blocks threshold calibration.
- Threshold scan values: `0.70, 0.75, 0.80, 0.85, 0.90, 0.95`.
- Auto-accept precision targets: A class `>= 0.98`, B class `>= 0.95`.
- If targets cannot be met, raise thresholds and reduce coverage; never weaken precision.
- Freeze model names, prompt hash, thresholds, and test manifest before one test run; do not tune on test.
- Runtime makes at most two verifier calls per turn: model A once and model B once.
- Runtime maximum five candidates, A-class slots before B-class slots.
- A-class acceptance/rejection requires both models.
- B-class entailment may use model A alone above the calibrated B threshold.
- B-class contradiction requires model B confirmation; if B does not confirm, result is `unavailable`.
- Runtime failures/disagreement/low confidence -> `unavailable`; never auto-accept.
- No new LangGraph node and no user confirmation question.
- Evidence remains internal: no SSE, interrupt, report prompt, report text, Java DTO, or MySQL.

---

## File Structure

Create under `ai-module/eval/semantic_grounding/`:

- `protocol.py` — constants, labels, sample schema, hashing helpers.
- `validate_dataset.py` — base/boundary schema, quotas, split leakage checks.
- `deterministic_prefilter.py` — obvious grounded/contradicted/invalid/echo routing.
- `labeler_config.py` — model A/B Agent construction from environment variables.
- `run_labelers.py` — independent JSONL labeling.
- `consensus.py` — exact agreement, disagreement, agreement and Cohen kappa.
- `calibrate_thresholds.py` — dev-only threshold scan.
- `freeze_test.py` — hash and freeze test labels/artifacts.
- `evaluate_test.py` — one frozen test run and metrics.
- `report.py` — Markdown evidence report.
- `dataset/qv-pseudo-v1.jsonl`
- `dataset/boundary.jsonl`
- `tests/test_*` in `ai-module/tests/`.

Create or modify under `ai-module/core/`:

- `core/semantic_verifier.py` — runtime A/B verifier, batching, consensus, status application.
- `core/agent.py` — optional temperature.
- `core/uncertainty.py` — four business states.
- `core/assistant_graph.py` — call verifier in `understand`, remove unusable slots, rebuild missing/report-missing.
- `config.py` and `.env.example` — labeler and threshold config.

---

### Task 1: Add Dedicated Zero-Temperature Agent Mode

**Files:**
- Modify: `ai-module/core/agent.py`
- Test: `ai-module/tests/test_semantic_verifier.py`

**Interfaces:**
- Produces: `Agent(..., temperature: float = 0.3, use_configured_slot: bool = True, allow_fallback: bool = True)`
- Dedicated labeler instances must use only their explicit base URL/API key/model and no fallback.

- [ ] **Step 1: Write the failing tests**

```python
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
        name="semantic_labeler_a", system_prompt="VERIFY", tools=[],
        base_url="http://dedicated", api_key="d", model="minimax-m3.1-flash",
        slot="small", use_configured_slot=False, allow_fallback=False,
    )
    assert agent._llm_endpoints() == [("http://dedicated", "d", "minimax-m3.1-flash", None)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "temperature_is_zero or ignores_global"`

Expected: FAIL because the Agent parameters are missing.

- [ ] **Step 3: Implement dedicated mode**

Add to `Agent.__init__`:

```python
temperature: float = 0.3,
use_configured_slot: bool = True,
allow_fallback: bool = True,
```

Store the fields and use `self.temperature` in `_build_payload()`.

Change `_llm_endpoints()` so global `SMALL_MODEL/TEXT_MODEL` and `FALLBACK_LLM_*` are considered only when their flags are true:

```python
def _llm_endpoints(self):
    if self.use_configured_slot:
        conf = SMALL_MODEL if self.slot == "small" else TEXT_MODEL
        if conf.base_url and conf.api_key and conf.model:
            chain = [(conf.base_url.rstrip("/"), conf.api_key,
                      conf.model, conf.effort or None)]
        else:
            chain = [(self.base_url, self.api_key, self.model, None)]
    else:
        chain = [(self.base_url, self.api_key, self.model, None)]

    if self.allow_fallback and FALLBACK_LLM_BASE_URL and FALLBACK_LLM_API_KEY and FALLBACK_LLM_MODEL:
        fallback = (FALLBACK_LLM_BASE_URL.rstrip("/"), FALLBACK_LLM_API_KEY,
                    FALLBACK_LLM_MODEL, FALLBACK_LLM_EFFORT or None)
        if (fallback[0], fallback[2]) != (chain[0][0], chain[0][2]):
            chain.append(fallback)
    return chain
```

Existing agents use the defaults and keep their behavior.

- [ ] **Step 4: Run agent regressions**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "temperature_is_zero or ignores_global" tests/test_agent_hardening.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/agent.py ai-module/tests/test_semantic_verifier.py
git commit -m "feat(ai): support dedicated zero-temperature agents"
```

---

### Task 2: Create Dataset Protocol And Validation

**Files:**
- Create: `ai-module/eval/semantic_grounding/protocol.py`
- Create: `ai-module/eval/semantic_grounding/validate_dataset.py`
- Create: `ai-module/eval/semantic_grounding/dataset/qv-pseudo-v1.jsonl`
- Create: `ai-module/eval/semantic_grounding/dataset/boundary.jsonl`
- Create: `ai-module/tests/test_semantic_grounding_dataset.py`

**Interfaces:**
- Produces: `validate_dataset(base_path, boundary_path) -> dict`
- Produces: `source_group_id` grouping and `split` constraints.

- [ ] **Step 1: Write failing dataset tests**

```python
from pathlib import Path
from eval.semantic_grounding.validate_dataset import validate_dataset

DATASET_DIR = Path(__file__).parents[1] / "eval/semantic_grounding/dataset"


def test_base_dataset_quotas_and_no_group_leakage():
    summary = validate_dataset(DATASET_DIR / "qv-pseudo-v1.jsonl",
                               DATASET_DIR / "boundary.jsonl")
    assert summary["base_total"] == 150
    assert summary["base_labels"] == {
        "entailed": 50, "neutral": 50, "contradicted": 50,
    }
    assert summary["dev_total"] == 90
    assert summary["test_total"] == 60
    assert summary["group_leakage"] == []
    assert 20 <= summary["boundary_total"] <= 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_semantic_grounding_dataset.py::test_base_dataset_quotas_and_no_group_leakage -q`

Expected: FAIL because dataset files and validator are missing.

- [ ] **Step 3: Define schema and validation**

Each base row:

```json
{
  "id": "qv-001",
  "source_group_id": "case-2026-001",
  "category": "dangerous_building",
  "slot": "structure",
  "slot_class": "A",
  "value": "墙体倾斜",
  "quote": "房子明显往一边斜",
  "source_text": "房子明显往一边斜",
  "split": "dev",
  "expected_label": "entailed"
}
```

Implemented validation:

```python
LABELS = {"entailed", "neutral", "contradicted"}
SPLITS = {"dev", "test"}


def validate_dataset(base_path, boundary_path):
    base = [json.loads(line) for line in Path(base_path).read_text(encoding="utf-8").splitlines() if line]
    boundary = [json.loads(line) for line in Path(boundary_path).read_text(encoding="utf-8").splitlines() if line]
    # Validate unique ids, canonical category/slot, slot_class in A/B/C,
    # quote and source_text non-empty, split in dev/test, expected_label in LABELS.
    # Enforce base_total=150, each label 50, dev_total=90, test_total=60.
    # Reject the same source_group_id in both dev and test.
    # Enforce 20 <= boundary_total <= 30; boundary rows use split="boundary".
    return summary
```

Base dataset construction rules:
- Prioritize real conversation quote/value pairs.
- Reuse candidates derived from current tests when real data is unavailable.
- Add template-generated positive/negative/contradiction cases.
- Add boundary cases for synonyms, negation, numbers, multi-turn references, vision source, and assistant-source misuse.
- Do not store full user conversations; keep only necessary evidence snippets.
- Never fabricate evidence that is claimed to be from a real conversation.
- `expected_label` is only a construction/stratification target, never a human gold label and never sent to labelers or used as threshold ground truth. Consensus labels are the calibration reference.

- [ ] **Step 4: Run dataset validation**

Run: `python -m pytest tests/test_semantic_grounding_dataset.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/eval/semantic_grounding/protocol.py ai-module/eval/semantic_grounding/validate_dataset.py ai-module/eval/semantic_grounding/dataset ai-module/tests/test_semantic_grounding_dataset.py
git commit -m "data: add semantic grounding pseudo-label dataset"
```

---
### Task 3: Add Deterministic Prefilter

**Files:**
- Create: `ai-module/eval/semantic_grounding/deterministic_prefilter.py`
- Test: `ai-module/tests/test_semantic_grounding_prefilter.py`

**Interfaces:**
- Produces: `prefilter_sample(sample) -> dict`
- Decision values: `invalid_source`, `grounded`, `contradicted`, `echo`, `needs_verifier`.

- [ ] **Step 1: Write failing prefilter tests**

```python
from eval.semantic_grounding.deterministic_prefilter import prefilter_sample


def test_direct_quote_support_skips_models():
    sample = {
        "category": "fire_lane_blocked", "slot": "blocker",
        "value": "杂物", "quote": "被杂物堵住", "source_text": "消防通道被杂物堵住",
    }
    assert prefilter_sample(sample)["decision"] == "grounded"


def test_quote_outside_source_is_invalid():
    sample = {
        "category": "fire_lane_blocked", "slot": "blocker",
        "value": "杂物", "quote": "被车辆堵住", "source_text": "消防通道被杂物堵住",
    }
    assert prefilter_sample(sample)["decision"] == "invalid_source"


def test_synonym_case_requires_verifier():
    sample = {
        "category": "dangerous_building", "slot": "structure",
        "value": "墙体倾斜", "quote": "房子明显往一边斜",
        "source_text": "房子明显往一边斜",
    }
    assert prefilter_sample(sample)["decision"] == "needs_verifier"
```

- [ ] **Step 2: Implement deterministic routing**

```python
from core.uncertainty import _digits_preserved, _negated_near_quote, is_echo_slot, normalize_text


def prefilter_sample(sample):
    value = str(sample.get("value") or "").strip()
    quote = str(sample.get("quote") or "").strip()
    source = str(sample.get("source_text") or "").strip()
    category = str(sample.get("category") or "").strip()
    if not quote or not source or normalize_text(quote) not in normalize_text(source):
        return {"decision": "invalid_source", "reason": "quote_not_in_source"}
    if is_echo_slot(value, category):
        return {"decision": "echo", "reason": "label_echo"}
    if normalize_text(value) in normalize_text(quote):
        return {"decision": "grounded", "reason": "direct_quote_support"}
    if not _digits_preserved(value, source):
        return {"decision": "contradicted", "reason": "numeric_mismatch"}
    if _negated_near_quote(source, quote, value):
        return {"decision": "contradicted", "reason": "negation_conflict"}
    return {"decision": "needs_verifier", "reason": "weak_value"}
```

Only `needs_verifier` rows are sent to the dual labelers. Deterministic `invalid_source`, `grounded`, `contradicted`, and `echo` decisions are preserved separately and are not converted into model calls.

- [ ] **Step 3: Run prefilter tests**

Run: `python -m pytest tests/test_semantic_grounding_prefilter.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add ai-module/eval/semantic_grounding/deterministic_prefilter.py ai-module/tests/test_semantic_grounding_prefilter.py
git commit -m "feat(eval): add deterministic semantic prefilter"
```

---
### Task 4: Configure Two Independent Labelers And Run JSONL Labeling

**Files:**
- Modify: `ai-module/config.py`
- Modify: `ai-module/.env.example`
- Create: `ai-module/eval/semantic_grounding/labeler_config.py`
- Create: `ai-module/eval/semantic_grounding/run_labelers.py`
- Test: `ai-module/tests/test_semantic_grounding_labelers.py`

**Interfaces:**
- Produces: `build_labeler("A" | "B") -> Agent`
- Produces: `label_rows(rows, labeler) -> dict[id, dict]`
- Produces: `labels_A.jsonl`, `labels_B.jsonl`, `deterministic.jsonl`.

- [ ] **Step 1: Write failing labeler tests**

```python
from eval.semantic_grounding.labeler_config import build_labeler


def test_labelers_use_distinct_models(monkeypatch):
    monkeypatch.setenv("SEMANTIC_LABELER_A_BASE_URL", "http://a")
    monkeypatch.setenv("SEMANTIC_LABELER_A_API_KEY", "ka")
    monkeypatch.setenv("SEMANTIC_LABELER_A_MODEL", "minimax-m3.1-flash")
    monkeypatch.setenv("SEMANTIC_LABELER_B_BASE_URL", "http://b")
    monkeypatch.setenv("SEMANTIC_LABELER_B_API_KEY", "kb")
    monkeypatch.setenv("SEMANTIC_LABELER_B_MODEL", "glm-5.3-flash")
    a = build_labeler("A")
    b = build_labeler("B")
    assert a.base_url == "http://a"
    assert a.model == "minimax-m3.1-flash"
    assert b.base_url == "http://b"
    assert b.model == "glm-5.3-flash"
    assert a.temperature == 0.0
    assert b.temperature == 0.0
```

- [ ] **Step 2: Implement environment configuration**

In `config.py`:

```python
SEMANTIC_LABELER_A_BASE_URL = os.getenv("SEMANTIC_LABELER_A_BASE_URL", "")
SEMANTIC_LABELER_A_API_KEY = os.getenv("SEMANTIC_LABELER_A_API_KEY", "")
SEMANTIC_LABELER_A_MODEL = os.getenv("SEMANTIC_LABELER_A_MODEL", "minimax-m3.1-flash")
SEMANTIC_LABELER_B_BASE_URL = os.getenv("SEMANTIC_LABELER_B_BASE_URL", "")
SEMANTIC_LABELER_B_API_KEY = os.getenv("SEMANTIC_LABELER_B_API_KEY", "")
SEMANTIC_LABELER_B_MODEL = os.getenv("SEMANTIC_LABELER_B_MODEL", "glm-5.3-flash")
```

In `.env.example`:

```ini
SEMANTIC_LABELER_A_BASE_URL=https://amr-link.open-design.ai/v1
SEMANTIC_LABELER_A_API_KEY=replace-with-minimax-key
SEMANTIC_LABELER_A_MODEL=minimax-m3.1-flash
SEMANTIC_LABELER_B_BASE_URL=https://amr-link.open-design.ai/v1
SEMANTIC_LABELER_B_API_KEY=replace-with-glm-key
SEMANTIC_LABELER_B_MODEL=glm-5.3-flash
```

Do not put real keys in Git.

- [ ] **Step 3: Build dedicated agents**

```python
_LABELER_SYSTEM_PROMPT = (
    "你是槽位证据关系标注器。只判断 quote 是否支持 value。"
    "relation 只能是 entailed / contradicted / neutral。"
    "不重新抽取事实，不参考对话，不使用工具。"
    "只输出 JSON：{\"label\":\"...\",\"confidence\":0.0}。"
)


def build_labeler(key):
    base = os.getenv(f"SEMANTIC_LABELER_{key}_BASE_URL", "")
    api_key = os.getenv(f"SEMANTIC_LABELER_{key}_API_KEY", "")
    model = os.getenv(f"SEMANTIC_LABELER_{key}_MODEL", "")
    if not base or not api_key or not model:
        raise RuntimeError(f"semantic labeler {key} is not configured")
    return Agent(
        name=f"semantic_labeler_{key.lower()}",
        system_prompt=_LABELER_SYSTEM_PROMPT,
        tools=[],
        base_url=base,
        api_key=api_key,
        model=model,
        temperature=0.0,
        use_configured_slot=False,
        allow_fallback=False,
    )
```

The input message contains only:

```json
{"slot":"structure","slot_question":"墙体是否有裂缝、倾斜或沉降？","value":"墙体倾斜","quote":"房子明显往一边斜"}
```

It must not contain `expected_label`, `split`, `source_group_id`, `category`, full dialogue, or the other model's result.

- [ ] **Step 4: Implement JSONL runner**

`run_labelers.py` must:

```text
1. load the requested split
2. run deterministic_prefilter
3. skip rows whose decision is not needs_verifier
4. call labeler A and labeler B independently
5. parse exactly one JSON object with label/confidence
6. write deterministic.jsonl, labels_A.jsonl, labels_B.jsonl
7. never write expected_label into the labeler prompt
```

Invalid JSON, invalid label, out-of-range confidence, or timeout is stored as:

```json
{"id":"qv-001","label":"invalid","reason":"parse_or_request_failed"}
```

- [ ] **Step 5: Run labeler tests**

Run: `python -m pytest tests/test_semantic_grounding_labelers.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai-module/config.py ai-module/.env.example ai-module/eval/semantic_grounding/labeler_config.py ai-module/eval/semantic_grounding/run_labelers.py ai-module/tests/test_semantic_grounding_labelers.py
git commit -m "feat(eval): run independent semantic labelers"
```

---
### Task 5: Compute Dual-Model Consensus And Quality Gates

**Files:**
- Create: `ai-module/eval/semantic_grounding/consensus.py`
- Test: `ai-module/tests/test_semantic_grounding_consensus.py`

**Interfaces:**
- Produces: `cohen_kappa(labels_a, labels_b) -> float`
- Produces: `build_consensus(deterministic_rows, labels_a, labels_b) -> dict`
- Outputs: `consensus.jsonl`, `disagreement.jsonl`, `agreement_summary.json`.

- [ ] **Step 1: Write failing metric tests**

```python
from eval.semantic_grounding.consensus import cohen_kappa, merge_pair


def test_exact_agreement_and_disagreement():
    assert merge_pair("entailed", "entailed") == {"label": "entailed", "status": "agreed"}
    assert merge_pair("entailed", "neutral") == {"label": "ambiguous", "status": "disagreed"}


def test_cohen_kappa():
    assert cohen_kappa(["entailed", "neutral", "contradicted"],
                       ["entailed", "neutral", "contradicted"]) == 1.0
    kappa = cohen_kappa(["entailed", "entailed", "neutral", "neutral"],
                        ["entailed", "neutral", "neutral", "neutral"])
    assert 0.0 <= kappa < 1.0
```

- [ ] **Step 2: Implement consensus metrics**

```python
LABELS = ("entailed", "neutral", "contradicted")


def merge_pair(a, b):
    if a in LABELS and b in LABELS and a == b:
        return {"label": a, "status": "agreed"}
    return {"label": "ambiguous", "status": "disagreed"}


def cohen_kappa(a, b):
    if len(a) != len(b) or not a:
        return 0.0
    observed = sum(x == y for x, y in zip(a, b)) / len(a)
    expected = 0.0
    for label in LABELS:
        pa = sum(x == label for x in a) / len(a)
        pb = sum(x == label for x in b) / len(b)
        expected += pa * pb
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)
```

`build_consensus()` must combine deterministic decisions and dual-model labels, and produce:

```json
{
  "overall_agreement": 0.82,
  "cohen_kappa": 0.71,
  "label_agreement": {"entailed":0.84,"neutral":0.79,"contradicted":0.82},
  "class_agreement": {"A":0.80,"B":0.86},
  "agreed_count":0,
  "disagreed_count":0,
  "invalid_count":0
}
```

Quality gate:

```python
def assert_quality_gate(summary):
    if summary["overall_agreement"] < 0.75:
        raise ValueError("overall_agreement below 0.75")
    if summary["cohen_kappa"] < 0.60:
        raise ValueError("cohen_kappa below 0.60")
```

Do not proceed to threshold calibration if the gate fails.

- [ ] **Step 3: Write disagreement artifact**

Each disagreement row:

```json
{
  "id":"qv-014",
  "slot_class":"A",
  "label_a":"entailed",
  "confidence_a":0.91,
  "label_b":"neutral",
  "confidence_b":0.73
}
```

Do not include full source conversations.

- [ ] **Step 4: Run consensus tests**

Run: `python -m pytest tests/test_semantic_grounding_consensus.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/eval/semantic_grounding/consensus.py ai-module/tests/test_semantic_grounding_consensus.py
git commit -m "feat(eval): add dual-model consensus metrics"
```

---
### Task 6: Calibrate Dev Thresholds Without Weakening Precision

**Files:**
- Create: `ai-module/eval/semantic_grounding/calibrate_thresholds.py`
- Test: `ai-module/tests/test_semantic_grounding_calibration.py`

**Interfaces:**
- Produces: `scan_thresholds(rows, slot_class, target_precision) -> dict`
- Produces: `thresholds.json` with `threshold_a`, `threshold_b`, `threshold_c`.

- [ ] **Step 1: Write failing calibration test**

```python
from eval.semantic_grounding.calibrate_thresholds import scan_thresholds

ROWS = [
    {"label":"entailed","min_confidence":0.91,"slot_class":"A","runtime_label_a":"entailed"},
    {"label":"entailed","min_confidence":0.84,"slot_class":"A","runtime_label_a":"entailed"},
    {"label":"neutral","min_confidence":0.90,"slot_class":"A","runtime_label_a":"entailed"},
]


def test_scan_picks_lowest_threshold_meeting_precision():
    best = scan_thresholds(ROWS, "A", target_precision=0.98)
    assert best["threshold"] == 0.91
```

- [ ] **Step 2: Implement threshold scan**

Use only dev rows whose dual labels agree. Scan:

```python
THRESHOLDS = (0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
```

For each threshold:

```python
auto_accept = [row for row in rows
               if row["runtime_label_a"] == "entailed"
               and row["min_confidence"] >= threshold]
correct = [row for row in auto_accept if row["label"] == "entailed"]
precision = len(correct) / len(auto_accept) if auto_accept else 0.0
coverage = len(correct) / len([row for row in rows if row["label"] == "entailed"])
false_accept_proxy = len([row for row in auto_accept if row["label"] != "entailed"]) / len(
    [row for row in rows if row["label"] != "entailed"]
)
```

Select:

```python
eligible = [r for r in results if r["precision"] >= target_precision and r["coverage"] > 0]
if not eligible:
    raise ValueError("no threshold meets precision target with non-zero coverage")
best = min(eligible, key=lambda item: item["threshold"])
```

- [ ] **Step 3: Class-specific calibration**

```text
threshold_a: dual consensus A-class rows, target precision 0.98
threshold_b: labeler A only vs dual consensus, B-class rows, target precision 0.95
threshold_c: contradicted rows, rejection precision >= 0.95
```

Runtime B uses single labeler A for entailment, so `threshold_b` must be calibrated from labeler A outputs against consensus labels, not from dual min-confidence alone.

For `threshold_c`, if no threshold meets rejection precision, use `unavailable` instead of automatic contradiction rejection.

- [ ] **Step 4: Write calibration artifacts**

Create `calibration/` with:

```text
threshold_scan_a.json
threshold_scan_b.json
threshold_scan_c.json
thresholds.json
```

`thresholds.json`:

```json
{"threshold_a":0.91,"threshold_b":0.84,"threshold_c":0.90,"dataset":"qv-pseudo-v1"}
```

The report must state:

```text
Thresholds were calibrated against dual-model consensus pseudo-labels.
No human review was performed.
```

- [ ] **Step 5: Run calibration tests**

Run: `python -m pytest tests/test_semantic_grounding_calibration.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai-module/eval/semantic_grounding/calibrate_thresholds.py ai-module/tests/test_semantic_grounding_calibration.py
git commit -m "feat(eval): calibrate semantic pseudo-label thresholds"
```

---
### Task 7: Freeze Test Artifacts And Evaluate Once

**Files:**
- Create: `ai-module/eval/semantic_grounding/freeze_test.py`
- Create: `ai-module/eval/semantic_grounding/evaluate_test.py`
- Create: `ai-module/eval/semantic_grounding/report.py`
- Test: `ai-module/tests/test_semantic_grounding_freeze.py`

**Interfaces:**
- Produces: `frozen_test.json`
- Produces: `test_metrics.json`, `REPORT.md`.

- [ ] **Step 1: Write failing freeze test**

```python
import json
from pathlib import Path
import pytest
from eval.semantic_grounding.freeze_test import freeze_manifest


def test_freeze_captures_hashes(tmp_path):
    dataset = tmp_path / "test.jsonl"
    dataset.write_text('{"id":"qv-001"}\n', encoding="utf-8")
    manifest = freeze_manifest(
        dataset_path=dataset,
        model_a="minimax-m3.1-flash",
        model_b="glm-5.3-flash",
        prompt="PROMPT",
        thresholds={"threshold_a":0.91,"threshold_b":0.84,"threshold_c":0.90},
    )
    assert manifest["test_sha256"]
    assert manifest["prompt_sha256"]
    assert manifest["models"] == ["minimax-m3.1-flash", "glm-5.3-flash"]


def test_freeze_refuses_second_write(tmp_path):
    out = tmp_path / "frozen_test.json"
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        freeze_manifest(dataset_path=tmp_path / "missing.jsonl", model_a="a", model_b="b",
                        prompt="P", thresholds={}, output_path=out)
```

- [ ] **Step 2: Implement freeze manifest**

`frozen_test.json` must include:

```json
{
  "dataset": "qv-pseudo-v1",
  "split": "test",
  "test_sha256": "...",
  "prompt_sha256": "...",
  "models": ["minimax-m3.1-flash", "glm-5.3-flash"],
  "thresholds": {"threshold_a":0.91,"threshold_b":0.84,"threshold_c":0.90},
  "frozen_at": "2026-11-24T00:00:00+00:00"
}
```

Refuse to overwrite an existing manifest.

- [ ] **Step 3: Implement one-shot test evaluation**

`evaluate_test.py` must:

```text
1. require frozen_test.json
2. verify dataset and prompt hashes before calling models
3. run labeler A and B exactly once on test
4. compute agreement, kappa, auto-accept precision, coverage
5. emit test_metrics.json
6. never modify thresholds
```

Report wording must include:

```text
Thresholds and evaluation use dual-model consensus pseudo-labels.
No human gold labels were available.
Test metrics are pseudo-label agreement metrics, not production accuracy.
```

- [ ] **Step 4: Run freeze tests**

Run: `python -m pytest tests/test_semantic_grounding_freeze.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/eval/semantic_grounding/freeze_test.py ai-module/eval/semantic_grounding/evaluate_test.py ai-module/eval/semantic_grounding/report.py ai-module/tests/test_semantic_grounding_freeze.py
git commit -m "feat(eval): freeze and evaluate semantic pseudo-label test"
```

---
### Task 8: Implement Runtime Dual-Model Semantic Verifier

**Files:**
- Create or modify: `ai-module/core/semantic_verifier.py`
- Modify: `ai-module/eval/semantic_grounding/labeler_config.py`
- Modify: `ai-module/config.py`
- Modify: `ai-module/.env.example`
- Create: `ai-module/tests/test_semantic_verifier.py`

**Interfaces:**
- Produces: `collect_weak_candidates(issues, audit, max_items=5) -> list[dict]`
- Produces: `verify_weak_slots(issues, audit, cancellation=None) -> dict`
- Produces: `grounded`, `grounded_by_model`, `rejected`, `unavailable` business statuses.

- [ ] **Step 1: Move shared labeler construction to core**

To prevent offline/runtime prompt drift, make `core/semantic_verifier.py` the single source for:

```python
SEMANTIC_LABELER_PROMPT
build_labeler("A" | "B")
```

`eval/semantic_grounding/labeler_config.py` should import these from `core.semantic_verifier`, not maintain a second prompt copy.

- [ ] **Step 2: Add runtime verifier configuration**

In `config.py`:

```python
SEMANTIC_VERIFIER_A_THRESHOLD = float(
    os.getenv("SEMANTIC_VERIFIER_A_THRESHOLD", "0.91")
)
SEMANTIC_VERIFIER_B_THRESHOLD = float(
    os.getenv("SEMANTIC_VERIFIER_B_THRESHOLD", "0.84")
)
SEMANTIC_VERIFIER_C_THRESHOLD = float(
    os.getenv("SEMANTIC_VERIFIER_C_THRESHOLD", "0.90")
)
SEMANTIC_VERIFIER_MAX_ITEMS = int(
    os.getenv("SEMANTIC_VERIFIER_MAX_ITEMS", "5")
)
```

Add matching values to `.env.example`.

- [ ] **Step 3: Write failing runtime tests**

```python
from core import semantic_verifier as sv


def test_a_class_requires_both_models(monkeypatch):
    issue = {
        "major_code": "fire",
        "subcategory_code": "fire_lane_blocked",
        "slots": {"blocker": "杂物"},
    }
    audit = {"fire_lane_blocked": {"blocker": {
        "status": "weak", "quote": "有东西", "source_ref": "u1",
        "value": "杂物", "business_status": "unavailable",
    }}}
    monkeypatch.setattr(sv, "_call_labeler", lambda key, candidates, cancellation=None: {
        "fire_lane_blocked:blocker": {"label": "entailed", "confidence": 0.95},
    })
    result = sv.verify_weak_slots([issue], audit)
    assert result["fire_lane_blocked"]["blocker"]["business_status"] == "grounded_by_model"


def test_a_class_needs_both_models(monkeypatch):
    issue = {
        "major_code": "fire",
        "subcategory_code": "fire_lane_blocked",
        "slots": {"blocker": "杂物"},
    }
    audit = {"fire_lane_blocked": {"blocker": {
        "status": "weak", "quote": "有东西", "source_ref": "u1",
        "value": "杂物", "business_status": "unavailable",
    }}}

    def fake(key, candidates, cancellation=None):
        if key == "A":
            return {"fire_lane_blocked:blocker": {"label": "entailed", "confidence": 0.95}}
        return {"fire_lane_blocked:blocker": {"label": "neutral", "confidence": 0.80}}

    monkeypatch.setattr(sv, "_call_labeler", fake)
    result = sv.verify_weak_slots([issue], audit)
    assert result["fire_lane_blocked"]["blocker"]["business_status"] == "unavailable"
```

Use stable candidate ids such as `fire_lane_blocked:blocker`.

- [ ] **Step 4: Implement candidate collection**

```python
def collect_weak_candidates(issues, audit, max_items=5):
    candidates = []
    for issue in issues or []:
        code = str(issue.get("subcategory_code") or "")
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
    candidates.sort(key=lambda row: 0 if row["value_class"] == "A" else 1)
    return candidates[:max_items]
```

- [ ] **Step 5: Implement a single model batch call**

Each batch input contains only `id`, `slot`, `slot_question`, `value`, `quote`. No dialogue, no expected label, no other model's result, no tools.

Use `_semantic_labeler_a` / `_semantic_labeler_b` created with:

```python
build_labeler("A")  # MiniMax M3.1 Flash
build_labeler("B")  # GLM-5.3 Flash
```

Both use `temperature=0.0`, `use_configured_slot=False`, `allow_fallback=False`.

Call A once for all selected candidates. Build a B candidate subset containing:

```text
all A-class candidates
+ B-class candidates whose A label is contradicted
```

Call B at most once. Do not call B for B-class candidates whose A label is entailed/neutral/unknown.

- [ ] **Step 6: Apply runtime consensus rules**

```python
def _a_class_status(a, b):
    if a["label"] == b["label"] == "entailed" and min(a["confidence"], b["confidence"]) >= A_THRESHOLD:
        return "grounded_by_model"
    if a["label"] == b["label"] == "contradicted" and min(a["confidence"], b["confidence"]) >= C_THRESHOLD:
        return "rejected"
    return "unavailable"


def _b_class_status(a, b):
    if a["label"] == "entailed" and a["confidence"] >= B_THRESHOLD:
        return "grounded_by_model"
    if (a["label"] == "contradicted" and b
            and b["label"] == "contradicted"
            and min(a["confidence"], b["confidence"]) >= C_THRESHOLD):
        return "rejected"
    return "unavailable"
```

All exceptions, invalid JSON, missing ids, invalid labels, invalid confidence, disagreement, timeout, or failed B confirmation become `unavailable`.

- [ ] **Step 7: Write status fields into audit**

For accepted model entailment:

```python
result["status"] = "grounded_by_model"
result["business_status"] = "grounded_by_model"
result["reason"] = "model_consensus_entailed"
result["model_a"] = {"label": a["label"], "confidence": a["confidence"]}
result["model_b"] = {"label": b["label"], "confidence": b["confidence"]}
```

For rejection:

```python
result["status"] = "rejected"
result["business_status"] = "rejected"
result["reason"] = "model_consensus_contradicted"
```

For invalid/indeterminate:

```python
result["status"] = "unavailable"
result["business_status"] = "unavailable"
result["reason"] = reason
```

- [ ] **Step 8: Add runtime tests**

At least cover:

```text
A-class dual entailed above T_A -> grounded_by_model
A-class one model neutral -> unavailable
A-class dual contradicted above T_C -> rejected
B-class A entailed above T_B -> grounded_by_model with one labeler call
B-class A contradicted + B confirmed -> rejected
B-class A contradicted + B neutral -> unavailable
A timeout -> unavailable
invalid JSON -> unavailable
more than five weak candidates -> only five sent
maximum two labeler calls per turn
```

- [ ] **Step 9: Run runtime verifier tests**

Run: `python -m pytest tests/test_semantic_verifier.py -q`

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add ai-module/core/semantic_verifier.py ai-module/eval/semantic_grounding/labeler_config.py ai-module/config.py ai-module/.env.example ai-module/tests/test_semantic_verifier.py
git commit -m "feat(ai): add runtime dual-model semantic verifier"
```

---
### Task 9: Add Four Business States

**Files:**
- Modify: `ai-module/core/uncertainty.py`
- Modify: `ai-module/tests/test_slot_evidence.py`

**Interfaces:**
- Produces: `business_status` on every evidence audit result.
- Internal detailed `status`/`reason` remain available for logs.

- [ ] **Step 1: Write failing business-state tests**

```python
from core.uncertainty import verify_slot_evidence

SOURCE_MAP = {"u1": "消防通道长期堆着杂物", "u2": "房子明显往一边斜"}


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

- [ ] **Step 2: Implement mapping**

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

Apply to every `verify_slot_evidence()` return. In `assess()`, apply it to legacy fallback results too. Keep detailed statuses as internal reasons.

- [ ] **Step 3: Run evidence tests**

Run: `python -m pytest tests/test_slot_evidence.py tests/test_uncertainty.py -q`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add ai-module/core/uncertainty.py ai-module/tests/test_slot_evidence.py
git commit -m "feat(ai): add four semantic business states"
```

---
### Task 10: Integrate Runtime Verifier Inside understand

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Modify: `ai-module/core/uncertainty.py`
- Test: `ai-module/tests/test_semantic_verifier.py`

**Interfaces:**
- Consumes: `slot_evidence_audit`
- Produces: final slots, missing, report_missing, issue unverified.

- [ ] **Step 1: Write failing integration tests**

```python
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
            "evidence": [{"slot": "blocker", "quote": "有东西", "source_ref": "u1"}],
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
    out = ag.understand({"messages": [ag.HumanMessage(content="消防通道长期被杂物堵住")]})
    assert "fire_lane_blocked_blocker" not in out["missing"]
    assert "impact" in out["issues"][0]["report_missing"]
```

Add helper `_mark(audit, code, slot, business_status)` that mutates and returns audit.

- [ ] **Step 2: Move missing calculation after evidence verification**

Remove the current early `category_slots / missing / report_missing` block. Recommended order:

```text
finalize issues
 -> assess deterministic evidence
 -> enforce-only verify_weak_slots
 -> build category_slots
 -> remove rejected/unavailable slots
 -> rebuild missing/report_missing
 -> policy
```

- [ ] **Step 3: Add removal and rebuild helpers**

```python
def _drop_unusable_slots(issues, category_slots, audit):
    removed = []
    for issue in issues:
        code = issue.get("subcategory_code") or ""
        for slot in list((issue.get("slots") or {}).keys()):
            result = ((audit.get(code) or {}).get(slot) or {})
            if result.get("business_status") not in {"rejected", "unavailable"}:
                continue
            issue["slots"].pop(slot, None)
            category_slots.setdefault(code, {}).pop(slot, None)
            removed.append(f"{code}.{slot}")
    return removed
```

```python
def _rebuild_issue_missing(issues, category_slots):
    missing = rebuild_missing(
        [issue["subcategory_code"] for issue in issues], category_slots
    )
    report_missing = rebuild_report_missing(
        [issue["subcategory_code"] for issue in issues], category_slots
    )
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

- [ ] **Step 4: Call verifier only in enforce mode**

```python
verdict = _apply_evidence_mode(assess(plan, source_messages, vision_summary))
if SLOT_EVIDENCE_MODE == "enforce":
    verdict["slot_evidence_audit"] = verify_weak_slots(
        issues,
        verdict.get("slot_evidence_audit") or {},
        _cancel_token(config),
    )
```

Then build and drop slots, rebuild missing, and only then call `decide_next_action()`.

- [ ] **Step 5: Preserve askability in enforce mode**

Use:

```python
evidence_cautions = bool(plan.get("major_mismatch"))
```

for enforce business evidence. `unavailable/rejected` must not set `cautious`; they become missing. Keep legacy caution for `off` and `shadow`.

Set issue unverified as:

```python
if SLOT_EVIDENCE_MODE == "enforce":
    issue["unverified"] = []
else:
    issue["unverified"] = unverified.get(issue["subcategory_code"], [])
```

- [ ] **Step 6: Run focused integration tests**

Run: `python -m pytest tests/test_semantic_verifier.py -q -k "a_unavailable or b_unavailable or grounded_by_model" tests/test_uncertainty.py tests/test_uncertainty_gating.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add ai-module/core/assistant_graph.py ai-module/core/uncertainty.py ai-module/tests/test_semantic_verifier.py
git commit -m "feat(ai): apply dual-model grounding inside understand"
```

---
### Task 11: Preserve Off/Shadow, SSE Boundary, And Full Regression

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Test: `ai-module/tests/test_semantic_verifier.py`
- Test: `ai-module/tests/test_slot_evidence.py`
- Test: `ai-module/tests/test_task_gate_interrupt.py`
- Modify: `docs/current/agent-orchestration.md`

**Interfaces:**
- Guarantees no labeler call outside enforce and no evidence leakage.

- [ ] **Step 1: Write shadow/off regression tests**

```python
def _weak_plan_for_mode():
    return {
        "ok": True, "intent": "report_hazard", "risk_level": "high",
        "issues": [{
            "major_code": "building", "subcategory_code": "dangerous_building",
            "slots": {"structure": "墙体倾斜"},
            "evidence": [{"slot": "structure", "quote": "房子明显往一边斜", "source_ref": "u1"}],
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
    monkeypatch.setattr(ag, "verify_weak_slots", lambda *a, **k: calls.append(1) or {})
    ag.understand({"messages": [ag.HumanMessage(content="房子明显往一边斜")]})
    assert calls == []


def test_off_does_not_call_labelers(monkeypatch):
    import core.assistant_graph as ag
    calls = []
    monkeypatch.setattr(ag, "SLOT_EVIDENCE_MODE", "off")
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: _weak_plan_for_mode())
    monkeypatch.setattr(ag, "verify_weak_slots", lambda *a, **k: calls.append(1) or {})
    ag.understand({"messages": [ag.HumanMessage(content="房子明显往一边斜")]})
    assert calls == []
```

- [ ] **Step 2: Verify evidence remains private**

```python
def test_public_issue_strips_semantic_audit():
    from core.assistant_graph import _public_issues
    issue = {
        "subcategory_code": "dangerous_building",
        "evidence": [{"slot": "structure", "quote": "往一边斜", "source_ref": "u1"}],
        "slot_evidence": {
            "structure": {"status": "grounded_by_model", "business_status": "grounded_by_model"}
        },
    }
    public = _public_issues([issue])[0]
    assert "evidence" not in public
    assert "slot_evidence" not in public
```

Keep the existing interrupt redaction test passing.

- [ ] **Step 3: Document pseudo-label caveat**

In `docs/current/agent-orchestration.md`, add:

```text
Thresholds are calibrated from dual-model consensus pseudo-labels.
No human gold labels exist for this calibration.
Runtime A-class decisions require dual-model agreement.
Runtime B-class acceptance may use one model above the calibrated threshold.
All disagreement, low confidence, timeout, and invalid output become unavailable.
```

- [ ] **Step 4: Run full AI regression excluding external MySQL**

Run: `python -m pytest tests -q --ignore=tests/test_memory_store.py`

Expected: PASS.

- [ ] **Step 5: Run compile check**

Run: `python -m compileall core eval tests -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai-module/core/assistant_graph.py ai-module/tests/test_semantic_verifier.py ai-module/tests/test_slot_evidence.py ai-module/tests/test_task_gate_interrupt.py docs/current/agent-orchestration.md
git commit -m "test(ai): preserve dual-model semantic boundaries"
```

---

## Threshold Calibration Is Not Accuracy Validation

Do not describe the pseudo-label scores as human-validated accuracy.

Required wording:

```text
Thresholds were selected against dual-model consensus pseudo-labels.
No human review was performed.
Test metrics measure agreement with pseudo-labels, not production accuracy.
```

If the quality gate or precision target cannot be met:

```text
raise thresholds
or return unavailable
do not relax precision targets
do not hand-label and claim human gold unless a real human review pass happened
```

## Final Acceptance Checklist

- [ ] Base dataset has 150 rows, 50 per pseudo-label, split 90/60 by source group.
- [ ] Boundary set has 20–30 rows and is not used for threshold selection.
- [ ] Deterministic filters run before labeler calls.
- [ ] Labelers are independent, `temperature=0`, no history, no tools, no fallback.
- [ ] Agreement and kappa meet gates before calibration.
- [ ] Disagreements are stored separately and excluded from calibration.
- [ ] Thresholds are chosen on dev only and satisfy precision targets.
- [ ] Test set is frozen once and not used for tuning.
- [ ] Runtime makes at most two labeler calls per turn.
- [ ] A class requires dual-model agreement for accept/reject.
- [ ] B class can accept via one model above calibrated threshold.
- [ ] B contradiction requires model B confirmation.
- [ ] Runtime failures never auto-accept.
- [ ] A unavailable slots return to missing and re-ask the original slot.
- [ ] B unavailable slots become report_missing and are not asserted facts.
- [ ] No confirmation node or extra user round is introduced.
- [ ] Evidence remains absent from SSE, interrupt, report, and Java/MySQL.
- [ ] Off/shadow behavior remains unchanged.
- [ ] Full AI regression passes.