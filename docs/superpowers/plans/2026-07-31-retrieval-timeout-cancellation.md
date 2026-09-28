# Retrieval Timeout and Cancellation Implementation Plan

> **For agentic workers:** Execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound each cases, policy, and regulation retrieval to 10 seconds, return a clear degraded result on timeout, and release active HTTP, MySQL, and Milvus resources when the SSE cancellation token is triggered.

**Architecture:** `HybridSearcher.hybrid_search()` owns one deadline per logical library lookup. It passes the remaining budget and `CancellationToken` through vector, embedding, MySQL, keyword, and hydration operations. Concrete clients apply the remaining timeout to their calls and register close callbacks; timeout is converted to a per-library fallback string, while client cancellation still raises `StreamCancelled` so the orchestrator stops the pipeline.

**Tech Stack:** Python 3.13, `requests`, PyMySQL, pymilvus, FastAPI SSE, existing `CancellationToken`.

## Global Constraints

- The budget is 10 seconds per `hybrid_search()` call, including vector and keyword work for that table.
- Cases, policy, regulation, and any extra case keyword lookup each get an independent budget.
- A timeout returns a degraded retrieval string and allows the orchestrator to continue with the next library.
- Browser cancellation raises `StreamCancelled` and must not be converted into a degraded result or an SSE error/done event.
- Every created response/connection is closed in `finally`; active closers are registered with `CancellationToken` while the operation is in progress.
- Existing callers and test doubles that do not accept new optional arguments remain compatible.
- Do not change non-streaming endpoint behavior beyond sharing the same bounded search implementation.

---

### Task 1: Add failing retrieval timeout tests

**Files:**
- Create: `ai-module/test_retrieval_timeout_cancellation.py`
- Modify: `ai-module/test_orchestrator_stream.py`

**Interfaces:**
- Tests expect `HybridSearcher.hybrid_search(..., cancellation=token, timeout_seconds=10)` and concrete calls to receive a remaining timeout.
- Tests expect cancellation to propagate as `StreamCancelled`, timeout to return a degraded string, MySQL connection options to include bounded timeouts, and Milvus search to receive a timeout.

- [x] Write tests for timeout fallback, cancellation propagation, MySQL connection cleanup, embedding response cleanup, Milvus timeout propagation, and orchestrator forwarding.
- [x] Run only this new test module once and confirm it fails because the optional timeout/cancellation contract is not implemented.

### Task 2: Add shared retrieval deadline and cancellation plumbing

**Files:**
- Modify: `ai-module/config.py`
- Modify: `ai-module/tools/hybrid_search.py`

**Interfaces:**
- Add `RETRIEVAL_TIMEOUT_SECONDS`, default `10.0`.
- Extend vector and hybrid search methods with optional `cancellation` and `deadline`/timeout arguments while preserving current defaults.
- Add internal `RetrievalTimeout` and helpers for checking cancellation and computing remaining seconds.

- [x] Make one deadline per logical table lookup.
- [x] Preserve `StreamCancelled`; convert only deadline expiry into the degraded result.
- [x] Use the remaining budget for every sub-operation and stop starting another sub-operation when the budget is exhausted.

### Task 3: Bound and close MySQL and embedding operations

**Files:**
- Modify: `ai-module/tools/hybrid_search.py`
- Modify: `ai-module/tools/knowledge_sync.py`

**Interfaces:**
- MySQL helpers accept the token and remaining timeout, pass `connect_timeout`, `read_timeout`, and `write_timeout`, register `conn.close`, and unregister it in `finally`.
- `SiliconFlowEmbeddingClient.embed()` accepts optional `timeout_seconds` and `cancellation`, closes the response, and registers its response closer after response creation.

- [x] Apply the same connection lifecycle to keyword, full-row, and ID hydration queries.
- [x] Apply the remaining timeout to both raw embedding requests and the Milvus embedding client.
- [x] Keep existing embedding fallback behavior for ordinary service errors, but never swallow `StreamCancelled`.

### Task 4: Bound Milvus and connect orchestrator retrieval stages

**Files:**
- Modify: `ai-module/tools/milvus_store.py`
- Modify: `ai-module/tools/hybrid_search.py`
- Modify: `ai-module/core/orchestrator.py`

**Interfaces:**
- `MilvusVectorStore.search(..., timeout_seconds=None, cancellation=None)` passes the call timeout to the SDK and registers an available client close callback.
- Both streaming retrieval paths call each `hybrid_search()` with the same cancellation token and independent 10-second budget; ordinary callers remain valid.

- [x] Ensure Milvus timeout or service failure can use the existing MySQL fallback without exceeding the logical lookup deadline.
- [x] Ensure a timed-out cases lookup does not prevent policy or regulation lookup from starting.
- [x] Ensure browser cancellation stops before the next library and never produces a synthetic retrieval fallback.

### Task 5: Final focused verification and review

**Files:**
- Review: all files changed by Tasks 1-4
- Modify: `docs/superpowers/plans/2026-07-31-retrieval-timeout-cancellation.md`

- [x] Run the new retrieval test module once after implementation.
- [x] Run the existing five focused Python cancellation/orchestrator tests once as a consolidated regression check.
- [x] Run Java compilation/tests if Maven is available; otherwise record the environment limitation without repeating the command.
- [x] Inspect the diff for timeout propagation, cancellation races, cleanup in `finally`, and accidental changes to non-streaming endpoints.
- [x] Record exact verification results and remaining limitations in this plan.

Verification:

- `python -m unittest test_retrieval_timeout_cancellation test_orchestrator_stream`: 8 tests passed.
- `python -m unittest tests.test_knowledge_sync tests.test_milvus_store`: 20 tests passed.
- `python -m unittest discover -s tests`: 45 tests passed, 3 skipped.
- `python -m unittest test_server_sse_cancellation test_server_sse_errors test_agent_cancellation test_retrieval_timeout_cancellation test_orchestrator_stream tests.test_retrieval_import`: 13 tests passed.
- `git diff --check`: passed.
- Java focused tests were not rerun because Maven and the Maven Wrapper are unavailable in this workspace; the limitation was already recorded by the preceding SSE cancellation task.
- The Python regression suite emits an existing Starlette/httpx deprecation warning and Milvus fallback logs; neither affects test results.
