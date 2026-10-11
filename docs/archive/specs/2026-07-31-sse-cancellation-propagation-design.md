> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/ai-assistant-sse-contract.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# SSE Cancellation Propagation Design

## Goal

When a browser closes either Java SSE endpoint, stop the Java-to-Python stream, cancel the Java background task, stop Python pipeline work, close any active upstream model response, and remove temporary upload files.

## Scope

This applies to:

- `POST /api/ai/analyze/stream`
- `POST /api/ai/chat/stream`

Non-streaming endpoints are unchanged.

## Design

Java creates one cancellation state per `SseEmitter`. The state stores the submitted `Future`, a cancellation flag, and a closer for the active `ClientHttpResponse`. `onCompletion`, `onTimeout`, and `onError` all call the same idempotent cancellation operation. The operation closes the upstream response and calls `Future.cancel(true)`. Binding the Future after registration is race-safe: a cancellation that happens first cancels the Future as soon as it is bound.

The Java worker checks the cancellation state before forwarding each event and suppresses completion/error delivery after client cancellation. Normal completion marks the state finished before completing the emitter, so the completion callback does not cancel a successful task.

Python creates a `CancellationToken` for each streaming request. The async streaming adapter runs the existing synchronous orchestrator generator in a worker thread while polling `Request.is_disconnected()`. Disconnecting the request cancels the token. The token is checked between pipeline stages, report/chat token iterations, and Agent tool rounds. Agent model calls register their active `requests.Response` with the token; cancellation closes that response and stops further model output.

Cancellation is silent from the client perspective: Python does not emit an error or synthetic `done` event after a disconnect. Existing error behavior remains an `error` event followed by `done` for genuine pipeline failures.

## Error Handling and Cleanup

- Java ignores exceptions caused by a cancelled stream and never attempts another emitter send.
- Python treats `StreamCancelled` as normal cancellation and suppresses error events.
- Genuine exceptions keep the existing error-plus-done SSE contract.
- Python always deletes the normalized image in the stream generator's `finally` block.
- Token cancellation and response closing are idempotent and tolerate close failures.

## Verification

Focused tests will prove Java callback registration and Future cancellation, Python disconnect cancellation, and cancellation-before-model-call short-circuiting. One Maven module test command and one Python unittest command will be run after implementation.
