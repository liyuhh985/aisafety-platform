# Milvus Delete Synchronization Design

## Goal

Deleting a case, policy knowledge record, or regulation from MySQL must enqueue
deletion of the vector with the same ID from the corresponding Milvus collection.
The MySQL deletion must remain available when Milvus is temporarily unavailable,
and pending cleanup must survive application restarts.

## Scope

- Add authenticated delete endpoints for cases, policy knowledge, and regulations.
- Delete the MySQL row and create a durable vector-delete task atomically.
- Process pending tasks in the background with retry and crash recovery.
- Add an internal Python endpoint that deletes Milvus vectors by source table and ID.
- Preserve the existing full and incremental vector synchronization behavior.

This change does not add create or update APIs, change embedding generation, or
rebuild any collection when one record is deleted.

## Collection Mapping

The existing mapping remains authoritative:

| MySQL table | Milvus collection |
| --- | --- |
| `tb_hazard_case` | `hazard_cases` |
| `tb_hazard_knowledge` | `hazard_policies` |
| `tb_regulation` | `hazard_regulations` |

The MySQL primary key is stored as the Milvus `doc_id` primary key. Deleting one
record therefore requires only a Milvus primary-key deletion and never requires
re-embedding the other records.

## HTTP API

The Java application adds these endpoints:

```text
DELETE /api/case/{id}
DELETE /api/knowledge/{id}
DELETE /api/regulation/{id}
```

A successful response means the MySQL record was deleted and a durable cleanup
task was committed. It does not wait for Milvus. A missing record returns `404`
and does not create a task.

Only `GET` requests under these three resource paths remain anonymous. Delete
requests require a valid JWT. The project currently has no administrator role, so
authorization is limited to authenticated users in this scope.

The Python AI service adds an internal JSON endpoint:

```text
POST /api/ai/internal/vectors/delete
X-Internal-Token: <shared secret>

{"table": "tb_hazard_case", "ids": [42]}
```

The endpoint accepts only the three allowlisted table names, requires a non-empty
ID list of bounded size, and calls the existing `MilvusVectorStore.delete_ids()`.
Deleting an ID that is already absent is successful, which makes retries
idempotent. Invalid input returns `400`, an invalid internal token returns `401`,
and a Milvus failure returns `503` without exposing credentials or internal error
details.

## Transactional Outbox

Migration SQL adds `tb_vector_sync_outbox` with these logical fields:

| Field | Purpose |
| --- | --- |
| `id` | Outbox primary key |
| `source_table` | One of the three allowlisted MySQL tables |
| `doc_id` | Deleted business-record ID |
| `operation` | `DELETE`; retained for explicit event semantics |
| `status` | `PENDING`, `PROCESSING`, `RETRY`, `SUCCEEDED`, or `FAILED` |
| `retry_count` | Number of failed delivery attempts |
| `next_retry_time` | Earliest time a retry may be claimed |
| `locked_at` | Time at which a worker claimed the task |
| `last_error` | Sanitized and length-limited failure summary |
| `create_time` | Creation timestamp |
| `update_time` | Last state-change timestamp |

Indexes cover due-task polling and stale-lock recovery. Each deletion event gets
its own row; there is no permanent uniqueness constraint on source table and
document ID because an ID may be restored and deleted again later.

Each domain service exposes a transactional delete method. It first verifies the
record exists, then deletes the business row and inserts a `PENDING` outbox row in
the same MySQL transaction. If either SQL operation fails, both operations roll
back.

## Background Processing

A scheduled worker in the Java web application runs every 30 seconds. It reads a
bounded batch of due `PENDING` or `RETRY` task IDs and claims each task with a
conditional update to `PROCESSING`. This conditional claim lets multiple
application instances run without processing the same task concurrently.

For each claimed task, the worker calls the Python internal endpoint through
`AiService`. On a successful response it marks the task `SUCCEEDED`. On failure it
increments `retry_count`, records a sanitized error class or message, calculates
the next attempt, and returns retryable failures to `RETRY`. A non-retryable
validation or authentication failure is marked `FAILED` for operator inspection
instead of being retried forever.

Retry delay increases exponentially and is capped at one hour. Retries do not have
a fixed attempt limit, so temporary Milvus or network outages cannot permanently
strand a vector. A `PROCESSING` task whose `locked_at` is older than five minutes
is eligible for reclamation after a worker crash.

Completed rows are retained for audit in this scope. Automatic history cleanup can
be added separately if task volume later warrants it.

## Configuration And Security

The Java application makes the existing AI base URL configurable and adds an
internal token property backed by environment variables:

```text
AI_BASE_URL=http://127.0.0.1:8000/api/ai
AI_INTERNAL_TOKEN=<high-entropy shared secret>
```

The Python service reads the same `AI_INTERNAL_TOKEN`. The internal endpoint fails
closed when the token is missing and compares supplied credentials using a
constant-time comparison. The secret is documented in example environment files
but its value is never committed or logged.

The Python service should remain reachable only from the Java host or a private
network. The token is defense in depth and does not justify publicly exposing port
8000.

## Error Semantics

- Missing MySQL record: return `404`; create no outbox task.
- MySQL delete or outbox insert failure: roll back the whole local transaction.
- Milvus unavailable or Python request failure: keep MySQL deletion committed and
  schedule a retry.
- Vector already absent: treat as successful deletion.
- Invalid outbox source table or rejected internal credentials: mark the task
  `FAILED` with a sanitized validation error because retries cannot repair it.
- Java or Python restart: pending tasks remain in MySQL and resume automatically.

Because MySQL and Milvus do not share a distributed transaction, a short interval
may exist in which Milvus still contains a deleted ID. Retrieval already hydrates
Milvus hits from MySQL, so a deleted record cannot produce full source content;
the worker then removes the stale vector.

## Testing

Python tests cover:

- Valid table and IDs call `delete_ids()` with the exact values.
- All three table-to-collection mappings are honored.
- Missing or incorrect internal tokens are rejected.
- Unsupported tables, empty lists, oversized lists, and invalid IDs are rejected.
- Milvus failures produce a sanitized `503` response.
- Repeated deletion of an absent vector succeeds.

Java tests cover:

- Each service deletes the expected row and inserts the correctly mapped outbox
  event.
- A missing row returns the not-found result and creates no event.
- The service method has a transaction boundary, including rollback behavior in an
  integration-level test where practical.
- The worker claims due tasks, marks success, schedules retries with capped delay,
  marks permanent failures, and reclaims stale `PROCESSING` tasks.
- Concurrent claim attempts allow only one worker to own a task.
- Anonymous `GET` access remains allowed while anonymous `DELETE` is rejected.
- `AiService` sends the configured internal token and request payload.

The existing AI unit suite, Milvus store tests, Java module tests, and current
SSE/upload regression tests must continue to pass. A live acceptance test may use
a disposable high-numbered ID: insert a temporary MySQL row and vector, call the
Java delete API, wait for the outbox task to succeed, and verify both stores no
longer contain the ID. Existing production knowledge records must not be used for
this destructive verification.

## Acceptance Criteria

- Deleting one record does not recreate a collection or embed unrelated records.
- The matching Milvus `doc_id` is eventually removed from only its mapped
  collection.
- MySQL deletion succeeds while Milvus is offline, and cleanup completes after
  Milvus recovers.
- Pending work survives a Java application restart.
- Duplicate delivery is harmless.
- Existing anonymous read behavior is unchanged, while deletion requires JWT
  authentication.
