> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/ai-assistant-sse-contract.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# Assistant SSE Interrupt Contract

## Goal

Define the one new SSE event the assistant emits after the orchestration change, so the front-end can render the "create a hazard task?" confirmation as an actual decision instead of a plain sentence.

## What changed on the wire

`POST /api/ai/assistant/stream` previously ended a report turn with the invitation sentence inside the report body. Now the report body never contains it, and the turn ends with a durable interrupt.

Events are unchanged except for one addition:

| type | content | notes |
|---|---|---|
| `status` | string | unchanged; progress text |
| `taxonomy` | `{selected_major_code, major_mismatch, issues[]}` | unchanged |
| `chunk` | string | unchanged; report tokens, answers, and the confirmation question |
| `interrupt` | `{type, question, issues?}` | **new** |
| `done` | `""` | unchanged; end of turn |
| `error` | string | unchanged |

## The new event

```json
{"type": "interrupt",
 "content": {"type": "confirm_create_task",
             "question": "需要我帮你在系统建一条隐患任务吗？",
             "issues": [{"major_code": "fire", "subcategory_code": "fire_equipment_fault"}]}}
```

`type` is either `confirm_create_task` or `ask_address`. `ask_address` is sent when the user already agreed but no usable address was found; the question then asks for the address.

## Ordering and duplication

On that turn the front-end receives, in order:

1. `chunk` - the report body (streamed token by token, never contains the invitation),
2. `chunk` - the confirmation question, prefixed with a blank line,
3. `interrupt` - the structured payload,
4. `done`.

The question is therefore present in both a `chunk` and the `interrupt`. This is deliberate: today's front-end renders the `chunk`, and the message also needs to be stored as the assistant's reply in session history. A front-end that renders confirm/reject buttons from `interrupt` should render the confirmation question from the `interrupt` payload (not the `chunk`) so the text is not shown twice - for example by treating the `chunk` immediately preceding an `interrupt` as the same message.

## What the front-end must send back

The interrupt is resolved by the **next** request in the same `session_id`:

- the user's plain message is enough (`{"message": "好的", "session_id": "...", "user_id": 1}`);
- the server detects that the thread is parked on the gate and resumes it, classifying the reply as confirm / decline / other;
- `user_id` must be present, otherwise no task can be created;
- if the reply is neither confirm nor decline, the graph treats it as a new turn and re-enters understanding, so a topic change mid-confirmation works without the front-end doing anything special.

No new request field is required. If the front-end offers confirm/reject buttons, sending `好的` / `不用了` as the next `message` is sufficient.

## Not required

- No client-side state machine for "did we ask?". The server owns it (the LangGraph thread is parked on `task_gate`).
- No change to the `taxonomy` flow or `selected_major_code` hint.
