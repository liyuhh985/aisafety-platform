# Milvus Vector Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将安全平台当前由 Python 扫描 MySQL 全表完成的应用层向量检索，升级为一个 Milvus 实例中的三个逻辑 collection，同时保留 MySQL 关键词检索、原文权威存储和可配置回退路径。

**Architecture:** MySQL 继续作为案例、政策知识和法规原文及业务字段的唯一事实来源。Milvus 只保存三类文档的 `doc_id`、内容哈希和 Embedding 向量；检索先在对应 collection 中取得 Top-K 的 ID，再批量回 MySQL 查询完整内容，最后与 MySQL `LIKE` 结果合并。Milvus 不可用、Embedding 维度不一致或同步未完成时，通过配置回退到现有的 MySQL 暴力向量检索，不能影响现有报告生成链路。

**Tech Stack:** Python 3.13 runtime already used by `ai-module`, MySQL, Milvus Standalone, `pymilvus`, existing SiliconFlow Embedding API (`BAAI/bge-m3`), NumPy, unittest, Docker Compose.

## Global Constraints

- MySQL remains the source of truth; do not delete or move the existing knowledge tables.
- Use one Milvus server with three collections: `hazard_cases`, `hazard_policies`, and `hazard_regulations`; do not deploy three Milvus servers.
- Do not use a floating Docker image tag such as `latest`; check the official Milvus compatibility matrix and pin an exact server image and matching `pymilvus` version during implementation.
- The vector metric is cosine similarity. The configured dimension must match the actual Embedding API response; fail fast on a dimension mismatch.
- The current `BAAI/bge-m3` model is the default model. Do not mix document vectors and query vectors produced by different models in one collection.
- The existing MySQL `LIKE` search remains part of hybrid retrieval and remains available when Milvus is disabled.
- `VECTOR_BACKEND=mysql` must provide an immediate rollback path. `VECTOR_BACKEND=milvus` may only be used after a successful full synchronization and smoke test.
- Do not put API keys, MySQL passwords, or Milvus credentials into committed files.
- Preserve the existing retrieval result sections and SSE order: cases, policy, regulations, then report generation.
- Existing unrelated worktree changes belong to the user and must not be reverted.

---

## Current Baseline

The current implementation is in `ai-module/tools/hybrid_search.py`:

1. `vector_search()` reads every row from the selected MySQL table.
2. It obtains or computes a document vector and calculates cosine similarity in Python for every row.
3. `keyword_search()` performs a MySQL `LIKE` search.
4. `hybrid_search()` merges and de-duplicates both result sets.
5. `ai-module/core/orchestrator.py` calls the searcher separately for `tb_hazard_case`, `tb_hazard_knowledge`, and `tb_regulation`.

The new implementation must preserve the public call shape used by the orchestrator:

```python
searcher.hybrid_search(query, table, vector_k=3, keyword_k=3) -> str
```

The internal vector branch will change from full-table scanning to Milvus Top-K search, but the formatted output and MySQL fallback must remain compatible.

## Target Data Model

Use the following table-to-collection mapping in one constant, rather than scattering string literals across the code:

```python
TABLE_TO_COLLECTION = {
    "tb_hazard_case": "hazard_cases",
    "tb_hazard_knowledge": "hazard_policies",
    "tb_regulation": "hazard_regulations",
}
```

Each collection uses the same schema:

```text
doc_id       INT64, primary key, not auto-generated
content_hash VARCHAR(64)
embedding    FLOAT_VECTOR, dim = MILVUS_EMBEDDING_DIM
```

The complete text is deliberately not authoritative in Milvus. Search returns `doc_id` and distance; the application uses those IDs to read the latest content from MySQL. This prevents stale report text when a policy or regulation is edited after synchronization.

## Task 1: Establish a Retrieval Contract and Baseline Tests

**Files:**
- Create: `ai-module/tests/__init__.py`
- Create: `ai-module/tests/test_retrieval_contract.py`
- Modify: `ai-module/tools/hybrid_search.py` only if a small test seam is needed

**Interfaces:**
- Consumes: existing `HybridSearcher.hybrid_search()` behavior.
- Produces: tests that define output sections, table validation, empty-result behavior, and the MySQL fallback contract before Milvus is introduced.

- [ ] **Step 1: Add tests for the current public retrieval behavior**

Use fakes for the vector and keyword branches so tests do not require MySQL, Milvus, or an Embedding API. Assert that `hybrid_search()` returns a non-empty “no result” message for an empty source and that duplicate IDs appear once.

- [ ] **Step 2: Add a test for invalid table names**

Assert that an unsupported table name raises `ValueError` before any database call. This prevents a future collection mapping from accepting arbitrary SQL identifiers.

- [ ] **Step 3: Run the baseline tests**

Run from `ai-module`:

```powershell
python -m unittest discover -s tests -v
```

Expected: all new tests pass against the current implementation, or the smallest test seam is added without changing runtime behavior.

- [ ] **Step 4: Commit the baseline contract**

```powershell
git add ai-module/tests ai-module/tools/hybrid_search.py
git commit -m "test: define retrieval contract before Milvus migration"
```

## Task 2: Add Milvus Runtime Configuration and Local Service

**Files:**
- Create: `ai-module/docker-compose.milvus.yml`
- Modify: `ai-module/config.py`
- Modify: `ai-module/.env.example`
- Modify: `ai-module/requirements.txt`
- Create: `ai-module/tests/test_milvus_config.py`

**Interfaces:**
- Consumes: existing `.env` loading in `config.py`.
- Produces: typed-enough module constants for backend selection, Milvus connection, collection names, and vector dimension.

- [ ] **Step 1: Check official Milvus and PyMilvus compatibility**

Before editing dependency versions, read the current official Milvus Standalone and PyMilvus installation documentation. Select one exact Milvus image tag and a matching `pymilvus` version. Record both versions in the compose file and `requirements.txt`; never use `latest`.

- [ ] **Step 2: Add configuration constants**

Add these environment variables with safe local defaults:

```text
VECTOR_BACKEND=mysql
MILVUS_ENABLED=false
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_ALIAS=safety_platform
MILVUS_EMBEDDING_DIM=1024
MILVUS_TIMEOUT_SECONDS=5
MILVUS_FALLBACK_TO_MYSQL=true
MILVUS_CASE_COLLECTION=hazard_cases
MILVUS_POLICY_COLLECTION=hazard_policies
MILVUS_REGULATION_COLLECTION=hazard_regulations
```

Parse the numeric values as integers/floats in `config.py`, and reject unsupported `VECTOR_BACKEND` values with a clear startup error.

- [ ] **Step 3: Add the pinned PyMilvus dependency**

Add the exact compatibility-checked `pymilvus` version. Do not add a second vector client library.

- [ ] **Step 4: Add the local Milvus compose file**

Use the official Milvus Standalone topology required by the selected version, including its required etcd and MinIO services. Bind Milvus to `127.0.0.1` for local development, add health checks where supported, and use named volumes so a container restart does not silently delete the index.

- [ ] **Step 5: Test configuration without importing a live Milvus connection**

Mock environment variables and assert defaults, integer conversion, collection names, and invalid backend rejection.

- [ ] **Step 6: Run the configuration tests**

```powershell
python -m unittest tests.test_milvus_config -v
```

- [ ] **Step 7: Commit the runtime setup**

```powershell
git add ai-module/docker-compose.milvus.yml ai-module/config.py ai-module/.env.example ai-module/requirements.txt ai-module/tests/test_milvus_config.py
git commit -m "feat: add pinned Milvus local runtime configuration"
```

## Task 3: Implement the Milvus Collection Adapter

**Files:**
- Create: `ai-module/tools/milvus_store.py`
- Create: `ai-module/tests/test_milvus_store.py`

**Interfaces:**
- Consumes: Milvus host/port, collection constants, and an injected Milvus client for tests.
- Produces:

```python
class MilvusVectorStore:
    def connect(self) -> None: ...
    def ensure_collections(self) -> None: ...
    def healthcheck(self) -> bool: ...
    def upsert(self, table: str, records: list[dict]) -> None: ...
    def delete_ids(self, table: str, doc_ids: list[int]) -> None: ...
    def search(self, table: str, query_vector: list[float], top_k: int) -> list[dict]: ...
```

Each returned search hit must have this shape:

```python
{"id": 123, "distance": 0.86, "content_hash": "..."}
```

- [ ] **Step 1: Write fake-client tests for collection creation**

Assert that `ensure_collections()` creates exactly the three mapped collections, uses `doc_id` as the primary key, uses the configured vector dimension, and creates a cosine-compatible index.

- [ ] **Step 2: Write fake-client tests for upsert and search**

Assert that `upsert()` maps MySQL IDs to `doc_id`, rejects vectors with the wrong dimension, and that `search()` returns normalized hit dictionaries sorted by the client response.

- [ ] **Step 3: Write a test for invalid table names**

Assert that `upsert()`, `delete_ids()`, and `search()` reject tables outside `TABLE_TO_COLLECTION`.

- [ ] **Step 4: Implement connection and schema creation**

Use the official `pymilvus` client API compatible with the selected server version. Keep all schema and index parameters in this file. Do not create collections during module import; require an explicit `connect()` or `ensure_collections()` call.

- [ ] **Step 5: Implement dimension validation**

Validate both the configured dimension and every inserted/query vector. A mismatch must raise a dedicated error that the retrieval layer can convert into a MySQL fallback, rather than silently inserting invalid data.

- [ ] **Step 6: Run adapter tests**

```powershell
python -m unittest tests.test_milvus_store -v
```

- [ ] **Step 7: Commit the adapter**

```powershell
git add ai-module/tools/milvus_store.py ai-module/tests/test_milvus_store.py
git commit -m "feat: add Milvus collection adapter"
```

## Task 4: Add Idempotent MySQL-to-Milvus Synchronization

**Files:**
- Create: `ai-module/tools/knowledge_sync.py`
- Create: `ai-module/tests/test_knowledge_sync.py`
- Modify: `ai-module/tools/hybrid_search.py` only to reuse a shared Embedding client if extraction is necessary

**Interfaces:**
- Consumes: the three MySQL tables, the existing Embedding model configuration, and `MilvusVectorStore`.
- Produces:

```powershell
python -m tools.knowledge_sync --source all --rebuild
python -m tools.knowledge_sync --source case
python -m tools.knowledge_sync --source policy
python -m tools.knowledge_sync --source regulation
```

- [ ] **Step 1: Define source readers**

Read only the fields needed to form the embedding text:

```text
case:        title + description + cause + rectification
policy:      title + content
regulation:  law_name + article + content + keywords
```

Return `id`, normalized text, and a SHA-256 `content_hash`. Keep the existing full columns in MySQL; do not copy all report fields into Milvus.

- [ ] **Step 2: Write synchronization tests**

Using fake MySQL rows, fake Embedding responses, and a fake store, test that unchanged hashes are skipped, changed rows are upserted, and `--rebuild` clears/replaces only the selected collection.

- [ ] **Step 3: Implement batched synchronization**

Process records in bounded batches. Generate document vectors with the same Embedding model used for queries. Log source name, read count, skipped count, upsert count, and failure count without logging API keys or full document contents.

- [ ] **Step 4: Handle Embedding failure safely**

Do not insert the existing 256-dimensional n-gram fallback vector into a 1024-dimensional Milvus collection. If the real Embedding API is unavailable, stop the sync with a non-zero exit code and tell the operator to use `VECTOR_BACKEND=mysql` until the service is restored.

- [ ] **Step 5: Implement stale-record cleanup for rebuilds**

For `--rebuild`, drop and recreate only the selected logical collection, then load all current MySQL IDs. For normal incremental sync, upsert changed/new IDs; document that physical deletion requires `--rebuild` until a change-log mechanism exists.

- [ ] **Step 6: Run synchronization unit tests**

```powershell
python -m unittest tests.test_knowledge_sync -v
```

- [ ] **Step 7: Commit the synchronization command**

```powershell
git add ai-module/tools/knowledge_sync.py ai-module/tests/test_knowledge_sync.py ai-module/tools/hybrid_search.py
git commit -m "feat: add idempotent knowledge synchronization to Milvus"
```

## Task 5: Switch Hybrid Retrieval to Milvus with Explicit Fallback

**Files:**
- Modify: `ai-module/tools/hybrid_search.py`
- Create: `ai-module/tests/test_hybrid_milvus_backend.py`
- Modify: `ai-module/agents/retrieval_agent.py` only if tool descriptions need to name the new backend behavior

**Interfaces:**
- Consumes: `MilvusVectorStore`, existing MySQL keyword search, and an Embedding client.
- Produces: the unchanged `hybrid_search(query, table, vector_k, keyword_k) -> str` interface.

- [ ] **Step 1: Write backend-selection tests**

Cover these cases with fakes:

1. `VECTOR_BACKEND=mysql` uses the existing MySQL vector branch.
2. `VECTOR_BACKEND=milvus` uses Milvus and then MySQL keyword search.
3. Milvus connection/search failure with fallback enabled uses MySQL vector search and still returns keyword results.
4. Milvus failure with fallback disabled returns a clear retrieval error instead of silently claiming that no regulation exists.
5. A Milvus result ID is hydrated from MySQL before formatting.

- [ ] **Step 2: Separate the old branch into a named fallback method**

Rename or extract the current full-table scan as an internal method such as:

```python
def mysql_vector_search(self, query: str, table: str, top_k: int) -> list[dict]: ...
```

Keep its existing JSON embedding cache behavior for rollback compatibility.

- [ ] **Step 3: Implement Milvus retrieval**

Generate one query vector, search the collection mapped from the validated table name, then bulk-read the returned IDs from the matching MySQL table. Preserve Milvus distance as `match_score` internally, but do not expose implementation-specific fields in the existing formatted report unless useful for diagnostics.

- [ ] **Step 4: Preserve hybrid merge semantics**

Run vector retrieval and keyword retrieval for the same source table, de-duplicate by integer ID, and retain the existing result formatting for cases, policy, and regulations. A missing regulation result must continue to be represented as an explicit no-result state.

- [ ] **Step 5: Add health-aware fallback logging**

Log one concise warning per request when Milvus is unavailable, including source and fallback reason. Do not log full user uploads, document content, tokens, or secrets.

- [ ] **Step 6: Run retrieval tests**

```powershell
python -m unittest tests.test_hybrid_milvus_backend -v
```

- [ ] **Step 7: Commit the retrieval switch**

```powershell
git add ai-module/tools/hybrid_search.py ai-module/tests/test_hybrid_milvus_backend.py ai-module/agents/retrieval_agent.py
git commit -m "feat: use Milvus for vector retrieval with MySQL fallback"
```

## Task 6: Run Local Integration and Backfill the Three Collections

**Files:**
- Modify: `ai-module/.env.example` if an operational variable is missing
- Create: `ai-module/tests/test_milvus_integration.py`
- Create: `docs/milvus-local-runbook.md`

**Interfaces:**
- Consumes: the compose service, synchronization command, and hybrid search backend.
- Produces: a repeatable local setup and verification procedure for a fresh developer machine.

- [ ] **Step 1: Install the Python dependency in the active environment**

From `ai-module`, install the pinned requirements using the same Python interpreter used to run the service. Verify that `python -c "from pymilvus import MilvusClient; print('ok')"` succeeds.

- [ ] **Step 2: Start Milvus Standalone**

Run:

```powershell
docker compose -f docker-compose.milvus.yml up -d
docker compose -f docker-compose.milvus.yml ps
```

Expected: etcd, MinIO, and Milvus are healthy; host port `19530` accepts a connection.

- [ ] **Step 3: Create collections and backfill all sources**

With MySQL and the real Embedding API available, run:

```powershell
python -m tools.knowledge_sync --source all --rebuild
```

Expected logs must show non-zero or explicitly empty counts for each of `case`, `policy`, and `regulation`, with no dimension mismatch.

- [ ] **Step 4: Enable Milvus only in the local environment**

Set:

```text
MILVUS_ENABLED=true
VECTOR_BACKEND=milvus
MILVUS_FALLBACK_TO_MYSQL=true
```

Restart only the Python AI service so it creates a fresh client connection.

- [ ] **Step 5: Run retrieval smoke tests**

Use at least these queries:

```text
施工现场临时用电隐患
高处作业未设置防护措施
消防通道被占用
```

Verify that each query returns separate case, policy, and regulation sections, and that every returned document can be hydrated from MySQL.

- [ ] **Step 6: Verify fallback behavior**

Stop only the Milvus container, run one analysis, and verify that the AI service logs a fallback and still emits the existing SSE sequence and report. Restore Milvus and verify Milvus retrieval resumes after service restart.

- [ ] **Step 7: Add the runbook**

Document start, stop, health check, full rebuild, incremental sync, log interpretation, rollback to `VECTOR_BACKEND=mysql`, and named-volume backup. Include the exact image and PyMilvus versions selected during implementation.

- [ ] **Step 8: Commit the integration documentation and test**

```powershell
git add ai-module/.env.example ai-module/tests/test_milvus_integration.py docs/milvus-local-runbook.md
git commit -m "docs: add Milvus local integration and rollback runbook"
```

## Task 7: Verify Performance, Correctness, and Existing User Flow

**Files:**
- Create: `ai-module/tests/test_retrieval_quality_cases.py`
- Modify: `docs/milvus-local-runbook.md` with measured results only

**Interfaces:**
- Consumes: the Milvus-backed searcher and the existing SSE/orchestrator tests.
- Produces: evidence that the migration improves retrieval mechanics without changing report semantics or account isolation.

- [ ] **Step 1: Create a small fixed retrieval evaluation set**

Add at least ten queries covering construction, fire safety, gas safety, traffic safety, and environmental safety. For each query, record the expected source type and at least one acceptable document ID from the seeded MySQL data. Do not use generated legal claims as expected answers.

- [ ] **Step 2: Compare MySQL and Milvus result sets**

For every evaluation query, record whether the expected document appears in Top-3. Investigate differences rather than automatically treating Milvus as correct; the source text and Embedding model are the authority for interpretation.

- [ ] **Step 3: Measure retrieval latency**

Run at least 20 repeated searches with the same query in both backends and record p50 and p95 latency for vector retrieval only. Include dataset counts and machine details in the runbook.

- [ ] **Step 4: Run all existing AI-module tests**

```powershell
python -m unittest discover -s tests -v
python test_orchestrator_stream.py
python test_server_sse_errors.py
python test_server_upload_validation.py
```

Expected: existing SSE event order, error handling, upload validation, and report formatting remain passing.

- [ ] **Step 5: Run the end-to-end user flow**

Analyze an image as account 1, log out, log in as account 2, and analyze a different image. Confirm that Milvus retrieval only uses public knowledge sources and that report/history data remains isolated by authenticated user. Milvus collections must never contain user-specific report or session data.

- [ ] **Step 6: Verify rollback**

Set `VECTOR_BACKEND=mysql`, restart the Python service, and repeat one analysis. The result must still contain cases, policy, regulations, and report output. This is the release gate for the migration.

- [ ] **Step 7: Commit only measured documentation changes**

```powershell
git add ai-module/tests/test_retrieval_quality_cases.py docs/milvus-local-runbook.md
git commit -m "test: verify Milvus retrieval quality and rollback"
```

## Acceptance Criteria

- One pinned Milvus Standalone service runs locally with persistent named volumes.
- Three collections exist and map one-to-one to the three MySQL source tables.
- A full synchronization can be rerun idempotently and reports counts for all three sources.
- Milvus vector search no longer reads all MySQL documents and calculates every cosine similarity in Python.
- MySQL remains the source of truth and keyword retrieval remains active.
- Missing or stale Milvus service has an explicit, tested MySQL fallback.
- Embedding API failures cannot insert vectors with the wrong dimension.
- Case, policy, and regulation results remain separately labeled and ordered in SSE output.
- A missing regulation result is reported as “暂未检索到明确法规条款，建议人工复核”, not replaced by a fabricated legal citation.
- Existing AI-module tests and the account-switching regression flow still pass.
- The runbook contains start, stop, sync, health check, rollback, and backup instructions.

## Rollback Plan

1. Set `VECTOR_BACKEND=mysql` and `MILVUS_ENABLED=false` in the AI module environment.
2. Restart only the Python AI service.
3. Keep the Milvus volumes intact for diagnosis; do not delete them as part of a normal rollback.
4. If the index is corrupt, stop the compose stack and recreate only the Milvus named volumes after confirming that MySQL remains available as the source of truth.
5. Re-enable Milvus only after `healthcheck`, synchronization, and retrieval smoke tests pass.

## Self-Review

- Spec coverage: runtime setup, three logical collections, initial backfill, retrieval integration, fallback, tests, performance comparison, rollback, and operational documentation are covered by Tasks 1-7.
- Placeholder scan: no task depends on a `TBD` implementation; the only version choice is deliberately required to be checked against the official compatibility matrix and then pinned before dependency installation.
- Type consistency: `MilvusVectorStore.search()` returns `id`, `distance`, and `content_hash`; the hybrid layer hydrates `id` from MySQL and preserves the existing string return contract.
- Scope check: this plan changes only the AI retrieval subsystem and its local infrastructure. It does not change Java APIs, authentication, report ownership, frontend state, or FRP.
