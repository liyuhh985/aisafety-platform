# Vision Evaluation v2.1 Interview-Grade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and freeze a human-reviewed 160-image vision diagnostic set, compare baseline and final prompts on the same test split, and produce only evidence-backed interview material.

**Architecture:** Keep v2.0 draft artifacts as audit history. Add a v2.1 candidate-reservoir pipeline: build more candidates than needed, preserve previously confirmed labels as review seeds, obtain human decisions, select exactly 80 positives and 80 hard negatives, freeze a 40/40 test split, run two prompt arms at temperature 0, and generate metrics plus error analysis.

**Tech Stack:** Python 3.11+, Pillow, existing `VisionClient`, pytest, CSV/JSONL, Markdown.

## Global Constraints

- Protocol version is `v2.1`.
- Final dataset has exactly 160 items: 80 positives and 80 negatives.
- Final dataset has dev 80 and test 80.
- Test has exactly 40 positives and 40 negatives.
- Each of 8 major categories has exactly 10 positive items total and 5 test positive items.
- Each of 8 confuser groups has exactly 10 negative items total and 5 test negative items.
- All 160 final labels are human-reviewed.
- Frozen test label sources are only `human_reviewed`, `human_confirmed_ai_prelabel`, and `legacy_review`.
- `ai_direct` never enters a frozen test label.
- Exact SHA-256 duplicates and dHash near-duplicates are rejected.
- Test and dev must not share an exact hash or a dHash distance `<= 4`.
- `freeze_test.py` counts final `has_hazard`, never `candidate_kind`.
- Baseline and final prompts run once on the frozen test at temperature `0`.
- Low confidence means human review; it is not a probability and not an automatic negative.
- Never call balanced test accuracy production accuracy or test FPR production FPR.
- If final does not beat baseline, write a failed-experiment analysis instead of an improvement claim.
- The old v2.0 `review_decisions.jsonl`, pending backups, and `REVIEW_SUMMARY.md` remain audit artifacts.

---

## File Structure

Create or modify under `ai-module/eval/vision/v2/`:

- `contract.py` — v2.1 constants and allowed label sources.
- `dedupe.py` — SHA-256 and dHash near-duplicate utilities.
- `build_manifest.py` — candidate-reservoir builder with seeded labels.
- `review_progress.py` — quota progress from candidate labels.
- `select_reviewed_set.py` — select final 160 items and deterministic dev/test split.
- `freeze_test.py` — enforce final-label meter and immutability.
- `make_review_worksheet.py` — include v2.1 stratum metadata.
- `finalize_labels.py` — merge a human-reviewed worksheet into the candidate pool.
- `prepare_prompts.py` — snapshot baseline prompt and build final prompt.
- `run_predictions.py` — run one prompt arm against one split.
- `score_v2.py` — raw and review-aware metrics.
- `compare_metrics.py` — baseline/final delta table.
- `generate_error_analysis.py` — deterministic error buckets and examples.
- `generate_report.py` — report and conditional interview notes.
- `tests/test_contract.py`
- `tests/test_dedupe.py`
- `tests/test_manifest.py`
- `tests/test_review_selection.py`
- `tests/test_freeze.py`
- `tests/test_predictions.py`
- `tests/test_metrics.py`
- `tests/test_compare_metrics.py`
- `tests/test_report.py`

Generated artifacts:

- `candidate_pool.json`
- `review_worksheet.csv`
- `review_decisions.v21.jsonl`
- `dataset_manifest.json`
- `prompt_manifest.json`
- `prompts/baseline.txt`
- `prompts/final.txt`
- `frozen_test_manifest.json`
- `predictions/baseline/`
- `predictions/final/`
- `metrics.baseline.json`
- `metrics.final.json`
- `metrics.comparison.json`
- `ERROR_ANALYSIS.md`
- `REPORT.md`
- `INTERVIEW_NOTES.md`

---

### Task 1: Add v2.1 contract constants

**Files:**
- Create: `ai-module/eval/vision/v2/contract.py`
- Test: `ai-module/eval/vision/v2/tests/test_contract.py`

**Interfaces:**
- Produces: `PROTOCOL_VERSION`, `TOTAL_ITEMS`, `POSITIVES`, `NEGATIVES`, `TEST_ITEMS`, `TEST_POSITIVES`, `TEST_NEGATIVES`, `PER_MAJOR`, `TEST_PER_MAJOR`, `PER_CONFUSER_GROUP`, `TEST_PER_CONFUSER_GROUP`, `MAJOR_CODES`, `ALLOWED_LABEL_SOURCES`.

- [ ] **Step 1: Write the failing contract test**

```python
from __future__ import annotations

import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import contract as c


def test_v21_contract_has_exact_interview_quotas():
    assert c.PROTOCOL_VERSION == "v2.1"
    assert c.TOTAL_ITEMS == 160
    assert c.POSITIVES == 80
    assert c.NEGATIVES == 80
    assert c.TEST_ITEMS == 80
    assert c.TEST_POSITIVES == 40
    assert c.TEST_NEGATIVES == 40
    assert c.PER_MAJOR == 10
    assert c.TEST_PER_MAJOR == 5
    assert c.PER_CONFUSER_GROUP == 10
    assert c.TEST_PER_CONFUSER_GROUP == 5
    assert len(c.MAJOR_CODES) == 8
    assert "ai_direct" not in c.ALLOWED_LABEL_SOURCES
```

- [ ] **Step 2: Run the test and verify it fails**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_contract.py -q
```

Expected: FAIL because `contract` does not exist.

- [ ] **Step 3: Add the constants**

```python
PROTOCOL_VERSION = "v2.1"
TOTAL_ITEMS = 160
POSITIVES = 80
NEGATIVES = 80
TEST_ITEMS = 80
TEST_POSITIVES = 40
TEST_NEGATIVES = 40
PER_MAJOR = 10
TEST_PER_MAJOR = 5
PER_CONFUSER_GROUP = 10
TEST_PER_CONFUSER_GROUP = 5
MAJOR_CODES = (
    "traffic",
    "municipal",
    "fire",
    "building",
    "utility",
    "construction",
    "elevator_special",
    "environment_other",
)
ALLOWED_LABEL_SOURCES = frozenset({
    "human_reviewed",
    "human_confirmed_ai_prelabel",
    "legacy_review",
})
```

- [ ] **Step 4: Run the test**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_contract.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```powershell
git add ai-module/eval/vision/v2/contract.py ai-module/eval/vision/v2/tests/test_contract.py
git commit -m "feat: add vision v2.1 evaluation contract"
```

---

### Task 2: Add dHash near-duplicate detection

**Files:**
- Create: `ai-module/eval/vision/v2/dedupe.py`
- Test: `ai-module/eval/vision/v2/tests/test_dedupe.py`

**Interfaces:**
- Produces: `sha256_file(path: Path) -> str`
- Produces: `dhash64(path: Path) -> int`
- Produces: `hamming64(left: int, right: int) -> int`
- Produces: `find_near_duplicate_pairs(items: list[dict], max_distance: int = 4) -> list[tuple[str, str, int]]`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import dedupe


def test_hamming_distance_counts_changed_bits():
    assert dedupe.hamming64(0b0000, 0b1010) == 2
    assert dedupe.hamming64(0b1111, 0b1111) == 0


def test_find_near_duplicate_pairs_uses_four_bit_threshold():
    items = [
        {"file": "a.jpg", "dhash64": 0b000000},
        {"file": "b.jpg", "dhash64": 0b000011},
        {"file": "c.jpg", "dhash64": 0b111111},
    ]
    pairs = dedupe.find_near_duplicate_pairs(items, max_distance=4)
    assert pairs == [("a.jpg", "b.jpg", 2)]
```

- [ ] **Step 2: Run the tests and verify they fail**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_dedupe.py -q
```

Expected: FAIL because `dedupe` does not exist.

- [ ] **Step 3: Implement the utilities**

```python
from __future__ import annotations

import hashlib
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageOps


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dhash64(path: Path) -> int:
    image = ImageOps.grayscale(Image.open(path)).resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(image.getdata())
    value = 0
    for row in range(8):
        for col in range(8):
            value = (value << 1) | int(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    return value


def hamming64(left: int, right: int) -> int:
    return int(left ^ right).bit_count()


def find_near_duplicate_pairs(items: list[dict], max_distance: int = 4) -> list[tuple[str, str, int]]:
    pairs = []
    for left, right in combinations(items, 2):
        distance = hamming64(int(left["dhash64"]), int(right["dhash64"]))
        if distance <= max_distance:
            pairs.append((left["file"], right["file"], distance))
    return pairs
```

- [ ] **Step 4: Run the tests**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_dedupe.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add ai-module/eval/vision/v2/dedupe.py ai-module/eval/vision/v2/tests/test_dedupe.py
git commit -m "feat: add image hashing for v2.1 dedupe"
```

---

### Task 3: Build the v2.1 candidate reservoir

**Files:**
- Modify: `ai-module/eval/vision/v2/build_manifest.py`
- Test: `ai-module/eval/vision/v2/tests/test_manifest.py`

**Interfaces:**
- Produces: `build_candidate_pool(vision_dir: Path, output_path: Path, seed_decisions_path: Path | None = None, seed: int = 20261106, positives_per_major: int = 30, negatives_per_group: int = 15) -> dict`
- Candidate items include `sha256`, `dhash64`, `candidate_kind`, `major_category`, `confuser_group`, `label_status`, `label_source`, and `prelabel_confidence`.

- [ ] **Step 1: Write failing reservoir tests**

```python
def test_candidate_pool_reserves_thirty_positives_per_major():
    items = make_balanced_candidates()
    pool = bm.select_candidate_reservoir(items, positives_per_major=30, negatives_per_group=15, seed=7)
    counts = Counter(item["major_category"] for item in pool if item["candidate_kind"] == "positive")
    assert counts == Counter({major: 30 for major in c.MAJOR_CODES})


def test_candidate_pool_reserves_fifteen_negatives_per_group():
    items = make_balanced_candidates()
    pool = bm.select_candidate_reservoir(items, positives_per_major=30, negatives_per_group=15, seed=7)
    counts = Counter(item["confuser_group"] for item in pool if item["candidate_kind"] == "negative")
    assert counts == Counter({major: 15 for major in c.MAJOR_CODES})
```

Add `make_balanced_candidates()` to the test file with 40 positive and 20 negative candidates per major, fields `file`, `source_path`, `source_category`, `mapped_category`, `major_category`, `confuser_group`, `candidate_kind`, `sha256`, `dhash64`.

- [ ] **Step 2: Run tests and verify failure**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_manifest.py -q
```

Expected: FAIL because `select_candidate_reservoir` does not exist.

- [ ] **Step 3: Implement reservoir selection**

```python
def select_candidate_reservoir(items, positives_per_major=30, negatives_per_group=15, seed=DEFAULT_SEED):
    positives = [dict(item) for item in items if item["candidate_kind"] == "positive"]
    negatives = [dict(item) for item in items if item["candidate_kind"] == "negative"]
    selected = []
    for offset, major in enumerate(sorted(contract.MAJOR_CODES)):
        group = [item for item in positives if item["major_category"] == major]
        selected.extend(_pick_balanced(group, positives_per_major, "source_category", seed + offset))
    for offset, group_name in enumerate(sorted(contract.MAJOR_CODES)):
        group = [item for item in negatives if item["confuser_group"] == group_name]
        selected.extend(_pick_balanced(group, negatives_per_group, "source_category", seed + 1000 + offset))
    return selected
```

In collection functions, attach `dhash64`, `prelabel_confidence`, and for negatives `confuser_group=taxonomy.major_by_sub[mapped]`.

Apply seed decisions by exact `source_path` first, then exact `sha256`; reject conflicting SHA and `ai_direct`. Preserve `label_source`.

- [ ] **Step 4: Add pool metadata and CLI**

`candidate_pool.json._meta` must include:

```json
{"version": "v2.1-candidate-pool", "protocol_version": "v2.1", "seed": 20261106, "positives_per_major": 30, "negatives_per_group": 15}
```

CLI flags: `--vision-dir`, `--output`, `--seed-decisions`, `--seed`, `--positives-per-major`, `--negatives-per-group`.

- [ ] **Step 5: Run tests**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_manifest.py -q
```

Expected: all manifest tests pass.

- [ ] **Step 6: Commit**

```powershell
git add ai-module/eval/vision/v2/build_manifest.py ai-module/eval/vision/v2/tests/test_manifest.py
git commit -m "feat: build v2.1 stratified candidate reservoir"
```

---

### Task 4: Add review progress and final 160-item selection

**Files:**
- Create: `ai-module/eval/vision/v2/review_progress.py`
- Create: `ai-module/eval/vision/v2/select_reviewed_set.py`
- Test: `ai-module/eval/vision/v2/tests/test_review_selection.py`

**Interfaces:**
- Produces: `summarize_progress(pool: dict) -> dict`
- Produces: `select_reviewed_set(pool: dict, seed: int = 20261106) -> dict`
- `select_reviewed_set` raises `ValueError` listing every quota deficit.

- [ ] **Step 1: Write failing tests**

```python
def test_progress_reports_deficits():
    pool = make_reviewed_fixture(positives_per_major=9, negatives_per_group=10)
    progress = rp.summarize_progress(pool)
    assert progress["positive_by_major"]["traffic"] == 9
    assert progress["missing_positive"]["traffic"] == 1
    assert progress["missing_negative"]["traffic"] == 0


def test_selection_requires_all_quotas():
    pool = make_reviewed_fixture(positives_per_major=9, negatives_per_group=10)
    with pytest.raises(ValueError, match="traffic: 1"):
        sr.select_reviewed_set(pool, seed=7)


def test_selection_outputs_exact_split_counts():
    pool = make_reviewed_fixture(positives_per_major=10, negatives_per_group=10)
    manifest = sr.select_reviewed_set(pool, seed=7)
    test = [item for item in manifest["items"] if item["split"] == "test"]
    assert len(manifest["items"]) == 160
    assert len(test) == 80
    assert sum(item["has_hazard"] is True for item in test) == 40
    assert sum(item["has_hazard"] is False for item in test) == 40
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_review_selection.py -q
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement progress calculation**

Count only `label_status=reviewed`. Produce `positive_by_major`, `negative_by_group`, `missing_positive`, and `missing_negative` for all 8 majors/groups.

- [ ] **Step 4: Implement final selection**

Only reviewed labels with allowed sources are eligible. Reject label/candidate-kind disagreement. Select exactly 10 positives per major and 10 negatives per confuser group, then split each stratum into 5 test and 5 dev with seed `20261106`.

- [ ] **Step 5: Add CLI output**

`select_reviewed_set.py` writes `dataset_manifest.json` with `_meta.version="v2.1"` and `_meta.protocol_version="v2.1"`. `review_progress.py` writes a JSON progress file and prints each deficit.

- [ ] **Step 6: Run tests and commit**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_review_selection.py -q
git add ai-module/eval/vision/v2/review_progress.py ai-module/eval/vision/v2/select_reviewed_set.py ai-module/eval/vision/v2/tests/test_review_selection.py
git commit -m "feat: select final v2.1 reviewed set"
```

---

### Task 5: Harden the freeze gate

**Files:**
- Modify: `ai-module/eval/vision/v2/freeze_test.py`
- Modify: `ai-module/eval/vision/v2/tests/test_freeze.py`

**Interfaces:**
- Produces: `freeze_test_manifest(manifest_path: Path, output_path: Path, protocol_version: str, prompt_manifest_path: Path, force: bool = False) -> dict`

- [ ] **Step 1: Replace old freeze fixtures with v2.1 fixtures**

The fixture must generate 8 major categories × 10 positives and 8 confuser groups × 10 negatives. Each stratum uses indices `0..4` for test and `5..9` for dev. Every item includes `sha256`, unique `dhash64`, final `has_hazard`, `label_source`, `reviewer`, and `review_time`.

- [ ] **Step 2: Write failing final-label tests**

```python
def test_freeze_uses_has_hazard_not_candidate_kind(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    make_final_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = next(item for item in manifest["items"] if item["split"] == "test" and item["candidate_kind"] == "positive")
    item["has_hazard"] = False
    item["major_category"] = ""
    item["subcategory"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="40 positive"):
        ft.freeze_test_manifest(manifest_path, tmp_path / "frozen.json", "v2.1", make_prompt_manifest(tmp_path))


def test_freeze_rejects_ai_direct_label(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    make_final_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    next(item for item in manifest["items"] if item["split"] == "test")["label_source"] = "ai_direct"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="label source"):
        ft.freeze_test_manifest(manifest_path, tmp_path / "frozen.json", "v2.1", make_prompt_manifest(tmp_path))
```

`make_prompt_manifest()` writes:

```python
{"baseline": {"id": "baseline", "sha256": "a" * 64}, "final": {"id": "final", "sha256": "b" * 64}}
```

- [ ] **Step 3: Run tests and verify failure**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_freeze.py -q
```

Expected: FAIL because the old freezer requires 200 items and counts `candidate_kind`.

- [ ] **Step 4: Implement final-label validation**

```python
if len(items) != contract.TOTAL_ITEMS:
    raise ValueError(f"expected 160 items, got {len(items)}")
test = [item for item in items if item["split"] == "test"]
dev = [item for item in items if item["split"] == "dev"]
test_pos = [item for item in test if item.get("has_hazard") is True]
test_neg = [item for item in test if item.get("has_hazard") is False]
if len(test) != contract.TEST_ITEMS:
    raise ValueError(f"expected 80 test items, got {len(test)}")
if len(test_pos) != contract.TEST_POSITIVES or len(test_neg) != contract.TEST_NEGATIVES:
    raise ValueError(f"expected 40 positive / 40 negative test items, got {len(test_pos)} / {len(test_neg)}")
for major in contract.MAJOR_CODES:
    count = sum(item.get("has_hazard") is True and item.get("major_category") == major for item in test)
    if count != contract.TEST_PER_MAJOR:
        raise ValueError(f"test major {major} expected 5 positives, got {count}")
```

Also validate allowed label sources, taxonomy membership, file existence, exact SHA uniqueness, dHash distance, and prompt manifest hashes.

- [ ] **Step 5: Write frozen hashes and metadata**

For each test item write `file_sha256`, `label_sha256`, `prompt_baseline_sha256`, and `prompt_final_sha256`. Frozen metadata includes protocol version, seed, frozen time, test counts, major counts, and the full prompt manifest.

- [ ] **Step 6: Run tests and commit**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_freeze.py -q
git add ai-module/eval/vision/v2/freeze_test.py ai-module/eval/vision/v2/tests/test_freeze.py
git commit -m "fix: enforce final-label v2.1 freeze gate"
```

---

### Task 6: Add prompt snapshots and prediction runner

**Files:**
- Create: `ai-module/eval/vision/v2/prepare_prompts.py`
- Create: `ai-module/eval/vision/v2/run_predictions.py`
- Test: `ai-module/eval/vision/v2/tests/test_predictions.py`

**Interfaces:**
- Produces: `prepare_prompts(output_dir: Path) -> dict`
- Produces: `run_arm(frozen_path: Path, prompt_path: Path, output_dir: Path, client, temperature: float = 0.0) -> dict`
- Prediction JSON includes `sha256`, `arm`, `prompt_sha256`, `model`, `temperature`, `raw_response`, `parsed`, `error`.

- [ ] **Step 1: Write failing prediction tests**

```python
class FakeClient:
    model = "fake-vision"

    def analyze(self, image_path, prompt, temperature):
        return '{"has_hazard": false, "confidence": "高", "reason_if_no_hazard": "正常"}'

    @staticmethod
    def _extract_json(text):
        return json.loads(text)


def test_run_arm_writes_one_prediction_per_sha(tmp_path):
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps({"items": [{"sha256": "abc", "source_path": str(tmp_path / "x.jpg")}]}), encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("prompt", encoding="utf-8")
    result = rp.run_arm(frozen, prompt, tmp_path / "out", FakeClient())
    assert result == {"total": 1, "written": 1, "failed": 0}
    payload = json.loads((tmp_path / "out" / "abc.json").read_text(encoding="utf-8"))
    assert payload["parsed"]["has_hazard"] is False
    assert payload["temperature"] == 0.0


def test_prepare_prompts_hashes_and_appends_rules(tmp_path):
    manifest = pp.prepare_prompts(tmp_path)
    baseline = (tmp_path / "baseline.txt").read_text(encoding="utf-8")
    final = (tmp_path / "final.txt").read_text(encoding="utf-8")
    assert manifest["baseline"]["sha256"] == hashlib.sha256(baseline.encode("utf-8")).hexdigest()
    assert "无法判断时输出 has_hazard=false" in final
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_predictions.py -q
```

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement prompt snapshots**

Copy `VISION_PROMPT` from `ai-module/prompts.py` into `prompts/baseline.txt`. Append this exact block to create `prompts/final.txt`:

```text
【v2.1 精度优先补充规则】
- 只有在画面清楚显示目标隐患时才输出 has_hazard=true。
- 不得仅凭新闻标题、字幕、文字说明、常识或上下文推测隐患。
- 场景正常或有可见证据表明符合要求时，输出 has_hazard=false。
- 因遮挡、模糊、信息不足而无法判断时，输出 has_hazard=false、confidence=低、subcategory 为空，并说明需要人工复核。
- confidence=低 仅表示需要人工复核，不代表无隐患。
```

Write `prompt_manifest.json` with the ID and SHA-256 of both prompts.

- [ ] **Step 4: Implement the prediction runner**

For every item in the selected split:

```python
raw = client.analyze(item["source_path"], prompt, temperature=temperature)
parsed = client._extract_json(raw) if raw else None
payload = {
    "sha256": item["sha256"],
    "arm": output_dir.name,
    "prompt_sha256": prompt_sha,
    "model": getattr(client, "model", ""),
    "temperature": temperature,
    "raw_response": raw,
    "parsed": parsed,
    "error": "" if parsed else "parse_failed",
}
```

Write one file keyed by SHA. Exit nonzero if any item fails to produce a parsed JSON object.

- [ ] **Step 5: Run tests and commit**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_predictions.py -q
git add ai-module/eval/vision/v2/prepare_prompts.py ai-module/eval/vision/v2/run_predictions.py ai-module/eval/vision/v2/tests/test_predictions.py
git commit -m "feat: add frozen prompt prediction runner"
```

---

### Task 7: Upgrade metrics and add baseline/final comparison

**Files:**
- Modify: `ai-module/eval/vision/v2/score_v2.py`
- Create: `ai-module/eval/vision/v2/compare_metrics.py`
- Modify: `ai-module/eval/vision/v2/tests/test_metrics.py`
- Create: `ai-module/eval/vision/v2/tests/test_compare_metrics.py`

**Interfaces:**
- Produces: `evaluate_items(items: list[dict], predictions: list[dict], taxonomy_path: Path) -> dict`
- Produces: `compare_metrics(baseline: dict, final: dict) -> dict`

- [ ] **Step 1: Write failing metric tests**

```python
def test_review_aware_routes_low_confidence_to_review(taxonomy_path):
    items = [
        {"has_hazard": True, "major_category": "traffic", "subcategory": "road_occupancy"},
        {"has_hazard": True, "major_category": "traffic", "subcategory": "road_occupancy"},
        {"has_hazard": False, "major_category": "", "subcategory": ""},
        {"has_hazard": False, "major_category": "", "subcategory": ""},
    ]
    preds = [
        {"has_hazard": True, "confidence": "高", "major_category": "traffic", "subcategory": "road_occupancy"},
        {"has_hazard": False, "confidence": "低", "major_category": "", "subcategory": ""},
        {"has_hazard": True, "confidence": "高", "major_category": "traffic", "subcategory": "road_occupancy"},
        {"has_hazard": False, "confidence": "高", "major_category": "", "subcategory": ""},
    ]
    metrics = sv.evaluate_items(items, preds, taxonomy_path)
    assert metrics["binary"] == {"tp": 1, "tn": 1, "fp": 1, "fn": 1}
    assert metrics["review_aware"]["review_rate"] == 0.25
    assert metrics["review_aware"]["auto_recall"] == 0.5
    assert metrics["review_aware"]["auto_fpr"] == 0.5


def test_invalid_prediction_is_counted_not_dropped(taxonomy_path):
    metrics = sv.evaluate_items(
        [{"has_hazard": True, "major_category": "traffic", "subcategory": "road_occupancy"}],
        [{"error": "parse_failed"}],
        taxonomy_path,
    )
    assert metrics["invalid"]["parse_failed"] == 1
    assert metrics["binary"]["fn"] == 1
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_metrics.py -q
```

Expected: FAIL because review-aware metrics are missing.

- [ ] **Step 3: Implement review-aware metrics**

- Missing/non-dict prediction = parse failure; raw binary treats it as negative.
- Missing/invalid `confidence` = review required.
- `confidence` not in `{高, 中}` = review required.
- `auto_recall = TP_auto / total positives`.
- `critical_miss_rate = FN_auto / total positives`.
- `auto_fpr = FP_auto / total negatives`.
- `review_rate = review_required / total items`.
- `auto_coverage = 1 - review_rate`.

- [ ] **Step 4: Add major-category metrics**

For positives with valid predictions, compute `major_correct`, per-major recall, 8-major macro recall, and a confusion map keyed by `gold_major -> pred_major`, `FN`, or `invalid`. Do not report subcategory accuracy.

- [ ] **Step 5: Write comparison test**

```python
def test_compare_metrics_reports_signed_deltas():
    baseline = {"binary": {"recall": 0.8, "fpr": 0.4, "precision": 0.6, "f1": 0.68},
                "major": {"macro_recall": 0.7},
                "review_aware": {"review_rate": 0.0, "auto_recall": 0.8, "auto_fpr": 0.4}}
    final = {"binary": {"recall": 0.75, "fpr": 0.2, "precision": 0.75, "f1": 0.75},
             "major": {"macro_recall": 0.72},
             "review_aware": {"review_rate": 0.1, "auto_recall": 0.7, "auto_fpr": 0.15}}
    result = cm.compare_metrics(baseline, final)
    assert result["delta"]["fpr"] == pytest.approx(-0.2)
    assert result["delta"]["precision"] == pytest.approx(0.15)
    assert result["delta"]["review_rate"] == pytest.approx(0.1)
```

- [ ] **Step 6: Run tests and commit**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_metrics.py ai-module/eval/vision/v2/tests/test_compare_metrics.py -q
git add ai-module/eval/vision/v2/score_v2.py ai-module/eval/vision/v2/compare_metrics.py ai-module/eval/vision/v2/tests/test_metrics.py ai-module/eval/vision/v2/tests/test_compare_metrics.py
git commit -m "feat: add review-aware vision metrics"
```

---

### Task 8: Generate the actual candidate pool and review worksheet

**Files:**
- Generated: `candidate_pool.json`
- Generated: `review_worksheet.csv`
- Generated: `review_progress.json`

- [ ] **Step 1: Build the candidate pool**

```powershell
py ai-module/eval/vision/v2/build_manifest.py `
  --vision-dir ai-module/eval/vision `
  --output ai-module/eval/vision/v2/candidate_pool.json `
  --seed-decisions ai-module/eval/vision/v2/review_decisions.jsonl `
  --positives-per-major 30 `
  --negatives-per-group 15
```

Expected: all 8 positive major groups and all 8 negative confuser groups are present.

- [ ] **Step 2: Generate the human-review worksheet**

```powershell
py ai-module/eval/vision/v2/make_review_worksheet.py `
  --manifest ai-module/eval/vision/v2/candidate_pool.json `
  --output ai-module/eval/vision/v2/review_worksheet.csv
```

Expected: one row per candidate; seeded reviewed rows keep their labels; other rows are `pending_review`.

- [ ] **Step 3: Show review progress**

```powershell
py ai-module/eval/vision/v2/review_progress.py `
  --pool ai-module/eval/vision/v2/candidate_pool.json `
  --output ai-module/eval/vision/v2/review_progress.json
```

Expected: positive count per major, negative count per confuser group, and remaining deficits.

- [ ] **Step 4: Commit generated materials**

```powershell
git add ai-module/eval/vision/v2/candidate_pool.json ai-module/eval/vision/v2/review_worksheet.csv ai-module/eval/vision/v2/review_progress.json
git commit -m "data: add vision v2.1 candidate reservoir"
```

---

### Task 9: Perform human review and select the final 160 items

**Files:**
- Modify: `candidate_pool.json`
- Modify: `review_worksheet.csv`
- Generated: `review_decisions.v21.jsonl`
- Generated: `dataset_manifest.json`

- [ ] **Step 1: Review in batches until every quota is full**

For each pending row:

1. Set `label_status` to `reviewed` or `excluded`.
2. For a positive, set `has_hazard=true`, `major_category`, `subcategory`, `difficulty`, `text_in_image`, and `notes`.
3. For a negative, set `has_hazard=false`, empty categories, `difficulty`, `text_in_image`, and a visible normal-scene reason in `notes`.
4. For an exclusion, leave `has_hazard` blank and fill `exclude_reason`.

Run after each batch:

```powershell
py ai-module/eval/vision/v2/review_progress.py `
  --pool ai-module/eval/vision/v2/candidate_pool.json `
  --output ai-module/eval/vision/v2/review_progress.json
```

Acceptance checkpoint: every `missing_positive` and `missing_negative` value is `0`. Do not lower quotas and do not borrow from another major.

- [ ] **Step 2: Validate and merge the human worksheet**

```powershell
py ai-module/eval/vision/v2/finalize_labels.py `
  --worksheet ai-module/eval/vision/v2/review_worksheet.csv `
  --manifest ai-module/eval/vision/v2/candidate_pool.json `
  --taxonomy ai-module/eval/vision/_taxonomy_final.json `
  --decisions-output ai-module/eval/vision/v2/review_decisions.v21.jsonl
```

Expected: every reviewed/excluded row is counted; invalid taxonomy, missing reviewer, missing time, and `ai_direct` final labels are rejected.

- [ ] **Step 3: Select exactly 160 final items**

```powershell
py ai-module/eval/vision/v2/select_reviewed_set.py `
  --pool ai-module/eval/vision/v2/candidate_pool.json `
  --output ai-module/eval/vision/v2/dataset_manifest.json `
  --seed 20261106
```

Expected:

```text
total=160
positive=80
negative=80
dev=80
test=80
test_positive=40
test_negative=40
each major total=10, test=5
each confuser group total=10, test=5
```

- [ ] **Step 4: Verify hashes and dedupe**

```powershell
py ai-module/eval/vision/v2/select_reviewed_set.py `
  --pool ai-module/eval/vision/v2/candidate_pool.json `
  --output ai-module/eval/vision/v2/dataset_manifest.json `
  --seed 20261106 `
  --verify-only
```

Expected: no SHA-256 duplicates, no dHash pair with distance `<= 4`, and no overlap with v1 `test_set/` or `images_merged/`.

- [ ] **Step 5: Commit final reviewed data**

```powershell
git add ai-module/eval/vision/v2/candidate_pool.json ai-module/eval/vision/v2/review_worksheet.csv ai-module/eval/vision/v2/review_decisions.v21.jsonl ai-module/eval/vision/v2/dataset_manifest.json
git commit -m "data: finalize vision v2.1 reviewed dataset"
```

---

### Task 10: Tune final prompt on dev, freeze test, and run both arms

**Files:**
- Generated: `prompts/baseline.txt`
- Generated: `prompts/final.txt`
- Generated: `prompt_manifest.json`
- Generated: `predictions/`
- Generated: `frozen_test_manifest.json`
- Generated: `metrics.dev-baseline.json`
- Generated: `metrics.dev-final.json`
- Generated: `metrics.baseline.json`
- Generated: `metrics.final.json`
- Generated: `metrics.comparison.json`

- [ ] **Step 1: Prepare prompt snapshots**

```powershell
py ai-module/eval/vision/v2/prepare_prompts.py `
  --output-dir ai-module/eval/vision/v2/prompts `
  --manifest ai-module/eval/vision/v2/prompt_manifest.json
```

Expected: both prompt files exist and their SHA-256 values are recorded.

- [ ] **Step 2: Run both prompt arms on dev**

```powershell
py ai-module/eval/vision/v2/run_predictions.py `
  --manifest ai-module/eval/vision/v2/dataset_manifest.json `
  --split dev `
  --prompt ai-module/eval/vision/v2/prompts/baseline.txt `
  --output ai-module/eval/vision/v2/predictions/dev-baseline `
  --temperature 0
```

```powershell
py ai-module/eval/vision/v2/run_predictions.py `
  --manifest ai-module/eval/vision/v2/dataset_manifest.json `
  --split dev `
  --prompt ai-module/eval/vision/v2/prompts/final.txt `
  --output ai-module/eval/vision/v2/predictions/dev-final `
  --temperature 0
```

Expected: 80 predictions per arm with no parse failures.

- [ ] **Step 3: Score dev and select the final prompt**

```powershell
py ai-module/eval/vision/v2/score_v2.py `
  --manifest ai-module/eval/vision/v2/dataset_manifest.json `
  --split dev `
  --predictions ai-module/eval/vision/v2/predictions/dev-baseline `
  --taxonomy ai-module/eval/vision/_taxonomy_final.json `
  --output ai-module/eval/vision/v2/metrics.dev-baseline.json
```

```powershell
py ai-module/eval/vision/v2/score_v2.py `
  --manifest ai-module/eval/vision/v2/dataset_manifest.json `
  --split dev `
  --predictions ai-module/eval/vision/v2/predictions/dev-final `
  --taxonomy ai-module/eval/vision/_taxonomy_final.json `
  --output ai-module/eval/vision/v2/metrics.dev-final.json
```

Decision rule: keep the final prompt only if it lowers dev `auto_fpr` without increasing `critical_miss_rate`, or improves balanced accuracy while keeping `critical_miss_rate <= baseline`. Otherwise state that no prompt improvement was found.

- [ ] **Step 4: Freeze test**

```powershell
py ai-module/eval/vision/v2/freeze_test.py `
  --manifest ai-module/eval/vision/v2/dataset_manifest.json `
  --output ai-module/eval/vision/v2/frozen_test_manifest.json `
  --protocol-version v2.1 `
  --prompt-manifest ai-module/eval/vision/v2/prompt_manifest.json
```

Expected: 80 test items, 40 positives, 40 negatives, 5 positives in every major, all labels human-reviewed, all hashes recorded.

- [ ] **Step 5: Run baseline and final once on frozen test**

```powershell
py ai-module/eval/vision/v2/run_predictions.py `
  --manifest ai-module/eval/vision/v2/frozen_test_manifest.json `
  --split test `
  --prompt ai-module/eval/vision/v2/prompts/baseline.txt `
  --output ai-module/eval/vision/v2/predictions/baseline `
  --temperature 0
```

```powershell
py ai-module/eval/vision/v2/run_predictions.py `
  --manifest ai-module/eval/vision/v2/frozen_test_manifest.json `
  --split test `
  --prompt ai-module/eval/vision/v2/prompts/final.txt `
  --output ai-module/eval/vision/v2/predictions/final `
  --temperature 0
```

Expected: 80 predictions per arm. Do not rerun to cherry-pick a result.

- [ ] **Step 6: Score frozen test and compare**

```powershell
py ai-module/eval/vision/v2/score_v2.py `
  --manifest ai-module/eval/vision/v2/frozen_test_manifest.json `
  --split test `
  --predictions ai-module/eval/vision/v2/predictions/baseline `
  --taxonomy ai-module/eval/vision/_taxonomy_final.json `
  --output ai-module/eval/vision/v2/metrics.baseline.json
```

```powershell
py ai-module/eval/vision/v2/score_v2.py `
  --manifest ai-module/eval/vision/v2/frozen_test_manifest.json `
  --split test `
  --predictions ai-module/eval/vision/v2/predictions/final `
  --taxonomy ai-module/eval/vision/_taxonomy_final.json `
  --output ai-module/eval/vision/v2/metrics.final.json
```

```powershell
py ai-module/eval/vision/v2/compare_metrics.py `
  --baseline ai-module/eval/vision/v2/metrics.baseline.json `
  --final ai-module/eval/vision/v2/metrics.final.json `
  --output ai-module/eval/vision/v2/metrics.comparison.json
```

Expected: signed deltas for recall, FPR, precision, F1, macro recall, review rate, auto recall, and auto FPR.

- [ ] **Step 7: Commit evaluation artifacts**

```powershell
git add ai-module/eval/vision/v2/prompts ai-module/eval/vision/v2/prompt_manifest.json ai-module/eval/vision/v2/frozen_test_manifest.json ai-module/eval/vision/v2/predictions ai-module/eval/vision/v2/metrics.dev-baseline.json ai-module/eval/vision/v2/metrics.dev-final.json ai-module/eval/vision/v2/metrics.baseline.json ai-module/eval/vision/v2/metrics.final.json ai-module/eval/vision/v2/metrics.comparison.json
git commit -m "eval: run frozen vision v2.1 comparison"
```

---

### Task 11: Generate error analysis, report, and interview notes

**Files:**
- Create: `ai-module/eval/vision/v2/generate_error_analysis.py`
- Create: `ai-module/eval/vision/v2/generate_report.py`
- Test: `ai-module/eval/vision/v2/tests/test_report.py`
- Generated: `ERROR_ANALYSIS.md`
- Generated: `REPORT.md`
- Generated: `INTERVIEW_NOTES.md`

- [ ] **Step 1: Write failing report tests**

```python
def test_error_classifier_buckets_false_positive_and_major_confusion():
    frozen = {"items": [
        {"sha256": "a", "has_hazard": False, "major_category": "", "subcategory": ""},
        {"sha256": "b", "has_hazard": True, "major_category": "traffic", "subcategory": "road_occupancy"},
    ]}
    predictions = [
        {"sha256": "a", "parsed": {"has_hazard": True, "confidence": "高", "major_category": "municipal", "subcategory": "manhole_damage"}},
        {"sha256": "b", "parsed": {"has_hazard": True, "confidence": "高", "major_category": "municipal", "subcategory": "manhole_damage"}},
    ]
    errors = ge.classify_errors(frozen, predictions)
    assert errors["false_positive"]["count"] == 1
    assert errors["major_confusion"]["count"] == 1


def test_interview_notes_do_not_claim_improvement_when_final_is_worse():
    baseline = {"binary": {"recall": 0.8, "fpr": 0.2, "precision": 0.8, "f1": 0.8},
                "major": {"macro_recall": 0.8},
                "review_aware": {"review_rate": 0.0, "auto_recall": 0.8, "auto_fpr": 0.2}}
    final = {"binary": {"recall": 0.7, "fpr": 0.3, "precision": 0.7, "f1": 0.7},
             "major": {"macro_recall": 0.7},
             "review_aware": {"review_rate": 0.1, "auto_recall": 0.65, "auto_fpr": 0.25}}
    notes = ge.generate_interview_notes(baseline, final, {"winner": "baseline"})
    assert "未优于" in notes
    assert "优化有效" not in notes
```

- [ ] **Step 2: Run tests and verify failure**

```powershell
py -m pytest ai-module/eval/vision/v2/tests/test_report.py -q
```

Expected: FAIL because the report modules do not exist.

- [ ] **Step 3: Implement deterministic error buckets**

Return:

```python
{
    "false_positive": {"count": 0, "examples": []},
    "false_negative": {"count": 0, "examples": []},
    "major_confusion": {"count": 0, "examples": []},
    "invalid_output": {"count": 0, "examples": []},
    "review_required": {"count": 0, "examples": []},
}
```

Each example includes `sha256`, `file`, `gold_major`, `pred_major`, `pred_subcategory`, and `confidence`.

- [ ] **Step 4: Generate error analysis**

```powershell
py ai-module/eval/vision/v2/generate_error_analysis.py `
  --frozen ai-module/eval/vision/v2/frozen_test_manifest.json `
  --baseline ai-module/eval/vision/v2/predictions/baseline `
  --final ai-module/eval/vision/v2/predictions/final `
  --output ai-module/eval/vision/v2/ERROR_ANALYSIS.md
```

The document must contain each bucket and count for both arms, up to 3 example files per bucket, and a table linking each bucket to prompt, model, label, or product rule. Inspect the top examples with `view_image` and add one sentence per top bucket explaining the visible cause.

- [ ] **Step 5: Generate report and interview notes**

```powershell
py ai-module/eval/vision/v2/generate_report.py `
  --baseline-metrics ai-module/eval/vision/v2/metrics.baseline.json `
  --final-metrics ai-module/eval/vision/v2/metrics.final.json `
  --comparison ai-module/eval/vision/v2/metrics.comparison.json `
  --error-analysis ai-module/eval/vision/v2/ERROR_ANALYSIS.md `
  --report ai-module/eval/vision/v2/REPORT.md `
  --interview-notes ai-module/eval/vision/v2/INTERVIEW_NOTES.md
```

`REPORT.md` must include counts, human-review status, freeze hashes, binary metrics, review-aware metrics, major confusion, error analysis, and limitations. `INTERVIEW_NOTES.md` must include the 90-second story, baseline/final numbers, three follow-up answers, and forbidden claims. If `comparison["winner"] != "final"`, state that the final prompt did not beat baseline.

- [ ] **Step 6: Run consistency check and commit**

```powershell
Select-String -Path ai-module/eval/vision/v2/INTERVIEW_NOTES.md -Pattern '生产准确率|真实业务分布|人工专家|25 类全部|线上误报率|自动建单'
git add ai-module/eval/vision/v2/generate_error_analysis.py ai-module/eval/vision/v2/generate_report.py ai-module/eval/vision/v2/tests/test_report.py ai-module/eval/vision/v2/ERROR_ANALYSIS.md ai-module/eval/vision/v2/REPORT.md ai-module/eval/vision/v2/INTERVIEW_NOTES.md
git commit -m "docs: add evidence-backed vision v2.1 report"
```

Expected: forbidden terms appear only in the explicit forbidden-claim section.

---

### Task 12: Update documentation and run full regression

**Files:**
- Modify: `ai-module/eval/vision/v2/PROTOCOL.md`
- Modify: `docs/current/interview-progress.md`
- Modify: `docs/superpowers/plans/2026-11-06-vision-eval-v2.md`
- Modify: current docs index if present.

- [ ] **Step 1: Update protocol**

Set protocol version `v2.1`, 160 items, 80/80, dev/test 80 each, test 40/40, 8 majors ×10 with test 5 each, 8 confuser groups ×10 with test 5 each, human-reviewed labels only, raw plus review-aware metrics, and diagnostic-only claims.

- [ ] **Step 2: Point old plan to the new plan**

Add:

```markdown
> Superseded by `docs/superpowers/plans/2026-11-06-vision-eval-v2-1-interview-grade.md`.
> Current target is 80 positive / 80 negative, test 40 / 40.
```

- [ ] **Step 3: Update interview progress**

Add:

```markdown
### 视觉评估集 v2.1

- 状态：见 `ai-module/eval/vision/v2/REPORT.md`
- 当前结论：只引用冻结 test 的 recall、FPR、macro recall 和 error analysis
- 明确限制：公开场景、小样本、单人复核，不代表生产分布
```

Do not add a metric absent from `metrics.baseline.json`, `metrics.final.json`, or `metrics.comparison.json`.

- [ ] **Step 4: Run full tests and consistency checks**

```powershell
py -m pytest ai-module/eval/vision/v2/tests -q
Select-String -Path ai-module/eval/vision/v2/REPORT.md,ai-module/eval/vision/v2/INTERVIEW_NOTES.md -Pattern '生产准确率|真实业务分布|人工专家|25 类全部|线上误报率'
```

Expected: all tests pass and forbidden terms appear only in the explicit forbidden-claim section.

- [ ] **Step 5: Commit documentation**

```powershell
git add ai-module/eval/vision/v2/PROTOCOL.md docs/current/interview-progress.md docs/superpowers/plans/2026-11-06-vision-eval-v2.md
git commit -m "docs: publish vision v2.1 evidence chain"
```

---

## Final Acceptance Gate

Do not describe the evaluation as interview-ready until all are true:

- [ ] `dataset_manifest.json` has 160 reviewed items.
- [ ] `test` has 40 positives and 40 negatives.
- [ ] Each major has 5 test positives.
- [ ] Each confuser group has 5 test negatives.
- [ ] All frozen test labels pass the allowed-source check.
- [ ] `frozen_test_manifest.json` contains file and label hashes.
- [ ] Baseline and final metrics use the same frozen test.
- [ ] Low-confidence review routing is reported.
- [ ] `ERROR_ANALYSIS.md` has at least three evidence-backed buckets.
- [ ] `INTERVIEW_NOTES.md` contains no production-distribution claim.
- [ ] Full test suite passes.

## Self-Review

- Spec coverage: dataset quotas, human review, dedupe, freeze, prompt comparison, review-aware metrics, error analysis, report, and interview boundaries each have a task.
- Placeholder scan: passed; no unresolved markers or unspecified implementation steps.
- Type consistency: `has_hazard`, `major_category`, `subcategory`, `confuser_group`, `dhash64`, `label_source`, `review_rate`, `critical_miss_rate`, and `auto_fpr` use one spelling throughout.
- Scope check: this plan produces a diagnostic benchmark and report, not a production-distribution study or a model-training project.

---

## Appendix A: Complete Test Fixture Helpers

Use these helpers in the corresponding test files so no task references an undefined fixture.

### A.1 Candidate reservoir fixture for `test_manifest.py`

```python
from collections import Counter

import contract as c


def make_balanced_candidates():
    items = []
    for major in c.MAJOR_CODES:
        for index in range(40):
            items.append({
                "file": f"{major}-pos-{index}.jpg",
                "source_path": f"C:/images/{major}-pos-{index}.jpg",
                "source_category": f"{major}_source",
                "mapped_category": "manhole_damage" if major == "municipal" else major,
                "major_category": major,
                "confuser_group": major,
                "candidate_kind": "positive",
                "sha256": f"{major}-pos-{index}",
                "dhash64": index,
            })
        for index in range(20):
            items.append({
                "file": f"{major}-neg-{index}.jpg",
                "source_path": f"C:/images/{major}-neg-{index}.jpg",
                "source_category": f"{major}_negative",
                "mapped_category": "manhole_damage" if major == "municipal" else major,
                "major_category": "",
                "confuser_group": major,
                "candidate_kind": "negative",
                "sha256": f"{major}-neg-{index}",
                "dhash64": 1000 + index,
            })
    return items
```

### A.2 Reviewed selection fixture for `test_review_selection.py`

```python
import contract as c

SUB_BY_MAJOR = {
    "traffic": "road_occupancy",
    "municipal": "manhole_damage",
    "fire": "fire_lane_blocked",
    "building": "structural_damage",
    "utility": "wire_fault",
    "construction": "deep_pit",
    "elevator_special": "elevator_stopped",
    "environment_other": "garbage_pile",
}


def make_reviewed_fixture(positives_per_major: int, negatives_per_group: int):
    items = []
    for major in c.MAJOR_CODES:
        for index in range(positives_per_major):
            items.append({
                "file": f"{major}-pos-{index}.jpg",
                "source_path": f"C:/images/{major}-pos-{index}.jpg",
                "source_category": f"{major}_source",
                "mapped_category": SUB_BY_MAJOR[major],
                "major_category": major,
                "confuser_group": major,
                "candidate_kind": "positive",
                "sha256": f"{major}-pos-{index}",
                "dhash64": index,
                "label_status": "reviewed",
                "has_hazard": True,
                "subcategory": SUB_BY_MAJOR[major],
                "difficulty": "easy",
                "text_in_image": False,
                "notes": "visible hazard",
                "reviewer": "tester",
                "review_time": "2026-11-06T10:00:00+08:00",
                "label_source": "human_reviewed",
            })
        for index in range(negatives_per_group):
            items.append({
                "file": f"{major}-neg-{index}.jpg",
                "source_path": f"C:/images/{major}-neg-{index}.jpg",
                "source_category": f"{major}_negative",
                "mapped_category": SUB_BY_MAJOR[major],
                "confuser_group": major,
                "candidate_kind": "negative",
                "sha256": f"{major}-neg-{index}",
                "dhash64": 1000 + index,
                "label_status": "reviewed",
                "has_hazard": False,
                "major_category": "",
                "subcategory": "",
                "difficulty": "easy",
                "text_in_image": False,
                "notes": "visible normal scene",
                "reviewer": "tester",
                "review_time": "2026-11-06T10:00:00+08:00",
                "label_source": "human_reviewed",
            })
    return {"_meta": {"version": "v2.1-candidate-pool"}, "items": items}
```

### A.3 Freeze fixture for `test_freeze.py`

```python
import contract as c

SUB_BY_MAJOR = {
    "traffic": "road_occupancy",
    "municipal": "manhole_damage",
    "fire": "fire_lane_blocked",
    "building": "structural_damage",
    "utility": "wire_fault",
    "construction": "deep_pit",
    "elevator_special": "elevator_stopped",
    "environment_other": "garbage_pile",
}


def make_final_manifest(path):
    items = []
    for major_index, major in enumerate(c.MAJOR_CODES):
        for kind, count in (("positive", 10), ("negative", 10)):
            for index in range(count):
                is_positive = kind == "positive"
                items.append({
                    "file": f"{major}-{kind}-{index}.jpg",
                    "source_path": str(path.parent / f"{major}-{kind}-{index}.jpg"),
                    "source_category": f"{major}-source",
                    "mapped_category": SUB_BY_MAJOR[major],
                    "major_category": major if is_positive else "",
                    "confuser_group": major,
                    "candidate_kind": kind,
                    "sha256": f"{major}-{kind}-{index}",
                    "dhash64": major_index * 1000 + index + (0 if is_positive else 100),
                    "split": "test" if index < 5 else "dev",
                    "label_status": "reviewed",
                    "has_hazard": is_positive,
                    "subcategory": SUB_BY_MAJOR[major] if is_positive else "",
                    "difficulty": "easy",
                    "text_in_image": False,
                    "notes": "fixture",
                    "reviewer": "tester",
                    "review_time": "2026-11-06T10:00:00+08:00",
                    "label_source": "human_reviewed",
                })
    for item in items:
        (path.parent / f"{item['file']}").write_bytes(b"x")
    path.write_text(json.dumps({"_meta": {"version": "v2.1"}, "items": items}), encoding="utf-8")


def make_prompt_manifest(tmp_path):
    path = tmp_path / "prompt_manifest.json"
    path.write_text(json.dumps({
        "baseline": {"id": "baseline", "sha256": "a" * 64},
        "final": {"id": "final", "sha256": "b" * 64},
    }), encoding="utf-8")
    return path
```
### A.4 Test imports

Each test file added by this plan must include:

```python
import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))
```

Import the module under test after that path setup, for example:

```python
import contract as c
import build_manifest as bm
import review_progress as rp
import select_reviewed_set as sr
import freeze_test as ft
import prepare_prompts as pp
import run_predictions as pred
import score_v2 as sv
import compare_metrics as cm
import generate_error_analysis as ge
```




