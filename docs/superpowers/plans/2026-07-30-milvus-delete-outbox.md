# Milvus Delete Outbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete a MySQL case, policy, or regulation immediately while durably and eventually deleting the same `doc_id` from its mapped Milvus collection.

**Architecture:** The Java service commits the domain deletion and a `DELETE` outbox event in one MySQL transaction. A scheduled Java worker claims durable events and calls a token-protected Python endpoint, which delegates to the existing `MilvusVectorStore.delete_ids()`; transient failures are retried with capped exponential delay.

**Tech Stack:** Java 21, Spring Boot 3.3.5, Spring Security, MyBatis-Plus 3.5.7, MySQL 8, FastAPI, Pydantic, PyMilvus, JUnit 5, Mockito, Python `unittest`.

## Global Constraints

- Keep the existing mappings `tb_hazard_case` to `hazard_cases`, `tb_hazard_knowledge` to `hazard_policies`, and `tb_regulation` to `hazard_regulations`.
- A single-record deletion must never recreate a Milvus collection or re-embed unrelated rows.
- MySQL deletion succeeds once the domain row and outbox event commit; it does not wait for Milvus.
- Retry transient failures without an attempt limit, cap retry delay at one hour, and reclaim `PROCESSING` tasks after five minutes.
- Keep anonymous `GET` access for cases, knowledge, and regulations; require JWT authentication for `DELETE`.
- Require `AI_INTERNAL_TOKEN` for the Python internal endpoint and never log or commit its value.
- Preserve all unrelated working-tree changes and stage only files belonging to each task.

---

## File Map

- `ai-module/config.py`: expose `AI_INTERNAL_TOKEN`.
- `ai-module/server.py`: validate the internal request and invoke the vector store.
- `ai-module/tests/test_vector_delete_api.py`: Python endpoint contract tests.
- `ai-module/.env.example`: document the internal token variable.
- `ai-module/db/migrate.sql`: create the durable outbox table and indexes.
- `safety-pojo/src/main/java/com/safety/pojo/entity/VectorSyncOutbox.java`: MyBatis entity for one vector-sync event.
- `safety-service/src/main/java/com/safety/service/mapper/VectorSyncOutboxMapper.java`: due-task polling and atomic state transitions.
- `safety-service/src/main/java/com/safety/service/service/VectorSyncOutboxService.java`: enqueue events, claim tasks, and calculate retry state.
- `safety-service/src/main/java/com/safety/service/service/CaseService.java`: transactional case deletion.
- `safety-service/src/main/java/com/safety/service/service/KnowledgeService.java`: transactional policy deletion.
- `safety-service/src/main/java/com/safety/service/service/RegulationService.java`: transactional regulation deletion.
- `safety-service/src/test/java/com/safety/service/service/KnowledgeDeleteServiceTest.java`: domain deletion/outbox tests for all three services.
- `safety-service/src/test/java/com/safety/service/service/VectorSyncOutboxServiceTest.java`: claim, retry, success, and permanent-failure state tests.
- `safety-web/src/main/java/com/safety/web/controller/{Case,Knowledge,Regulation}Controller.java`: authenticated delete HTTP endpoints.
- `safety-web/src/main/java/com/safety/web/config/SecurityConfig.java`: method-specific anonymous read rules.
- `safety-web/src/main/java/com/safety/web/service/AiService.java`: configurable AI URL and authenticated vector-delete call.
- `safety-web/src/main/java/com/safety/web/service/VectorDeleteOutboxWorker.java`: scheduled delivery loop.
- `safety-web/src/main/java/com/safety/web/SafetyApplication.java`: enable scheduling.
- `safety-web/src/main/resources/application.yml`: AI client and worker settings.
- `safety-web/src/main/resources/application-local.yml.example`: safe configuration examples.
- `safety-web/src/test/java/com/safety/web/controller/KnowledgeDeleteControllerTest.java`: controller response tests.
- `safety-web/src/test/java/com/safety/web/config/KnowledgeEndpointSecurityTest.java`: anonymous GET versus DELETE security contract.
- `safety-web/src/test/java/com/safety/web/service/AiServiceVectorDeleteTest.java`: outgoing URL, JSON, and token contract.
- `safety-web/src/test/java/com/safety/web/service/VectorDeleteOutboxWorkerTest.java`: worker success and failure classification.

### Task 1: Protected Python Vector Deletion API

**Files:**
- Create: `ai-module/tests/test_vector_delete_api.py`
- Modify: `ai-module/config.py`
- Modify: `ai-module/server.py`
- Modify: `ai-module/.env.example`

**Interfaces:**
- Consumes: `MilvusVectorStore.delete_ids(table: str, doc_ids: list[int]) -> None`.
- Produces: `POST /api/ai/internal/vectors/delete` with JSON `{"table": str, "ids": list[int]}` and `X-Internal-Token`; success body `{"deleted_count": int}`.

- [ ] **Step 1: Write failing endpoint tests**

Create tests with `fastapi.testclient.TestClient`, patch `server.MilvusVectorStore`, and verify: correct token calls `delete_ids("tb_hazard_case", [42])`; an incorrect or missing token returns `401`; unknown tables, empty IDs, non-positive IDs, and more than 100 IDs return `400`; a store exception returns sanitized `503` without the original exception text.

```python
def test_vector_delete_calls_store_for_authorized_request(self):
    response = self.client.post(
        "/api/ai/internal/vectors/delete",
        headers={"X-Internal-Token": "test-token"},
        json={"table": "tb_hazard_case", "ids": [42]},
    )
    self.assertEqual(response.status_code, 200)
    self.store.delete_ids.assert_called_once_with("tb_hazard_case", [42])
```

- [ ] **Step 2: Run the new tests and verify red**

Run: `cd ai-module; python -m unittest tests.test_vector_delete_api -v`

Expected: FAIL because the endpoint and `AI_INTERNAL_TOKEN` do not exist.

- [ ] **Step 3: Add minimal validated endpoint**

Read `AI_INTERNAL_TOKEN = os.getenv("AI_INTERNAL_TOKEN", "")` in `config.py`. In `server.py`, add a bounded Pydantic request model, an allowlist of the three table names, constant-time `hmac.compare_digest` token verification, dependency-injectable store construction, and exception translation to `400`, `401`, or sanitized `503`.

```python
class VectorDeleteRequest(BaseModel):
    table: str
    ids: list[int]

@app.post("/api/ai/internal/vectors/delete")
def delete_vectors(payload: VectorDeleteRequest, x_internal_token: str = Header(default="")):
    if not AI_INTERNAL_TOKEN or not hmac.compare_digest(x_internal_token, AI_INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if payload.table not in TABLE_TO_COLLECTION or not 1 <= len(payload.ids) <= 100:
        raise HTTPException(status_code=400, detail="Invalid vector delete request")
    if any(doc_id <= 0 for doc_id in payload.ids):
        raise HTTPException(status_code=400, detail="Invalid vector delete request")
    try:
        MilvusVectorStore().delete_ids(payload.table, payload.ids)
    except Exception:
        raise HTTPException(status_code=503, detail="Vector store unavailable")
    return {"deleted_count": len(payload.ids)}
```

- [ ] **Step 4: Run focused and existing Python tests**

Run: `cd ai-module; python -m unittest tests.test_vector_delete_api tests.test_milvus_store tests.test_milvus_config -v`

Expected: PASS.

- [ ] **Step 5: Commit the Python endpoint**

```powershell
git add -- ai-module/config.py ai-module/server.py ai-module/.env.example ai-module/tests/test_vector_delete_api.py
git commit -m "feat: expose protected Milvus delete endpoint"
```

### Task 2: Durable Outbox Model And State Machine

**Files:**
- Create: `safety-pojo/src/main/java/com/safety/pojo/entity/VectorSyncOutbox.java`
- Create: `safety-service/src/main/java/com/safety/service/mapper/VectorSyncOutboxMapper.java`
- Create: `safety-service/src/main/java/com/safety/service/service/VectorSyncOutboxService.java`
- Create: `safety-service/src/test/java/com/safety/service/service/VectorSyncOutboxServiceTest.java`
- Modify: `ai-module/db/migrate.sql`

**Interfaces:**
- Produces: `enqueueDelete(String sourceTable, Long docId)`, `findClaimable(int limit)`, `boolean claim(Long id)`, `markSucceeded(Long id)`, `markRetry(Long id, int previousRetryCount, String error)`, and `markFailed(Long id, String error)`.
- Produces mapper operations whose updates require the current task state expected by the transition.

- [ ] **Step 1: Write failing state-machine tests**

Use Mockito to assert `enqueueDelete` inserts `operation=DELETE`, `status=PENDING`, `retryCount=0`, and an immediately due `nextRetryTime`; `claim` returns the mapper's conditional-update result; `markRetry` increments the count, truncates error text to 1000 characters, and calculates delays of 30, 60, 120 seconds up to 3600 seconds; success and permanent failure delegate to conditional mapper updates.

```java
@Test
void retryDelayIsCappedAtOneHour() {
    service.markRetry(7L, 20, "milvus unavailable");
    verify(mapper).markRetry(eq(7L), eq(21), any(LocalDateTime.class), eq("milvus unavailable"));
}
```

- [ ] **Step 2: Run the service test and verify red**

Run: `mvn -pl safety-service -am -Dtest=VectorSyncOutboxServiceTest -Dsurefire.failIfNoSpecifiedTests=false test`

Expected: FAIL because the entity, mapper, and service do not exist.

- [ ] **Step 3: Implement the entity, mapper, service, and migration**

Create the entity with `id`, `sourceTable`, `docId`, `operation`, `status`, `retryCount`, `nextRetryTime`, `lockedAt`, `lastError`, `createTime`, and `updateTime`. Use annotated SQL for bounded polling and conditional transitions. Candidate polling must include due `PENDING`/`RETRY` tasks and `PROCESSING` tasks locked more than five minutes ago.

Append an idempotent `CREATE TABLE IF NOT EXISTS tb_vector_sync_outbox` migration with `idx_vector_sync_due(status, next_retry_time)` and `idx_vector_sync_stale(status, locked_at)`.

- [ ] **Step 4: Run the outbox tests**

Run: `mvn -pl safety-service -am -Dtest=VectorSyncOutboxServiceTest -Dsurefire.failIfNoSpecifiedTests=false test`

Expected: PASS.

- [ ] **Step 5: Commit the outbox state machine**

```powershell
git add -- ai-module/db/migrate.sql safety-pojo/src/main/java/com/safety/pojo/entity/VectorSyncOutbox.java safety-service/src/main/java/com/safety/service/mapper/VectorSyncOutboxMapper.java safety-service/src/main/java/com/safety/service/service/VectorSyncOutboxService.java safety-service/src/test/java/com/safety/service/service/VectorSyncOutboxServiceTest.java
git commit -m "feat: add durable vector delete outbox"
```

### Task 3: Transactional Domain Deletion

**Files:**
- Modify: `safety-service/src/main/java/com/safety/service/service/CaseService.java`
- Modify: `safety-service/src/main/java/com/safety/service/service/KnowledgeService.java`
- Modify: `safety-service/src/main/java/com/safety/service/service/RegulationService.java`
- Create: `safety-service/src/test/java/com/safety/service/service/KnowledgeDeleteServiceTest.java`

**Interfaces:**
- Consumes: `VectorSyncOutboxService.enqueueDelete(String sourceTable, Long docId)`.
- Produces: `@Transactional boolean delete(Long id)` on each of the three domain services.

- [ ] **Step 1: Write failing deletion tests**

For each service, mock its domain mapper and the outbox service. Assert an affected-row count of one enqueues the exact source table and returns true; zero returns false without enqueueing; an outbox exception propagates. Reflect on each method to assert `@Transactional` is present, establishing that a real Spring proxy rolls back the prior domain delete if enqueueing fails.

```java
@Test
void caseDeleteEnqueuesMatchingSourceAndId() {
    when(caseMapper.deleteById(42L)).thenReturn(1);
    assertTrue(caseService.delete(42L));
    verify(outboxService).enqueueDelete("tb_hazard_case", 42L);
}
```

- [ ] **Step 2: Run the domain tests and verify red**

Run: `mvn -pl safety-service -am -Dtest=KnowledgeDeleteServiceTest -Dsurefire.failIfNoSpecifiedTests=false test`

Expected: FAIL because the constructors and delete methods do not match the contract.

- [ ] **Step 3: Add minimal transactional delete methods**

Inject `VectorSyncOutboxService` into all three services. Implement delete-by-primary-key, return false when no row was affected, and enqueue the mapped source only after a successful delete. Annotate each method with `@Transactional(rollbackFor = Exception.class)`.

- [ ] **Step 4: Run all safety-service tests**

Run: `mvn -pl safety-service -am test`

Expected: PASS, including existing cache regression tests.

- [ ] **Step 5: Commit domain deletion**

```powershell
git add -- safety-service/src/main/java/com/safety/service/service/CaseService.java safety-service/src/main/java/com/safety/service/service/KnowledgeService.java safety-service/src/main/java/com/safety/service/service/RegulationService.java safety-service/src/test/java/com/safety/service/service/KnowledgeDeleteServiceTest.java
git commit -m "feat: enqueue vector cleanup on knowledge deletion"
```

### Task 4: Delete Controllers And JWT Rules

**Files:**
- Modify: `safety-web/src/main/java/com/safety/web/controller/CaseController.java`
- Modify: `safety-web/src/main/java/com/safety/web/controller/KnowledgeController.java`
- Modify: `safety-web/src/main/java/com/safety/web/controller/RegulationController.java`
- Modify: `safety-web/src/main/java/com/safety/web/config/SecurityConfig.java`
- Create: `safety-web/src/test/java/com/safety/web/controller/KnowledgeDeleteControllerTest.java`
- Create: `safety-web/src/test/java/com/safety/web/config/KnowledgeEndpointSecurityTest.java`

**Interfaces:**
- Consumes: each domain service's `boolean delete(Long id)`.
- Produces: three `DELETE /api/.../{id}` endpoints returning HTTP 200 with `R.ok()` or HTTP 404 with `R.fail(404, ...)`.

- [ ] **Step 1: Write failing controller and security tests**

Direct controller tests assert true produces success and false produces an HTTP 404 response. A focused Spring Security test imports `SecurityConfig`, supplies mocked dependencies, and asserts anonymous `GET /api/case` is not rejected by security while anonymous `DELETE /api/case/1` returns `403`; an authenticated request reaches the controller.

- [ ] **Step 2: Run focused web tests and verify red**

Run: `mvn -pl safety-web -am -Dtest=KnowledgeDeleteControllerTest,KnowledgeEndpointSecurityTest -Dsurefire.failIfNoSpecifiedTests=false test`

Expected: FAIL because delete mappings are missing and current broad path rules permit anonymous deletion.

- [ ] **Step 3: Implement endpoint responses and method-specific security**

Add `@DeleteMapping("/{id:\\d+}")`. Replace broad anonymous resource matchers with:

```java
.requestMatchers(HttpMethod.GET, "/api/case/**", "/api/knowledge/**", "/api/regulation/**").permitAll()
```

Leave all non-GET methods under `.anyRequest().authenticated()`.

- [ ] **Step 4: Run focused and existing web controller tests**

Run: `mvn -pl safety-web -am -Dtest=KnowledgeDeleteControllerTest,KnowledgeEndpointSecurityTest,AiControllerHealthTest -Dsurefire.failIfNoSpecifiedTests=false test`

Expected: PASS.

- [ ] **Step 5: Commit controllers and security**

```powershell
git add -- safety-web/src/main/java/com/safety/web/controller/CaseController.java safety-web/src/main/java/com/safety/web/controller/KnowledgeController.java safety-web/src/main/java/com/safety/web/controller/RegulationController.java safety-web/src/main/java/com/safety/web/config/SecurityConfig.java safety-web/src/test/java/com/safety/web/controller/KnowledgeDeleteControllerTest.java safety-web/src/test/java/com/safety/web/config/KnowledgeEndpointSecurityTest.java
git commit -m "feat: add authenticated knowledge delete APIs"
```

### Task 5: AI Client And Reliable Delivery Worker

**Files:**
- Modify: `safety-web/src/main/java/com/safety/web/service/AiService.java`
- Create: `safety-web/src/main/java/com/safety/web/service/VectorSyncPermanentException.java`
- Create: `safety-web/src/main/java/com/safety/web/service/VectorDeleteOutboxWorker.java`
- Modify: `safety-web/src/main/java/com/safety/web/SafetyApplication.java`
- Modify: `safety-web/src/main/resources/application.yml`
- Modify: `safety-web/src/main/resources/application-local.yml.example`
- Create: `safety-web/src/test/java/com/safety/web/service/AiServiceVectorDeleteTest.java`
- Create: `safety-web/src/test/java/com/safety/web/service/VectorDeleteOutboxWorkerTest.java`

**Interfaces:**
- Consumes: `VectorSyncOutboxService` state transitions and Python's internal endpoint.
- Produces: `AiService.deleteVectors(String sourceTable, List<Long> ids) -> void`.
- Produces: `VectorDeleteOutboxWorker.processPendingDeletes() -> void`, scheduled every 30 seconds.

- [ ] **Step 1: Write failing AI client tests**

Inject a test `RestTemplate`, base URL, and token into `AiService`. Use `MockRestServiceServer` to assert a POST to `/internal/vectors/delete` carries `X-Internal-Token`, JSON table/IDs, and accepts 2xx. Assert HTTP 400/401 throws `VectorSyncPermanentException`, while 5xx and connection failures remain retryable `RestClientException`s.

- [ ] **Step 2: Run the AI client test and verify red**

Run: `mvn -pl safety-web -am -Dtest=AiServiceVectorDeleteTest -Dsurefire.failIfNoSpecifiedTests=false test`

Expected: FAIL because the configurable constructor and delete method do not exist.

- [ ] **Step 3: Implement configurable AI client deletion**

Replace the hard-coded static base URL with constructor-injected `${ai.base-url}` and `${ai.internal-token}` values while retaining a testable package-private constructor. Send `Map.of("table", sourceTable, "ids", ids)` as JSON and classify only 400/401 as permanent.

- [ ] **Step 4: Write failing worker tests**

Mock outbox and AI services. Assert unclaimed tasks are skipped; success calls `markSucceeded`; `VectorSyncPermanentException` calls `markFailed`; `RestClientException` calls `markRetry` with the previous retry count; and one failed task does not prevent later tasks in the batch from being processed.

- [ ] **Step 5: Run the worker test and verify red**

Run: `mvn -pl safety-web -am -Dtest=VectorDeleteOutboxWorkerTest -Dsurefire.failIfNoSpecifiedTests=false test`

Expected: FAIL because the worker does not exist.

- [ ] **Step 6: Implement and schedule the bounded worker**

Enable scheduling on `SafetyApplication`. Add a worker using:

```java
@Scheduled(fixedDelayString = "${vector-sync.delete.poll-delay-ms:30000}")
public void processPendingDeletes() {
    for (VectorSyncOutbox task : outboxService.findClaimable(batchSize)) {
        if (!outboxService.claim(task.getId())) continue;
        try {
            aiService.deleteVectors(task.getSourceTable(), List.of(task.getDocId()));
            outboxService.markSucceeded(task.getId());
        } catch (VectorSyncPermanentException e) {
            outboxService.markFailed(task.getId(), e.getMessage());
        } catch (RuntimeException e) {
            outboxService.markRetry(task.getId(), task.getRetryCount(), e.getClass().getSimpleName());
        }
    }
}
```

Add `ai.base-url`, `ai.internal-token`, `vector-sync.delete.poll-delay-ms`, and `vector-sync.delete.batch-size` properties backed by environment variables. Document safe example values without a real secret.

- [ ] **Step 7: Run worker, AI client, and existing web regression tests**

Run: `mvn -pl safety-web -am test`

Expected: PASS.

- [ ] **Step 8: Commit reliable delivery**

```powershell
git add -- safety-web/src/main/java/com/safety/web/SafetyApplication.java safety-web/src/main/java/com/safety/web/service/AiService.java safety-web/src/main/java/com/safety/web/service/VectorSyncPermanentException.java safety-web/src/main/java/com/safety/web/service/VectorDeleteOutboxWorker.java safety-web/src/main/resources/application.yml safety-web/src/main/resources/application-local.yml.example safety-web/src/test/java/com/safety/web/service/AiServiceVectorDeleteTest.java safety-web/src/test/java/com/safety/web/service/VectorDeleteOutboxWorkerTest.java
git commit -m "feat: retry Milvus vector deletion from outbox"
```

### Task 6: Full Verification And Safe Acceptance

**Files:**
- Modify only files required to correct failures introduced by Tasks 1-5.

**Interfaces:**
- Verifies the complete MySQL delete to durable outbox to Milvus delete path.

- [ ] **Step 1: Run all Python regression tests**

Run: `cd ai-module; python -m unittest discover -s tests -v; python test_server_sse_errors.py; python test_server_upload_validation.py; python test_orchestrator_stream.py`

Expected: all configured unit and regression tests PASS; documented live tests may SKIP when their opt-in environment flag is absent.

- [ ] **Step 2: Run the full Maven reactor**

Run: `mvn test`

Expected: BUILD SUCCESS across all modules.

- [ ] **Step 3: Run static change checks**

Run: `git diff --check; git status --short`

Expected: no whitespace errors; only known user changes and intentional feature files remain.

- [ ] **Step 4: Apply migration and configure the shared token**

Apply only the `CREATE TABLE IF NOT EXISTS tb_vector_sync_outbox` statement to the configured MySQL database. Set the same generated `AI_INTERNAL_TOKEN` in the ignored `ai-module/.env` and Java runtime environment. Do not print or commit the token.

- [ ] **Step 5: Perform non-destructive live checks**

Call the Python internal endpoint with a positive ID that is confirmed absent from the selected collection and verify a 200 response. Verify an incorrect token returns 401. Do not delete any existing production vector during this check.

- [ ] **Step 6: Review feature diff and commit final corrections**

Stage only intentional corrections, then commit if needed:

```powershell
git commit -m "test: verify reliable Milvus delete synchronization"
```

Record test counts, skipped live checks, migration status, and any deployment prerequisite in the final handoff.
