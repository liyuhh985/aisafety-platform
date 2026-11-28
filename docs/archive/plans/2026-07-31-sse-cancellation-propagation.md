> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/ai-assistant-sse-contract.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# SSE Cancellation Propagation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete browser-to-model cancellation propagation for both Java SSE endpoints.

**Architecture:** Java owns one cancellation session per `SseEmitter`, binds its submitted Future and active Python response to that session, and uses all three emitter lifecycle callbacks as cancellation triggers. Python adapts synchronous orchestrator generators to an async disconnect-aware stream, then passes a cancellation token through Orchestrator and Agent calls so active model responses can be closed.

**Tech Stack:** Spring Boot 3.3.5, Java 21, `SseEmitter`, `RestTemplate`, FastAPI, `asyncio`, `threading`, and `requests`.

## Global Constraints

- Apply the behavior to both `/api/ai/analyze/stream` and `/api/ai/chat/stream`.
- Preserve genuine-error SSE behavior: `error` followed by `done`.
- Do not emit synthetic error or done events after client cancellation.
- Preserve temporary-image cleanup in Python.
- Do not change non-streaming endpoints.
- Run focused tests once in red-first form and once as the final verification.

---

### Task 1: Add failing cancellation tests

**Files:**
- Create: `safety-web/src/test/java/com/safety/web/service/AiServiceStreamCancellationTest.java`
- Create: `ai-module/test_server_sse_cancellation.py`
- Create: `ai-module/test_agent_cancellation.py`
- Modify: `ai-module/test_server_sse_errors.py`

**Interfaces:**
- The Java test expects `AiService` to accept an injected `ExecutorService` and register timeout/completion/error callbacks on each returned emitter.
- The Python test expects `stream_analysis` to pass a cancellation token to the orchestrator and stop after `Request.is_disconnected()` becomes true.

- [x] **Step 1: Write the Java failing test**

Test a timeout callback on `chatStream`: capture the submitted Future, invoke the registered `ResponseBodyEmitter` timeout callback, and assert `future.cancel(true)`. Also assert normal completion callbacks are registered alongside timeout and error callbacks.

- [x] **Step 2: Write the Python failing test**

Use a request whose `is_disconnected()` returns false once and true on the next poll. Use an orchestrator generator that yields one event and then waits until its received token is cancelled. Assert the stream contains only the first event and the token was cancelled.

- [x] **Step 3: Update the existing error fake signature**

Allow `FailingOrchestrator.analyze_stream(..., cancellation=None)` so the error-contract test remains valid when the production stream passes the token.

- [x] **Step 4: Run the focused tests and confirm expected failure**

Run:

```powershell
mvn -pl safety-web -am -Dtest=AiServiceStreamCancellationTest test
python -m unittest ai-module.test_server_sse_cancellation ai-module.test_server_sse_errors
```

Expected and observed: Python failed because the stream did not pass/cancel a token. Java could not start because this workspace has no Maven executable or wrapper.

---

### Task 2: Make Java SSE lifecycle cancellation complete

**Files:**
- Modify: `safety-web/src/main/java/com/safety/web/service/AiService.java`
- Test: `safety-web/src/test/java/com/safety/web/service/AiServiceStreamCancellationTest.java`

**Interfaces:**
- Add package-private constructor `AiService(RestTemplate, String, String, ExecutorService)` for deterministic tests; keep the public constructor behavior unchanged.
- Add a private `StreamCancellation` state object with `cancel()`, `setFuture(Future<?>)`, `setUpstreamCloser(Runnable)`, `clearUpstreamCloser()`, `isCancelled()`, `finish()`, and `isFinished()`.
- Route both stream methods through one helper that registers `onCompletion`, `onTimeout`, and `onError` before submitting the task.

- [x] **Step 1: Implement the minimal cancellation state**

Use atomic state and an atomic Future/closer reference. `cancel()` must be idempotent, close the active response, and cancel an already-bound Future; `setFuture()` must immediately cancel when cancellation won the race.

- [x] **Step 2: Route analyze and chat stream execution through the state**

Save the `Future<?>` returned by `streamExecutor.submit`, register all emitter callbacks, keep the response closer bound while reading, check `isCancelled()` before send, and mark normal completion before `emitter.complete()`.

- [ ] **Step 3: Run the Java focused test once for green**

Run:

```powershell
mvn -pl safety-web -am -Dtest=AiServiceStreamCancellationTest test
```

Blocked by the missing Maven executable; the Java test was not run.

---

### Task 3: Add Python cancellation token and propagate it through model calls

**Files:**
- Create: `ai-module/core/cancellation.py`
- Modify: `ai-module/core/agent.py`
- Modify: `ai-module/core/orchestrator.py`
- Test: `ai-module/test_server_sse_cancellation.py`

**Interfaces:**
- `CancellationToken.is_cancelled() -> bool`, `cancel() -> None`, `register(closer) -> None`, `unregister(closer) -> None`, and `throw_if_cancelled() -> None`.
- `Agent.run(..., cancellation=None)`, `Agent.run_stream(..., cancellation=None)`, `_call_llm(..., cancellation=None)`, and `_call_llm_stream(..., cancellation=None)` preserve existing callers through the default.
- `Orchestrator.analyze_stream(..., cancellation=None)` and `Orchestrator.chat_stream(..., cancellation=None)` preserve existing callers through the default.

- [x] **Step 1: Implement the token and cancellation exception**

Use `threading.Event` plus a lock-protected closer set. Cancellation sets the event and invokes each closer once; registering after cancellation closes immediately.

- [x] **Step 2: Propagate token checks through Agent and Orchestrator**

Check before each stage, tool round, and output token. Register active model `Response.close` callbacks around `requests.post`, unregister them in `finally`, and raise `StreamCancelled` instead of yielding an error after cancellation.

- [x] **Step 3: Defer execution verification until the server adapter is connected**

The Task 1 red run already proves the new contract is missing. Do not rerun the same Python cancellation test between token propagation and adapter wiring; run it once in the consolidated final verification after Task 4.

---

### Task 4: Make both FastAPI SSE adapters disconnect-aware

**Files:**
- Modify: `ai-module/server.py`
- Modify: `ai-module/test_server_sse_errors.py`
- Test: `ai-module/test_server_sse_cancellation.py`

**Interfaces:**
- Add an async disconnect-aware adapter that accepts a request and a synchronous generator factory, runs production work in a worker thread, and yields SSE frames from an asyncio queue.
- Add `stream_chat(request, orch, message, session_id)` matching `stream_analysis` cancellation and cleanup behavior.

- [x] **Step 1: Implement the async adapter**

Poll `Request.is_disconnected()` while the worker runs. On disconnect or ASGI cancellation, call `token.cancel()`, stop forwarding queued events, and suppress cancellation errors. For genuine exceptions, preserve `error` then `done`.

- [x] **Step 2: Connect analyze and chat endpoints**

Pass the token into both orchestrator generators, make `/chat/stream` accept `Request`, and keep image deletion in `stream_analysis`'s `finally` block.

- [x] **Step 3: Run the single final verification**

Run:

```powershell
mvn -pl safety-web -am -Dtest=AiServiceStreamCancellationTest test
python -m unittest ai-module.test_server_sse_cancellation ai-module.test_server_sse_errors ai-module.test_orchestrator_stream
```

Observed: Python focused tests PASS (`Ran 5 tests ... OK`). Java focused test was not run because Maven is unavailable.

---

### Task 5: Review the diff and record completion

**Files:**
- Review: all files changed by Tasks 1-4
- Modify: `docs/superpowers/plans/2026-07-31-sse-cancellation-propagation.md`

- [x] **Step 1: Inspect the diff for scope and callback races**

Confirm only the two SSE endpoints and their cancellation dependencies changed, and confirm normal completion cannot invoke cancellation before the worker releases its response.

- [x] **Step 2: Mark completed checklist items and summarize verification**

Record the final focused commands and result in the plan document without adding unrelated refactors or tests.

### Task 6: Bound SSE admission under load

**Files:**
- Modify: `safety-web/src/main/java/com/safety/web/service/AiService.java`
- Create: `safety-web/src/main/java/com/safety/web/service/AiStreamBusyException.java`
- Modify: `safety-web/src/main/java/com/safety/web/controller/AiController.java`
- Modify: `safety-web/src/main/java/com/safety/web/config/GlobalExceptionHandler.java`
- Test: `safety-web/src/test/java/com/safety/web/service/AiServiceStreamCapacityTest.java`
- Test: `safety-web/src/test/java/com/safety/web/controller/AiControllerStreamCapacityTest.java`

- [x] Replace the unbounded fixed-thread-pool queue with 8 worker threads, an `ArrayBlockingQueue(32)`, and `AbortPolicy`.
- [x] Convert `RejectedExecutionException` into `AiStreamBusyException` for both SSE endpoints.
- [x] Return HTTP 429 with `当前服务繁忙，请稍后重试` through the global exception handler.
- [ ] Run Java capacity tests; blocked because Maven and Maven Wrapper are unavailable in the workspace.
