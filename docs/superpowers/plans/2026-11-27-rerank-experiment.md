# Rerank Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated, feature-flagged rerank experiment that compares the existing hybrid retrieval against a larger candidate pool with optional reranking, without changing the production retrieval default.

**Architecture:** Add a reranker interface with Noop and HTTP adapters, expose a structured candidate-retrieval method on `HybridSearcher`, and add a standalone evaluation script that reuses the existing query set and metrics. The production path remains unchanged unless the experiment passes the pre-registered gate and is merged in a later plan.

**Tech Stack:** Python 3.13, existing `HybridSearcher`, `pytest`, `requests`, existing MySQL/Milvus retrieval, cloud-host local execution through SSH for read-only evaluation.

## Global Constraints

- Work in `E:\java\newProject-rag-rerank` on branch `codex/rag-rerank-experiment`; do not use the current dirty worktree for experimental edits.
- `RERANK_ENABLED=false` by default.
- `RERANK_CANDIDATE_K=10`, `RERANK_FINAL_K=5`, `RERANK_TIMEOUT_SECONDS=1.0`.
- Do not modify chunking, Embedding, Milvus schema, MySQL schema, frontend, Java code, or the default `hybrid_search` output.
- Do not claim StubReranker results as model performance.
- Evaluation is read-only; no MySQL/Milvus writes.
- Acceptance gate: Hit@5 remains 1.000; MRR improves by at least 0.025 absolute; at least 5 of 14 non-Top-1 queries reach rank 1; rerank added P95 latency ≤ 300 ms; negative EmptyRate remains 1.00.
- If the gate fails, do not merge into the main project; preserve the code and report as Rag Lab material.

---

### Task 0: Create the isolated worktree

**Files:**
- No repository file changes.

**Interfaces:**
- Consumes: current `HEAD`, which includes the approved design spec.
- Produces: isolated worktree `E:\java\newProject-rag-rerank` on branch `codex/rag-rerank-experiment`.

- [ ] **Step 1: Create the worktree**

Run from `E:\java\newProject`:

```powershell
git worktree add E:\java\newProject-rag-rerank -b codex/rag-rerank-experiment HEAD
```

Expected: git reports a new worktree and branch.

- [ ] **Step 2: Verify isolation**

Run:

```powershell
cd E:\java\newProject-rag-rerank
git status --short --branch
```

Expected: branch is `codex/rag-rerank-experiment` and the worktree is clean.

- [ ] **Step 3: Verify the existing retrieval contract tests pass in the worktree**

Run:

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_retrieval_contract.py tests/test_retrieval_min_score.py -q
```

Expected: all selected tests pass before experiment edits.

- [ ] **Step 4: Do not commit**

Worktree creation itself does not create a repository commit.

---

### Task 1: Add experiment configuration and reranker interface

**Files:**
- Modify: `ai-module/config.py` near the existing `SF_*` configuration.
- Modify: `ai-module/.env.example` near the embedding configuration.
- Create: `ai-module/core/reranker.py`.
- Create: `ai-module/tests/test_reranker.py`.

**Interfaces:**
- Consumes: `core.cancellation.CancellationToken` and `StreamCancelled`.
- Produces: `NoopReranker.rerank(query, candidates, final_k, cancellation=None, timeout_seconds=...) -> list[dict]`.
- Produces: `safe_rerank(reranker, query, candidates, final_k, cancellation=None, timeout_seconds=...) -> list[dict]`.

- [ ] **Step 1: Write failing tests**

Create `ai-module/tests/test_reranker.py`:

```python
import pytest

from core.cancellation import StreamCancelled
from core.reranker import NoopReranker, safe_rerank


class StubReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [candidates[1], candidates[0]][:final_k]


class BadIdReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [{"id": 999, "title": "unknown"}]


class DuplicateReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [candidates[0], candidates[0]]


class EmptyReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return []


class ErrorReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        raise RuntimeError("reranker unavailable")


class CancelledReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        raise StreamCancelled()


def candidates():
    return [
        {"id": 1, "title": "one"},
        {"id": 2, "title": "two"},
        {"id": 3, "title": "three"},
    ]


def test_noop_reranker_returns_first_final_k():
    result = NoopReranker().rerank("q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_accepts_valid_reordering():
    result = safe_rerank(StubReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [2, 1]


def test_safe_rerank_falls_back_on_unknown_id():
    result = safe_rerank(BadIdReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_falls_back_on_duplicate_id():
    result = safe_rerank(DuplicateReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_fills_remaining_slots_from_original_order():
    result = safe_rerank(NoopReranker(), "q", candidates(), 3)
    assert [item["id"] for item in result] == [1, 2, 3]


def test_safe_rerank_falls_back_on_empty_result():
    result = safe_rerank(EmptyReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_falls_back_on_exception():
    result = safe_rerank(ErrorReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_propagates_cancellation():
    with pytest.raises(StreamCancelled):
        safe_rerank(CancelledReranker(), "q", candidates(), 2)
```

- [ ] **Step 2: Run the tests and confirm they fail**

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_reranker.py -q
```

Expected: failure because `core.reranker` does not exist or required names are missing.

- [ ] **Step 3: Add configuration defaults**

In `ai-module/config.py`, after the existing `SF_EMBED_MODEL` line, add:

```python
# Rerank experiment. Disabled until the read-only evaluation gate passes.
RERANK_ENABLED = _env_bool("RERANK_ENABLED", "false")
RERANK_CANDIDATE_K = int(os.getenv("RERANK_CANDIDATE_K", "10"))
RERANK_FINAL_K = int(os.getenv("RERANK_FINAL_K", "5"))
RERANK_TIMEOUT_SECONDS = float(os.getenv("RERANK_TIMEOUT_SECONDS", "1.0"))
RERANK_BASE_URL = os.getenv("RERANK_BASE_URL", SF_BASE_URL)
RERANK_API_KEY = os.getenv("RERANK_API_KEY", SF_API_KEY)
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
```

In `ai-module/.env.example`, after the embedding settings, add:

```text
# Rerank experiment. Keep disabled unless an approved evaluation is running.
RERANK_ENABLED=false
RERANK_CANDIDATE_K=10
RERANK_FINAL_K=5
RERANK_TIMEOUT_SECONDS=1.0
RERANK_BASE_URL=https://api.siliconflow.cn/v1
RERANK_API_KEY=replace-with-rerank-key
RERANK_MODEL=BAAI/bge-reranker-v2-m3
```

- [ ] **Step 4: Implement the reranker interface and safe wrapper**

Create `ai-module/core/reranker.py`:

```python
# -*- coding: utf-8 -*-
"""Reranker interface and safe fallback wrapper for retrieval experiments."""

from typing import Protocol

from config import RERANK_TIMEOUT_SECONDS
from core.cancellation import StreamCancelled


class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[dict], final_k: int,
               cancellation=None, timeout_seconds: float = RERANK_TIMEOUT_SECONDS) -> list[dict]:
        """Return candidates in reranked order."""
        ...


class NoopReranker:
    def rerank(self, query: str, candidates: list[dict], final_k: int,
               cancellation=None, timeout_seconds: float = RERANK_TIMEOUT_SECONDS) -> list[dict]:
        return list(candidates[:max(0, int(final_k))])


def _candidate_ids(candidates: list[dict]) -> list:
    return [item.get("id") for item in candidates if isinstance(item, dict)]


def safe_rerank(reranker, query: str, candidates: list[dict], final_k: int,
                cancellation=None, timeout_seconds: float = RERANK_TIMEOUT_SECONDS) -> list[dict]:
    """Run a reranker, validating output and falling back to original order."""
    candidates = list(candidates or [])
    final_k = max(0, int(final_k))
    if not candidates or final_k == 0:
        return []

    try:
        ranked = reranker.rerank(
            query,
            candidates,
            final_k,
            cancellation=cancellation,
            timeout_seconds=timeout_seconds,
        )
    except StreamCancelled:
        raise
    except Exception:
        return candidates[:final_k]

    original_ids = _candidate_ids(candidates)
    ranked_ids = _candidate_ids(ranked) if isinstance(ranked, list) else []
    original_set = set(original_ids)

    if (not ranked_ids or len(ranked_ids) != len(set(ranked_ids))
            or any(item_id not in original_set for item_id in ranked_ids)):
        return candidates[:final_k]

    selected = list(ranked[:final_k])
    selected_ids = [item.get("id") for item in selected]
    for item in candidates:
        if len(selected) >= final_k:
            break
        if item.get("id") not in selected_ids:
            selected.append(item)
            selected_ids.append(item.get("id"))
    return selected
```

- [ ] **Step 5: Run the reranker tests**

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_reranker.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add ai-module/config.py ai-module/.env.example ai-module/core/reranker.py ai-module/tests/test_reranker.py
git commit -m "feat: add safe reranker interface and experiment config"
```

---

### Task 2: Add the HTTP reranker adapter

**Files:**
- Create: `ai-module/core/reranker_http.py`.
- Create: `ai-module/tests/test_reranker_http.py`.

**Interfaces:**
- Consumes: the `Reranker` protocol from Task 1.
- Produces: `HTTPReranker.rerank(query, candidates, final_k, cancellation=None, timeout_seconds=...) -> list[dict]`.

- [ ] **Step 1: Write the failing adapter tests**

Create `ai-module/tests/test_reranker_http.py`:

```python
import pytest

from core.reranker_http import HTTPReranker


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def candidates():
    return [
        {"id": 1, "title": "消防通道", "description": "车辆占用消防通道"},
        {"id": 2, "title": "配电箱", "description": "配电箱门缺失"},
    ]


def test_http_reranker_posts_documents_and_maps_ranked_indices():
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append((url, headers, json, timeout))
        return FakeResponse({
            "results": [
                {"index": 1, "relevance_score": 0.98},
                {"index": 0, "relevance_score": 0.42},
            ]
        })

    reranker = HTTPReranker(
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-rerank-model",
        http_post=fake_post,
    )
    result = reranker.rerank("消防通道被占用", candidates(), final_k=2)

    assert [item["id"] for item in result] == [2, 1]
    assert result[0]["rerank_score"] == 0.98
    assert calls[0][0] == "https://example.test/v1/rerank"
    assert calls[0][1]["Authorization"] == "Bearer secret"
    assert calls[0][2]["model"] == "test-rerank-model"
    assert calls[0][2]["top_n"] == 2
    assert calls[0][3] == 1.0


def test_http_reranker_rejects_invalid_result_shape():
    reranker = HTTPReranker(
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-rerank-model",
        http_post=lambda *args, **kwargs: FakeResponse({"results": "bad"}),
    )

    with pytest.raises(ValueError, match="results"):
        reranker.rerank("消防通道被占用", candidates(), final_k=2)
```

- [ ] **Step 2: Run the adapter tests and confirm they fail**

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_reranker_http.py -q
```

Expected: failure because the adapter does not exist.

- [ ] **Step 3: Implement the HTTP adapter**

Create `ai-module/core/reranker_http.py`:

```python
# -*- coding: utf-8 -*-
"""HTTP reranker adapter for an OpenAI-compatible rerank endpoint."""

import requests


class HTTPReranker:
    def __init__(self, base_url: str, api_key: str, model: str, http_post=requests.post):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http_post = http_post

    @staticmethod
    def _document_text(candidate: dict) -> str:
        title = str(candidate.get("title") or candidate.get("name") or "").strip()
        body = str(
            candidate.get("description")
            or candidate.get("content")
            or candidate.get("text")
            or ""
        ).strip()
        return "\n".join(part for part in (title, body) if part)

    def rerank(self, query: str, candidates: list[dict], final_k: int,
               cancellation=None, timeout_seconds: float = 1.0) -> list[dict]:
        if cancellation:
            cancellation.throw_if_cancelled()
        if not candidates:
            return []

        response = self.http_post(
            self.base_url + "/rerank",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "query": query,
                "documents": [self._document_text(item) for item in candidates],
                "top_n": max(1, int(final_k)),
            },
            timeout=float(timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise ValueError("rerank response results must be a list")

        ranked = []
        for row in results:
            if not isinstance(row, dict):
                raise ValueError("rerank result must be an object")
            index = row.get("index")
            score = row.get("relevance_score", row.get("score"))
            if not isinstance(index, int) or index < 0 or index >= len(candidates):
                raise ValueError("rerank result index out of range")
            if not isinstance(score, (int, float)):
                raise ValueError("rerank result score must be numeric")
            item = dict(candidates[index])
            item["rerank_score"] = float(score)
            ranked.append(item)
        return ranked[:max(0, int(final_k))]
```

- [ ] **Step 4: Run the adapter tests**

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_reranker_http.py tests/test_reranker.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add ai-module/core/reranker_http.py ai-module/tests/test_reranker_http.py
git commit -m "feat: add HTTP reranker adapter"
```

---

### Task 3: Add structured candidate retrieval without changing the default search path

**Files:**
- Modify: `ai-module/tools/hybrid_search.py` around `hybrid_search()` and `_merge_results()`.
- Create: `ai-module/tests/test_rerank_candidates.py`.

**Interfaces:**
- Consumes: `HybridSearcher.vector_search()` and `HybridSearcher.keyword_search()`.
- Produces: `HybridSearcher.retrieve_candidates(query, table, vector_k, keyword_k, cancellation=None, timeout_seconds=...) -> list[dict]`.

- [ ] **Step 1: Write failing tests**

Create `ai-module/tests/test_rerank_candidates.py`:

```python
import pytest

from tools.hybrid_search import HybridSearcher, RetrievalTimeout


class FakeSearcher(HybridSearcher):
    def __init__(self, vector_results=None, keyword_results=None, error=None):
        self.vector_results = vector_results or []
        self.keyword_results = keyword_results or []
        self.error = error
        self.vector_calls = []
        self.keyword_calls = []

    def vector_search(self, query, table, top_k=3, cancellation=None, deadline=None):
        self.vector_calls.append((query, table, top_k))
        if self.error:
            raise self.error
        return [dict(item) for item in self.vector_results]

    def keyword_search(self, keyword, table, limit=3, cancellation=None, timeout_seconds=None):
        self.keyword_calls.append((keyword, table, limit))
        return [dict(item) for item in self.keyword_results]


def test_retrieve_candidates_expands_window_and_deduplicates():
    searcher = FakeSearcher(
        vector_results=[
            {"id": 1, "title": "v1"},
            {"id": 2, "title": "v2"},
        ],
        keyword_results=[
            {"id": 2, "title": "k2"},
            {"id": 3, "title": "k3"},
        ],
    )

    result = searcher.retrieve_candidates(
        "query", "tb_hazard_case", vector_k=10, keyword_k=10
    )

    assert [item["id"] for item in result] == [1, 2, 3]
    assert searcher.vector_calls == [("query", "tb_hazard_case", 10)]
    assert searcher.keyword_calls == [("query", "tb_hazard_case", 10)]


def test_retrieve_candidates_propagates_vector_errors():
    searcher = FakeSearcher(error=RetrievalTimeout("timeout"))

    with pytest.raises(RetrievalTimeout):
        searcher.retrieve_candidates("query", "tb_hazard_case")
```

- [ ] **Step 2: Run the failing tests**

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_rerank_candidates.py -q
```

Expected: failure because `retrieve_candidates` is missing.

- [ ] **Step 3: Add `retrieve_candidates()` and reuse it in `hybrid_search()`**

Insert before `hybrid_search()` in `ai-module/tools/hybrid_search.py`:

```python
    def retrieve_candidates(self, query: str, table: str = "tb_hazard_case",
                            vector_k: int = 3, keyword_k: int = 3,
                            cancellation: CancellationToken | None = None,
                            timeout_seconds: float = RETRIEVAL_TIMEOUT_SECONDS) -> list[dict]:
        """Return merged structured candidates for evaluation or reranking."""
        if table not in TABLE_TO_COLLECTION:
            raise ValueError(f"Unsupported retrieval table: {table}")

        deadline = time.monotonic() + max(0.001, float(timeout_seconds))
        _check_cancelled(cancellation)
        vector_results = _call_with_optional_kwargs(
            self.vector_search,
            query,
            table,
            top_k=vector_k,
            cancellation=cancellation,
            deadline=deadline,
        )
        _check_cancelled(cancellation)
        keyword_results = _call_with_optional_kwargs(
            self.keyword_search,
            query,
            table,
            limit=keyword_k,
            cancellation=cancellation,
            timeout_seconds=_remaining(deadline),
        )
        _check_cancelled(cancellation)
        return self._merge_results(keyword_results, vector_results, vector_k, keyword_k)
```

Then replace the existing candidate-fetch body of `hybrid_search()` with:

```python
        try:
            merged = self.retrieve_candidates(
                query,
                table,
                vector_k=vector_k,
                keyword_k=keyword_k,
                cancellation=cancellation,
                timeout_seconds=timeout_seconds,
            )
        except StreamCancelled:
            raise
        except RetrievalTimeout:
            _check_cancelled(cancellation)
            return self._degraded_result(query, table)
        except MilvusRetrievalError as exc:
            _check_cancelled(cancellation)
            return f"Milvus 向量检索不可用：{exc}。请暂时使用 MySQL 检索或稍后重试。"
```

Keep the existing formatting block after this try/except unchanged.

- [ ] **Step 4: Run retrieval tests**

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_retrieval_contract.py tests/test_retrieval_min_score.py tests/test_rerank_candidates.py -q
```

Expected: all tests pass; existing `hybrid_search` assertions remain valid.

- [ ] **Step 5: Commit**

```powershell
git add ai-module/tools/hybrid_search.py ai-module/tests/test_rerank_candidates.py
git commit -m "feat: expose structured retrieval candidates"
```

---

### Task 4: Add the rerank evaluation script

**Files:**
- Create: `ai-module/eval/eval_rerank.py`.
- Create: `ai-module/tests/test_eval_rerank.py`.

**Interfaces:**
- Consumes: `QUERY_SET`, `NEGATIVE_SET`, `category_label`, `production_keyword`, `load_gold_ids` from `eval.eval_retrieval`.
- Consumes: `searcher.retrieve_candidates()` from Task 3 and `safe_rerank()` from Task 1.
- Produces: `evaluate_ranked(ranked_ids, gold_ids, k=5) -> dict`.
- Produces: `gate_result(baseline, rerank) -> dict`.

- [ ] **Step 1: Write failing pure-function tests**

Create `ai-module/tests/test_eval_rerank.py`:

```python
from eval.eval_rerank import evaluate_ranked, gate_result


def test_evaluate_ranked_reports_first_rank_and_mrr():
    result = evaluate_ranked([8, 2, 7, 3], {2, 3, 9}, k=5)

    assert result["top1"] is False
    assert result["hit"] is True
    assert result["first_rank"] == 2
    assert result["mrr"] == 0.5
    assert result["p_at_5"] == 2 / 5
    assert result["recall_at_5"] == 2 / 3


def test_gate_result_rejects_hit_drop():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 0.984, "mrr": 0.920, "top1_hits": 58, "empty_rate": 1.0,
              "added_p95_ms": 100}

    result = gate_result(baseline, rerank)
    assert result["passed"] is False
    assert "Hit@5" in result["reason"]


def test_gate_result_accepts_all_thresholds():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 1.0, "mrr": 0.905, "top1_hits": 55, "empty_rate": 1.0,
              "added_p95_ms": 250}

    result = gate_result(baseline, rerank)
    assert result["passed"] is True
```

- [ ] **Step 2: Confirm the tests fail**

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_eval_rerank.py -q
```

Expected: failure because `eval.eval_rerank` does not exist.

- [ ] **Step 3: Implement the evaluation script**

Create `ai-module/eval/eval_rerank.py`:

```python
# -*- coding: utf-8 -*-
"""Read-only comparison of baseline, expanded candidates, and reranking."""

import json
import os
import sys
import time
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _AI_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import (
    RERANK_API_KEY,
    RERANK_BASE_URL,
    RERANK_CANDIDATE_K,
    RERANK_ENABLED,
    RERANK_FINAL_K,
    RERANK_MODEL,
    RERANK_TIMEOUT_SECONDS,
)
from core.reranker import NoopReranker, safe_rerank
from core.reranker_http import HTTPReranker
from eval.eval_metrics import hit_at_k, mrr, precision_at_k, recall_at_k
from eval.eval_queries import NEGATIVE_SET, QUERY_SET, category_label
from eval.eval_retrieval import load_gold_ids, production_keyword
from tools.hybrid_search import searcher


def evaluate_ranked(ranked_ids, gold_ids, k=5):
    if k <= 0:
        raise ValueError("k must be positive")
    gold = set(gold_ids or [])
    first = None
    for index, item_id in enumerate(ranked_ids or [], 1):
        if item_id in gold:
            first = index
            break
    recall, ceiling = recall_at_k(ranked_ids or [], gold, k)
    return {
        "top1": bool(ranked_ids and ranked_ids[0] in gold),
        "hit": hit_at_k(ranked_ids or [], gold, k),
        "first_rank": first,
        "mrr": mrr(ranked_ids or [], gold),
        "p_at_5": precision_at_k(ranked_ids or [], gold, k),
        "recall_at_5": recall,
        "ceil_at_5": ceiling,
        "top": list(ranked_ids or [])[:k],
    }


def gate_result(baseline, rerank):
    reasons = []
    if rerank["hit_at_5"] < baseline["hit_at_5"]:
        reasons.append("Hit@5 dropped")
    if rerank["mrr"] < baseline["mrr"] + 0.025:
        reasons.append("MRR improvement below 0.025")
    if rerank["top1_hits"] < baseline["top1_hits"] + 5:
        reasons.append("fewer than 5 non-Top-1 queries moved to rank 1")
    if rerank.get("added_p95_ms", 999999) > 300:
        reasons.append("rerank P95 overhead exceeds 300ms")
    if rerank.get("empty_rate", 0.0) < 1.0:
        reasons.append("negative EmptyRate dropped below 1.00")
    return {"passed": not reasons, "reason": "; ".join(reasons)}


def _reranker():
    if not RERANK_ENABLED:
        return NoopReranker()
    return HTTPReranker(
        base_url=RERANK_BASE_URL,
        api_key=RERANK_API_KEY,
        model=RERANK_MODEL,
    )


def _ids(items):
    return [int(item["id"]) for item in items if item.get("id") is not None]


def _collect(mode, keyword, gold):
    started = time.perf_counter()
    if mode == "baseline":
        items = searcher.retrieve_candidates(keyword, "tb_hazard_case", vector_k=3, keyword_k=3)
    elif mode == "expanded":
        items = searcher.retrieve_candidates(
            keyword, "tb_hazard_case",
            vector_k=RERANK_CANDIDATE_K, keyword_k=RERANK_CANDIDATE_K,
        )
    elif mode == "rerank":
        items = searcher.retrieve_candidates(
            keyword, "tb_hazard_case",
            vector_k=RERANK_CANDIDATE_K, keyword_k=RERANK_CANDIDATE_K,
        )
        items = safe_rerank(
            _reranker(), keyword, items, RERANK_FINAL_K,
            timeout_seconds=RERANK_TIMEOUT_SECONDS,
        )
    else:
        raise ValueError(f"unknown mode: {mode}")
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    metrics = evaluate_ranked(_ids(items), gold, RERANK_FINAL_K)
    metrics["latency_ms"] = elapsed_ms
    return metrics


def _p95(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


def main():
    gold_by_label = load_gold_ids()
    modes = ("baseline", "expanded", "rerank")
    records = {mode: [] for mode in modes}
    negatives = {mode: 0 for mode in modes}

    for item in QUERY_SET:
        keyword = production_keyword(item["subcategory"], "槽位有值(schema键)")
        gold = gold_by_label.get(category_label(item["major"], item["subcategory"]), set())
        for mode in modes:
            records[mode].append(_collect(mode, keyword, gold))

    for item in NEGATIVE_SET:
        for mode in modes:
            metrics = _collect(mode, item["query"], set())
            if not metrics["top"]:
                negatives[mode] += 1

    summaries = {}
    for mode in modes:
        rows = records[mode]
        summaries[mode] = {
            "hit_at_5": sum(1.0 for row in rows if row["hit"]) / len(rows),
            "mrr": sum(row["mrr"] for row in rows) / len(rows),
            "top1_hits": sum(1 for row in rows if row["top1"]),
            "empty_rate": negatives[mode] / max(1, len(NEGATIVE_SET)),
            "p95_ms": _p95([row["latency_ms"] for row in rows]),
        }

    baseline_p95 = summaries["baseline"]["p95_ms"]
    summaries["expanded"]["added_p95_ms"] = max(
        0.0, summaries["expanded"]["p95_ms"] - baseline_p95
    )
    summaries["rerank"]["added_p95_ms"] = max(
        0.0, summaries["rerank"]["p95_ms"] - baseline_p95
    )

    gate = gate_result(summaries["baseline"], summaries["rerank"])
    payload = {
        "date": "2026-11-27",
        "rerank_enabled": RERANK_ENABLED,
        "candidate_k": RERANK_CANDIDATE_K,
        "final_k": RERANK_FINAL_K,
        "model": RERANK_MODEL,
        "summaries": summaries,
        "gate": gate,
    }
    out = Path(_AI_ROOT) / "db" / "eval_rerank_output.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_eval_rerank.py tests/test_reranker.py tests/test_reranker_http.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add ai-module/eval/eval_rerank.py ai-module/tests/test_eval_rerank.py
git commit -m "feat: add rerank evaluation harness"
```

---

### Task 5: Cloud read-only evaluation and evidence report

**Files:**
- Create: `docs/evidence/2026-11-27-rerank-experiment.md`.
- Create: `docs/evidence/2026-11-27-rerank-experiment.json`.
- Generated: `ai-module/db/eval_rerank_output.json`.

**Interfaces:**
- Consumes: the experiment branch from Tasks 0–4.
- Produces: a merge/no-merge decision with reproducible evidence.

- [ ] **Step 1: Verify local tests**

```powershell
cd E:\java\newProject-rag-rerank\ai-module
python -m pytest tests/test_reranker.py tests/test_reranker_http.py tests/test_rerank_candidates.py tests/test_eval_rerank.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run read-only cloud evaluation through SSH**

On the cloud host, using the deployment venv and `127.0.0.1` services:

```powershell
ssh ubuntu@106.53.219.214 "cd /home/ubuntu/ai-module && venv/bin/python3 eval/eval_rerank.py"
```

Expected: produces `db/eval_rerank_output.json`; no database writes; no MySQL fallback.

- [ ] **Step 3: Verify output integrity**

```powershell
Get-FileHash E:\java\newProject-rag-rerank\ai-module\db\eval_rerank_output.json -Algorithm SHA256
```

Expected: report the hash in evidence; do not treat a failed or missing output as a result.

- [ ] **Step 4: Write evidence report**

The evidence report must include:

```text
- branch and commit
- code hashes for reranker.py, reranker_http.py, hybrid_search.py, eval_rerank.py
- cloud run command and environment
- case count, query count, negative count
- baseline/expanded/rerank summaries
- MRR, Top-1, Hit@5, P@5, Recall@5, P95 and EmptyRate
- failure samples
- gate result and exact failed reasons
- whether model was Noop or real
- whether the branch is eligible for merge
```

- [ ] **Step 5: Decide and commit evidence**

If `gate.passed=true`, commit the evidence and proceed to a separate integration plan.
If `gate.passed=false`, commit the evidence, do not merge, and preserve the branch as Rag Lab material.

```powershell
git add docs/evidence/2026-11-27-rerank-experiment.md docs/evidence/2026-11-27-rerank-experiment.json
git commit -m "eval: record rerank experiment result"
```

- [ ] **Step 6: Do not merge automatically**

Merging to the main project requires a separate approved plan and a clean rerun against the main branch baseline.

---

## Plan Self-Review

### Spec coverage

- Isolated experimental branch: Task 0.
- Default-off feature flag: Task 1.
- Candidate pool 10+10 → final 5: Task 3 and Task 4.
- Pluggable reranker: Tasks 1–2.
- Safe fallback for errors, malformed output and empty output: Task 1.
- Existing `hybrid_search` default preserved: Task 3 uses compatibility tests.
- No chunking/schema/frontend changes: Global Constraints and spec non-goals.
- Read-only cloud evaluation: Task 5.
- Pre-registered gate and Lab fallback: Task 4 `gate_result()` and Task 5 Step 5.
- No fake model results: Task 4 distinguishes Noop from real model; evidence must report model mode.

### Type consistency

- `Reranker.rerank(query, candidates, final_k, cancellation, timeout_seconds)`.
- `safe_rerank(...)` consumes the same signature.
- `HTTPReranker` implements the same signature.
- `HybridSearcher.retrieve_candidates(...)` returns `list[dict]`.
- `evaluate_ranked(ranked_ids, gold_ids, k=5)` consumes IDs, not candidate dicts.
- `gate_result(baseline, rerank)` consumes summary dicts with exact keys used in `main()`.

### Placeholder scan

No `TBD`, `TODO`, "implement later", "similar to Task N", or unspecified error-handling steps are present.
