> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# LangGraph-Native Orchestration Design

## Goal

Make the assistant graph actually use LangGraph, instead of using it as a streaming wrapper around a linear if-else chain.

`understand` stays the semantic entry point. What changes is how state is held across turns, how retrieval is fanned out, how the "create a task?" confirmation is executed, and how much obsolete fallback code remains.

## Position

A vertical city-safety hazard assistant. The graph is the orchestration core, so every LangGraph capability used must have a reason a reviewer can verify in the code.

## What the current graph actually is

`ai-module/core/assistant_graph.py:873` builds:

```text
        set_entry_point("understand")

understand -> scope_guard -> route -> route_decider
                                        |-> direct_reply  -> END
                                        |-> search -> report -> END
                                        |-> meta_clarify  -> END
                                        |-> clarify       -> END
```

Eight nodes, exactly one conditional edge, every other edge unconditional. `clarify` and `meta_clarify` are single-question terminals. `search -> report` is a fixed two-hop.

LangGraph's documented value is durable execution, `interrupt`, time travel, and converging parallel paths ([choosing-apis](https://docs.langchain.com/oss/python/langgraph/choosing-apis)). None of the four is used. The graph's only real contribution today is node-level `updates` streaming (the status line) and `get_stream_writer` (report tokens).

## Verified gaps

### G1 - The checkpointer is write-only

`run_stream_events` rebuilds a full `initial` state every turn (`ai-module/core/assistant_graph.py:983`) and passes `categories: []`, `category_slots: {}`, `missing: []`, `issues: []`, `pending_categories: []`, then calls `app.stream(initial, config, ...)` (`:1027`).

Input keys are applied as a state update, so explicit values overwrite whatever the checkpoint held. Verified with a minimal graph:

```text
turn1: {'messages': ['u1'], 'categories': ['fire'], 'slots': {'loc': 'x'}}
turn2 (input passes empty categories): {'messages': ['u1','u2'], 'categories': [], 'slots': {}}
```

`InMemorySaver` therefore accumulates state nobody reads back. Cross-turn facts survive only because `understand` re-derives them from `messages` every turn. `WorkingMemory` holds messages, the planner re-extracts structure, and the checkpoint holds a third unread copy.

### G2 - Semantic decisions are implemented as string matching

- `direct_reply` (`:603`) splits the model answer on `[。！!？]` and drops any sentence containing `吗 / 请 / 方便 / 什么 / 哪 / 怎么 / 是否`, to stop a question leaking into the answer.
- `can_offer_task_creation` (`:796`) decides the task invitation; `report` (`:806`) then checks `"建一条隐患任务" not in draft` and appends a hard-coded sentence.
- `_asked_to_create` (`:933`) answers "did we already invite the user?" by substring search for that same sentence.
- `_is_confirmation` (`:912`) answers "did the user agree?" with a `_CONFIRM_WORDS` keyword table.
- `dialogue_policy._answering_previous_question` answers "did the user just answer our question?" with `"？" in content`.

None of these is a model capability limit. Each converts a semantic decision into a Chinese keyword table. That conversion is the mechanical feel: wording present in the table works, everything else silently takes the wrong branch.

### G3 - Retrieval is strictly sequential

`search` (`:758`) loops categories and calls `search_regulation` then `search_cases` per category. Two hazards means four serial tool calls.

Concurrency is safe: `tools/hybrid_search.py` opens a fresh `pymysql` connection per call (`:75`) and uses `requests.post` per embedding call (`:326`) with no shared session; `server.py:301` runs a single uvicorn worker.

### G4 - New and old paths coexist inside one function

`route` (`:372-580`) is about 210 lines performing category inference, merge, relocation, negation, pending-relationship handling, slot extraction, missing recomputation, policy evaluation, and routing. When `plan_ok` is true it follows the planner; when false it runs `_infer_categories`, `_llm_extract_slots`, `_relocate`, `_find_negated`, `_merge_categories`, and the whole `pending_categories` machinery. `route_decider` (`:581`) reads `next_action` first, then falls back to `clarify_count` / `clarify_stopped` / `pending_categories` from the older design.

### G5 - `_detect_direct_mode` short-circuits the planner

`understand` (`:296`) returns early when `_detect_direct_mode` yields `quick_judgment`, leaving `dialogue_plan: {}` so the planner never runs. A query such as "楼下消防栓坏了算隐患吗" contains both `算` and `消火栓`, so it takes this path and gets a generic no-retrieval answer from `direct_reply`'s fallback branch - a plausible cause of "only a short simple answer" reports. The planner already exposes `intent == "quick_assessment"` and `dialogue_policy` already handles it, so the pre-LLM keyword gate is redundant.

## Design

Four changes. Each is independently deployable and independently testable.

Order and rationale: **C2 -> C4 -> C1 -> C3**. C1 must follow C4. Passing persisted `categories` into the existing `route` would activate the `pending_categories` / `meta_clarify` branch (today `old_cats` is always empty so that branch is dead), producing a cross-round "same place or separate?" question that C4 deletes anyway. C3 depends on C1 for durable state.

### C2 - Parallel retrieval with `Send`

Split `search` into a barrier node and a worker node:

```python
def search(state) -> dict:
    """Barrier: reset the categories being searched, then fan out."""
    return {"category_results": {c: None for c in (state.get("categories") or [])}}

def plan_retrieval(state) -> list[Send]:
    sends = []
    for category in state.get("categories") or []:
        keyword = _pick_keyword(category, (state.get("category_slots") or {}).get(category, {}))
        for tool in ("search_regulation", "search_cases"):
            sends.append(Send("retrieve", {
                "category": category, "tool": tool, "keyword": keyword,
            }))
    return sends

def retrieve(state) -> dict:
    field = _RESULT_FIELD[state["tool"]]
    return {"category_results": {
        state["category"]: {field: _run_tool(state["tool"], state["keyword"])}
    }}
```

`category_results` needs a reducer, because concurrent branches each return a partial dict:

```python
def merge_category_results(left, right) -> dict:
    merged = {k: dict(v) for k, v in (left or {}).items()}
    for category, value in (right or {}).items():
        if value is None:
            merged[category] = {}
        else:
            merged.setdefault(category, {})
            merged[category].update(value or {})
    return merged
```

Edges: `search` becomes a conditional-edge source returning `plan_retrieval`'s `Send` list; `retrieve -> report` converges after all branches finish.

### C4 - `understand` is the only writer; delete the old path

`understand` becomes solely responsible for facts and for the policy decision, in this order:

1. run the planner; normalize to canonical subcategory codes;
2. merge persisted per-category slots into the planner result (incremental, does not restart from scratch);
3. recompute `missing` deterministically from the merged slots (`critical` slots only), so it cannot contradict the slots;
4. `categories` = ordered, de-duplicated `issues[].subcategory_code`;
5. `next_action` = `decide_next_action(plan, {...})`;
6. set `asked_question_last_turn = bool(clarification_question)`.

`route` shrinks to a pure mapping, using `Command(goto=...)`:

```python
def route(state) -> Command[Literal["direct_reply", "search"]]:
    if state.get("next_action") in {"report_full", "report_preliminary"}:
        return Command(goto="search")
    return Command(goto="direct_reply")
```

Deleted nodes and helpers: `clarify`, `meta_clarify`, `_llm_phrase`, `_infer_categories`, `_score_category`, `_find_negated`, `_merge_categories`, `_is_separate_answer`, `_is_same_place_answer`, `_detect_other_cats`, `_relocate`, `_llm_extract_slots`, `_llm_classify`, `_join_text`, `_SAME_PLACE_WORDS`, `_SEPARATE_WORDS`, `_CATEGORY_KEYWORDS`, `_sort_by_priority`, `_dedupe`.

Deleted state keys: `pending_categories`, `relationship`, `category_index`, `active_category`, `clarify_count`, `clarify_stopped`, `route_decision`.

Also deleted: `_detect_direct_mode`'s `quick_judgment` short-circuit (G5), `direct_reply`'s sentence-stripping regex (G2), `dialogue_policy._answering_previous_question` (replaced by `asked_question_last_turn`), and `dialogue_policy`'s `meta_clarify` action.

Kept deliberately: `STOP_PHRASES` and `REPORT_PHRASES`. Those are explicit user *instructions* ("直接出报告"), not semantic classification, so keyword matching is the right tool there.

Fallback when the planner fails: `understand` returns `next_action = "answer_now"` with empty `issues`; `direct_reply` asks for a concrete description. No re-entry into the old slot-extraction path.

### C1 - The checkpointer is the single source of truth

`AssistantState` gains reducers:

```python
class AssistantState(TypedDict, total=False):
    messages: Annotated[list, append_messages]
    category_results: Annotated[dict, merge_category_results]
    ...
```

```python
MAX_THREAD_MESSAGES = 20

def append_messages(left, right) -> list:
    return add_messages(left or [], right or [])[-MAX_THREAD_MESSAGES:]
```

`run_stream_events` no longer resets structured state. It sends only the new turn:

```python
initial = {
    "session_id": session_id,
    "messages": [HumanMessage(content=message)],
    "vision_summary": vision_summary,
    "selected_major_code": selected_major_code,
}
```

Message history is seeded from `WorkingMemory` **only when the checkpoint has no messages yet** (process restart, or a session created before a deploy). This keeps `WorkingMemory` as the history API for `/api/ai/history` without duplicating it into the graph on every turn:

```python
seed = [] if app.get_state(config).values.get("messages") else _history_messages(history)
```

A new entry node `begin_turn` resets per-turn flags and is entered only from `START`. `task_gate` re-entry reaches `understand` directly, bypassing `begin_turn`.

Checkpointer moves from `InMemorySaver` to `SqliteSaver` at `ai-module/data/checkpoints.db`, so threads survive a restart and `interrupt` state is durable.

### C3 - Task confirmation via `interrupt`

`report` stops appending any invitation sentence. It sets `offer_task` from `can_offer_task_creation`. A conditional edge after `report` routes to `task_gate` when `offer_task and not task_offered`.

```python
def task_gate(state) -> Command[Literal["submit_task", "close_task", "understand"]]:
    answer = interrupt({
        "type": "confirm_create_task",
        "question": "需要我帮你在系统建一条隐患任务吗？",
        "issues": state.get("issues") or [],
    })
    decision = str((answer or {}).get("decision") or "other")
    if decision == "confirm":
        return Command(goto="submit_task", update={"task_offered": True})
    if decision == "decline":
        return Command(goto="close_task", update={"task_offered": True})
    return Command(goto="understand", update={"task_offered": True})
```

Verified on this project's bridge (`stream_mode=["updates", "custom"]`, sync `app.stream` inside `asyncio.to_thread`):

- the interrupt surfaces as `{"__interrupt__": (Interrupt(value={...}),)}` in the `updates` stream;
- `app.get_state(config).next == ("task_gate",)` is the "we already asked" flag, replacing `_asked_to_create`;
- resuming works with one call that both answers the gate and carries the new user message: `Command(resume={"decision": ...}, update={"messages": [HumanMessage(message)]})`.

The bridge checks `next` first:

```python
pending = app.get_state(config).next
if pending == ("task_gate",):
    payload = Command(resume={"decision": classify(message)}, update={"messages": [HumanMessage(message)]})
else:
    payload = initial
```

`classify` returns `confirm` / `decline` / `other`. Deterministic yes/no words first, planner fallback otherwise. `other` sends the graph back through `understand`, which is why `task_gate` needs a `goto` to a non-entry node.

`submit_task` calls `tools/hazard_submit.submit_from_history` using the message history held in graph state and the latest human message as `latest`; `_PENDING_ADDRESS` is deleted. A missing address is handled by the same node rather than a global dict: `submit_task` sets `task_phase = "address"` and returns `Command(goto="task_gate")`; `task_gate` chooses its interrupt payload from `task_phase`, stores the resumed free-text answer as `address_text`, and returns to `submit_task`.

SSE contract addition (front-end work owned by another model): a new `interrupt` event carrying `{"type": "confirm_create_task", "question": ...}`. The `chunk` / `status` / `taxonomy` / `done` / `error` events are unchanged.

## Final graph

```text
START -> begin_turn -> understand -> scope_guard -> route
                                                      |-> direct_reply -> END
                                                      `-> search =(Send)=> retrieve -> report -> after_report
                                                                                                    |-> task_gate -|-> submit_task -> END
                                                                                                    |              |-> close_task  -> END
                                                                                                    |              `-> understand
                                                                                                    `-> END
```

The graph now has: a fan-out with a join (`Send`), a cycle (`task_gate -> understand`), a durable human-in-the-loop pause (`interrupt`), cross-turn state with reducers (C1), and dynamic routing (`Command`).

## Out of scope

- Java backend. No change; `submit_from_history` and its HTTP contract stay as they are.
- Front-end. Only the contract note above is handed to the front-end model.
- Postgres or Redis checkpointer. `SqliteSaver` is enough for this project.
- Multi-agent supervisor. The official docs note a single agent with the right tools and prompt usually matches a multi-agent setup.
- The `/api/ai/analyze` `Orchestrator` path and `assistant_agent.py` / `get_assistant()`: still unreferenced by the main chain, but removing them needs a traffic check, so it stays a separate follow-up.

## Latency

Current turn cost is roughly 1 minute, dominated by serial retrieval plus several serial LLM calls. C2 removes the serial retrieval term (2N calls become 2 waves), C4 removes the extra planner-bypassing calls and the redundant extraction, C1 removes the per-turn re-extraction. The graph should get faster, not slower.

## Verification

- Unit: reducer merge semantics, `Send` fan-out shape, `route` mapping, policy actions, slot-merge determinism, `classify`.
- Graph-level: two-turn run over the real compiled graph asserting that structured state persists (the G1 probe as a permanent test).
- Graph-level: interrupt round trip - turn 1 pauses at `task_gate` with `next == ("task_gate",)`, turn 2 with `Command(resume=...)` reaches `submit_task`.
- Regression: existing `ai-module/tests/` suite, excluding the two known pre-existing failures (`test_hazard_flow.py::test_report_writes_custom_chunks` after the 2026-09-25 rename, `tests/test_vector_delete_api.py`).
- Live: SSE smoke on port 8000 plus one manual pass through the four flows (quick judgment, full report, task creation, out of scope).


## Deviations from this design (as built)

Recorded after implementation, so the doc matches the code.

1. **Checkpointer stays `InMemorySaver`; no `SqliteSaver`.** `langgraph-checkpoint-sqlite` is not installed, and it would add a runtime dependency at deploy time. It also would not change the failure mode: `WorkingMemory` (the history source used by `/api/ai/history`) is in-process too, and the service runs a single uvicorn worker (`server.py:301`). Reducers, one-source-of-truth state, and incremental slot merge - the parts that fix real defects - do not need disk. Adding a durable checkpointer is a follow-up only if the service becomes multi-worker.

2. **The gate emits both a `chunk` and an `interrupt` event.** The question text is emitted as a `chunk` first (what today's front-end renders, and what lands in `WorkingMemory` as the assistant reply) and then as a structured `interrupt` event carrying `{"type", "question", "issues"}`. Emitting only the structured event would leave the current front-end showing an empty reply. Contract for the front-end model: `docs/superpowers/specs/2026-09-25-assistant-sse-interrupt-contract.md`.

3. **`classify_task_reply` uses exact or prefix matching, never substring matching.** An earlier version used `in text`, which classified "我要投诉物业" as consent to create a task because it contains "要". Decline markers are checked first.

4. **`_plan_issues` was added as a deterministic fallback.** `understand` reads `plan["issues"]`. If a planner ever returns the older `categories` / `category_slots` shape, the issues are rebuilt from it rather than collapsing to "no hazard found".

5. **`_detect_direct_mode` keeps the greeting set but drops the `quick_judgment` branch entirely.** G5 is fixed by removing the pre-LLM short-circuit, not by tuning its keywords.

6. **`_drop_question_sentences` moved into `dialogue_understanding.parse_plan`.** "An answer must not carry a question when a `question` field exists" is now enforced once at the boundary where model output enters the system, instead of inside `direct_reply`'s presentation code.

7. **`Orchestrator` and `/api/ai/analyze` are untouched.** Their traffic is still unverified, so they remain a separate follow-up. `core/assistant_agent.py` and `get_assistant()` were deleted: the object was constructed on every request (`server.py:216`) and never used.

## Measured result

Live SSE smoke on the deployed service (single turn, two hazards, full report with real retrieval): **9 seconds**, down from roughly 60 seconds. Only one task invitation appears in the stream. `retrieve` now runs 4 branches concurrently for 2 hazards (`tests/test_parallel_retrieval.py::test_retrieval_branches_run_concurrently` asserts 4 x 0.3s of work completes in about 0.3s).

## Follow-up round 2026-09-25 (later): household boundary + one architecture

### 户内 / 公共边界 — one field, two sentences

Decision: do **not** add a scope dimension to the pipeline. Add one attribute and use it in exactly two places.

- The planner returns `premises_scope`: `public` (default) | `indoor` | `indoor_risk`. It is a *per-hazard* judgement from the description, not a property of the subcategory - the same `gas_leak` is `indoor_risk` for "我家厨房的燃气管道漏气" and `public` for "小区里的燃气管道老化漏气了". Verified live for both. (Named `premises_scope`, not `scope`, because the planner contract already uses `scope` for `hazard|emergency|smalltalk|ambiguous|out_of_scope`.)
- It does **exactly two things**: `understand` prepends one explanatory sentence when the scope first appears or changes (never repeated per turn), and the task invitation carries a reminder via `task_invitation_question`.
- It does **not** block the flow, change the classification, or refuse anything. `issues` are untouched.
- Exposed in the `taxonomy` event as `premises_scope`.

### One architecture: the `Orchestrator` path is gone

The four legacy URLs (`/api/ai/analyze`, `/api/ai/analyze/stream`, `/api/ai/chat`, `/api/ai/chat/stream`) now run **the same assistant graph**; they only map event names back to the old contract (`chunk` -> `report`, plus `status`/`error`/`done` pass-through, and the `vision` / `no_hazard` prelude before the graph).

Deleted: `core/orchestrator.py`, `agents/` (5 files), `main.py`, and the four standalone scripts that were written against the removed class. `core/__init__.py` no longer exports `Orchestrator`, so any straggler import fails loudly instead of silently keeping a second path alive.

Kept alive deliberately: `eval_rag.py` used `Orchestrator._build_report_context` and the report agent. That prompt builder moved to `core/report_context.py` (a pure module), and the report agent is constructed locally, so the retrieval/report evaluation harness still runs. `tests/test_report_context.py` was retargeted at the pure module.

Verified live after deploy: `/api/ai/analyze` returns `{session_id, vision, report}`, `/api/ai/analyze/stream` emits `status`/`report`/`done`, `/api/ai/chat` returns `{session_id, reply}`.

One deliberate difference from the assistant endpoint: the compat endpoints pass `cancellation=None`, matching their previous behaviour (they never propagated a cancel token; they only stopped consuming on disconnect). The assistant endpoint still propagates it properly.
