> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# LangGraph-Native Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the assistant graph use LangGraph's real capabilities - reducer-backed cross-turn state, `Send` fan-out retrieval, a durable `interrupt` task confirmation, and `Command` routing - replacing the linear chain and the string-matching decisions around it.

**Architecture:** `understand` becomes the single writer of structured facts and the policy decision; `route` shrinks to a `Command(goto=...)` mapping; retrieval fans out with `Send` and converges through a dict reducer; the "create a task?" confirmation becomes `interrupt()` instead of a global dict plus substring matching.

**Tech Stack:** Python 3.11, LangGraph 1.2.11, pytest, FastAPI SSE bridge, existing Milvus/MySQL hybrid retrieval.

## Global Constraints

- Order is C2 -> C4a -> C4b -> C1 -> C3. C1 must not ship before C4a (persisted `categories` would activate the `pending_categories` branch that C4a deletes).
- Spec: `docs/superpowers/specs/2026-09-25-langgraph-native-orchestration-design.md`.
- Do not touch the Java backend or the front-end. Front-end work is owned by another model.
- Keep the SSE events `chunk`, `status`, `taxonomy`, `done`, `error` byte-compatible. C3 adds one new event only.
- Do not remove `STOP_PHRASES` or `REPORT_PHRASES`: those are explicit user instructions, not classification.
- Keep the two known pre-existing failures out of scope: `tests/test_multi_hazard.py::test_report_writes_custom_chunks`, `tests/test_vector_delete_api.py`.
- Do not `git commit` unless asked.
- One question per turn maximum. Never ask a question whose answer is already known from state.
- If a test fails twice for reasons outside the current task, stop and report instead of iterating.

---

### Task 1: Parallel retrieval with `Send`

**Files:**
- Modify: `ai-module/core/langgraph_state.py`
- Modify: `ai-module/core/assistant_graph.py` (`search` at :758, `build_graph` at :873)
- Test: `ai-module/tests/test_parallel_retrieval.py`

**Interfaces:**
- Consumes: `_pick_keyword(category, slots) -> str`, `_run_tool(name, keyword) -> str` (already exist).
- Produces: `merge_category_results(left, right) -> dict`; `plan_retrieval(state) -> list[Send]`; `retrieve(state) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
from langgraph.types import Send

from core.assistant_graph import plan_retrieval, retrieve
from core.langgraph_state import merge_category_results


def test_merge_category_results_deep_merges_partial_branches():
    left = {"fire_equipment_fault": {"regulation": "R1"}}
    right = {"fire_equipment_fault": {"case": "C1"}}
    assert merge_category_results(left, right) == {
        "fire_equipment_fault": {"regulation": "R1", "case": "C1"}
    }


def test_merge_category_results_none_clears_category():
    left = {"fire_equipment_fault": {"regulation": "old", "case": "old"}}
    assert merge_category_results(left, {"fire_equipment_fault": None}) == {
        "fire_equipment_fault": {}
    }


def test_plan_retrieval_fans_out_one_send_per_category_and_tool():
    state = {
        "categories": ["fire_equipment_fault", "road_occupancy"],
        "category_slots": {"fire_equipment_fault": {"facility_type": "消火栓"}},
    }
    sends = plan_retrieval(state)
    assert len(sends) == 4
    assert all(isinstance(send, Send) for send in sends)
    assert {send.node for send in sends} == {"retrieve"}
    assert sorted(send.arg["tool"] for send in sends) == [
        "search_cases", "search_cases", "search_regulation", "search_regulation",
    ]


def test_plan_retrieval_is_empty_without_categories():
    assert plan_retrieval({"categories": []}) == []


def test_retrieve_writes_only_its_own_field(monkeypatch):
    monkeypatch.setattr(
        "core.assistant_graph._run_tool", lambda name, keyword: f"{name}:{keyword}"
    )
    update = retrieve({
        "category": "road_occupancy", "tool": "search_cases", "keyword": "占道",
    })
    assert update == {
        "category_results": {"road_occupancy": {"case": "search_cases:占道"}}
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai-module; python -m pytest tests/test_parallel_retrieval.py -v`
Expected: FAIL - `ImportError: cannot import name 'merge_category_results'`.

- [ ] **Step 3: Write minimal implementation**

In `ai-module/core/langgraph_state.py`:

```python
def merge_category_results(left, right) -> dict:
    """Reducer for concurrent retrieval branches writing partial per-category dicts."""
    merged = {key: dict(value) for key, value in (left or {}).items()}
    for category, value in (right or {}).items():
        if value is None:
            merged[category] = {}
        else:
            merged.setdefault(category, {})
            merged[category].update(value or {})
    return merged
```

In `ai-module/core/assistant_graph.py`, replace the body of `search` and add two functions. Import `Send` from `langgraph.types` and `merge_category_results` from `core.langgraph_state`.

```python
_RESULT_FIELD = {"search_regulation": "regulation", "search_cases": "case"}


def search(state: AssistantState) -> dict:
    """Barrier node: clear the categories about to be re-searched, then fan out."""
    return {"category_results": {cat: None for cat in (state.get("categories") or [])}}


def plan_retrieval(state: AssistantState) -> list[Send]:
    sends = []
    for category in state.get("categories") or []:
        keyword = _pick_keyword(category, (state.get("category_slots") or {}).get(category, {}))
        for tool_name in _RESULT_FIELD:
            sends.append(Send("retrieve", {
                "category": category, "tool": tool_name, "keyword": keyword,
            }))
    return sends


def retrieve(state: AssistantState) -> dict:
    field = _RESULT_FIELD[state["tool"]]
    result = _run_tool(state["tool"], state["keyword"])
    return {"category_results": {state["category"]: {field: result}}}
```

In `build_graph`, declare `category_results` with the reducer on `AssistantState` (done in Task 4 for other keys, but `category_results` is needed now):

```python
from typing import Annotated
class AssistantState(TypedDict, total=False):
    category_results: Annotated[dict, merge_category_results]
```

Wire the edges:

```python
g.add_node("retrieve", retrieve)
g.add_conditional_edges("search", plan_retrieval)
g.add_edge("retrieve", "report")
```

`search` keeps its incoming edge from `route_decider` and no longer needs `report` directly.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ai-module; python -m pytest tests/test_parallel_retrieval.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Verify the join actually happens**

Run: `cd ai-module; python -m pytest tests/test_report_context.py tests/test_multi_hazard.py -v`
Expected: `test_report_context.py` passes. `test_multi_hazard.py::test_report_writes_custom_chunks` may still fail (pre-existing, out of scope).

- [ ] **Step 6: Commit**

```bash
git add ai-module/core/langgraph_state.py ai-module/core/assistant_graph.py ai-module/tests/test_parallel_retrieval.py
git commit -m "perf(retrieval): fan out regulation/case search with Send"
```
---

### Task 2: `understand` is the only writer, `route` becomes a mapping (C4a)

**Files:**
- Modify: `ai-module/core/assistant_graph.py` (`understand` :285, `route` :372-580, `route_decider` :581)
- Modify: `ai-module/core/dialogue_policy.py` (`_answering_previous_question`, `meta_clarify`)
- Modify: `ai-module/core/langgraph_state.py`
- Test: `ai-module/tests/test_thin_route.py`

**Interfaces:**
- Consumes: `dialogue_understanding.understand(messages, vision_summary, selected_major_code) -> dict` (planner plan), `dialogue_policy.decide_next_action(plan, state) -> dict`, `slot_schemas.get_slot_schema(subcategory_code) -> list[Slot]`.
- Produces: `understand(state) -> dict` writing `issues`, `categories`, `category_slots`, `missing`, `next_action`, `clarification_question`, `asked_question_last_turn`, `selected_major_code`, `major_mismatch`; `route(state) -> Command[Literal["direct_reply", "search"]]`.

- [ ] **Step 1: Write the failing test**

```python
from langgraph.types import Command

from core.assistant_graph import route


def test_route_sends_report_actions_to_search():
    assert route({"next_action": "report_full"}).goto == "search"
    assert route({"next_action": "report_preliminary"}).goto == "search"


def test_route_sends_answer_actions_to_direct_reply():
    for action in ("answer_now", "answer_with_optional_question", "ask_critical_question", ""):
        assert route({"next_action": action}).goto == "direct_reply"


def test_route_never_returns_a_clarify_branch():
    assert route({"next_action": "ask_critical_question"}).goto != "clarify"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai-module; python -m pytest tests/test_thin_route.py -v`
Expected: FAIL - `route` currently returns a `dict`, so `.goto` raises `AttributeError`.

- [ ] **Step 3: Rewrite `understand` as the single writer**

Replace `understand`'s tail so it owns facts and the policy decision. The planner call, canonicalization, and `selected_major_code` handling stay as they are.

```python
def understand(state: AssistantState) -> dict:
    user_text = _latest_user_text(state)
    vision_summary = state.get("vision_summary", "")
    selected_major_code = state.get("selected_major_code", "")
    emergency_scope = decide_scope({}, user_text)
    if emergency_scope.get("scope") == "emergency":
        return {
            "direct_mode": "emergency_reply",
            "scope": "emergency",
            "scope_reason": emergency_scope.get("reason", ""),
            "dialogue_plan": {},
            "next_action": "answer_now",
        }
    if _detect_direct_mode(user_text, vision_summary):
        return {"direct_mode": "smalltalk", "dialogue_plan": {}, "next_action": "answer_now"}

    plan = _understand_plan(list(state.get("messages", [])), vision_summary, selected_major_code)
    if not plan or not plan.get("ok"):
        return {
            "dialogue_plan": {},
            "issues": [],
            "categories": [],
            "category_slots": {},
            "missing": [],
            "next_action": "answer_now",
            "clarification_question": "",
            "asked_question_last_turn": False,
        }
    issues = _merge_persisted_slots(plan.get("issues") or [], state.get("category_slots") or {})
    categories = [issue["subcategory_code"] for issue in issues]
    slots = {issue["subcategory_code"]: issue.get("slots") or {} for issue in issues}
    missing = rebuild_missing(categories, slots)
    for issue in issues:
        issue["missing"] = [
            slot.key for slot in get_slot_schema(issue["subcategory_code"])
            if slot.key in missing
        ]
    plan = dict(plan)
    plan["issues"] = issues
    policy = decide_next_action(plan, {**state, "user_text": user_text, "missing": missing})
    action = policy.get("action") or "answer_now"
    report_mode = policy.get("report_mode", "none")
    if missing and report_mode == "full":
        action, report_mode = "report_preliminary", "preliminary"
    question = policy.get("question", "") or ""
    return {
        "dialogue_plan": plan,
        "intent": plan.get("intent", ""),
        "issues": issues,
        "categories": categories,
        "category_slots": slots,
        "missing": missing,
        "selected_major_code": plan.get("selected_major_code", selected_major_code),
        "major_mismatch": bool(plan.get("major_mismatch")),
        "clarification_question": question,
        "optional_question": bool(policy.get("optional_question")),
        "next_action": action,
        "report_mode": report_mode,
        "policy_reason": policy.get("reason", ""),
        "asked_question_last_turn": bool(question),
    }
```

Add the merge helper next to `rebuild_missing`:

```python
def _merge_persisted_slots(issues: list[dict], persisted: dict) -> list[dict]:
    """Fold facts carried in graph state into this turn's planner result."""
    merged = []
    for issue in issues:
        code = issue.get("subcategory_code")
        kept = dict(persisted.get(code) or {})
        kept.update({k: v for k, v in (issue.get("slots") or {}).items() if v})
        issue = dict(issue)
        issue["slots"] = kept
        merged.append(issue)
    return merged
```

- [ ] **Step 4: Replace `route` and delete `route_decider`**

```python
def route(state: AssistantState) -> Command[Literal["direct_reply", "search"]]:
    if state.get("next_action") in {"report_full", "report_preliminary"}:
        return Command(goto="search")
    return Command(goto="direct_reply")
```

In `build_graph`, drop `route_decider` entirely. `route` becomes a plain node that *returns* a `Command`; LangGraph follows `Command.goto` automatically, so `route` needs no conditional edge:

```python
g.add_node("route", route)
g.add_edge("scope_guard", "route")
```

- [ ] **Step 5: Drop the `meta_clarify` policy action**

In `ai-module/core/dialogue_policy.py`: delete the `pending_categories` early return, delete `_answering_previous_question`, and replace its call site:

```python
    if complete and state.get("asked_question_last_turn"):
        return _decision(
            "report_full",
            reason="user answered the clarification and facts are complete",
            needs_search=True,
            report_mode="full",
        )
```

- [ ] **Step 6: Run tests**

Run: `cd ai-module; python -m pytest tests/test_thin_route.py tests/test_dialogue_policy.py tests/test_semantic_dialogue.py -v`
Expected: new file PASS. `test_dialogue_policy.py` and `test_semantic_dialogue.py` need their `meta_clarify` / `pending_categories` expectations updated to the new action set - update them in this task, do not delete the assertions, retarget them.

- [ ] **Step 7: Commit**

```bash
git add ai-module/core/assistant_graph.py ai-module/core/dialogue_policy.py ai-module/core/langgraph_state.py ai-module/tests/
git commit -m "refactor(graph): understand owns facts, route becomes a Command mapping"
```

---

### Task 3: Delete the clarify/meta_clarify path and the string-matched decisions (C4b)

**Files:**
- Modify: `ai-module/core/assistant_graph.py` (`clarify` :718, `meta_clarify` :745, `direct_reply` :603, `_detect_direct_mode` :245, `build_graph` :873)
- Modify: `ai-module/core/langgraph_state.py`
- Test: `ai-module/tests/test_thin_route.py` (extend)

**Interfaces:**
- Consumes: `understand` and `route` from Task 2.
- Produces: graph with nodes `understand`, `scope_guard`, `route`, `direct_reply`, `search`, `retrieve`, `report`; `direct_reply` renders `answer` then `question` with no regex filtering.

- [ ] **Step 1: Write the failing test**

```python
from core.assistant_graph import build_graph


def test_graph_has_no_legacy_clarify_nodes():
    nodes = set(build_graph().get_graph().nodes)
    assert "clarify" not in nodes
    assert "meta_clarify" not in nodes


def test_graph_nodes_are_the_intended_set():
    nodes = set(build_graph().get_graph().nodes)
    assert {"understand", "scope_guard", "route", "direct_reply",
            "search", "retrieve", "report"} <= nodes


def test_state_has_no_legacy_keys():
    from core.langgraph_state import AssistantState
    for key in ("pending_categories", "relationship", "category_index",
                "active_category", "clarify_count", "clarify_stopped", "route_decision"):
        assert key not in AssistantState.__annotations__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai-module; python -m pytest tests/test_thin_route.py -v`
Expected: FAIL - `clarify` and `meta_clarify` are present.

- [ ] **Step 3: Delete the legacy code**

Delete from `ai-module/core/assistant_graph.py`: nodes `clarify` and `meta_clarify`; functions `_llm_phrase`, `_infer_categories`, `_score_category`, `_find_negated`, `_merge_categories`, `_is_separate_answer`, `_is_same_place_answer`, `_detect_other_cats`, `_relocate`, `_llm_extract_slots`, `_llm_classify`, `_join_text`, `_extract_vision_category`; constants `_SAME_PLACE_WORDS`, `_SEPARATE_WORDS`, `_CATEGORY_KEYWORDS`, `_dedupe`, `_sort_by_priority`; the `quick_judgment` branch of `_detect_direct_mode` (keep only the greeting set, rename it `_is_greeting`); and the `Language`/`CATEGORIES` references that become unused.

Delete from `ai-module/core/langgraph_state.py`: `pending_categories`, `relationship`, `category_index`, `active_category`, `clarify_count`, `clarify_stopped`, `route_decision`. Add `asked_question_last_turn: bool`, `offer_task: bool`, `task_offered: bool`, `task_phase: str`, `address_text: str`.

In `build_graph`, remove `add_node("clarify", ...)`, `add_node("meta_clarify", ...)`, `add_node("route_decider", ...)` and their edges.

- [ ] **Step 4: Remove the answer/question regex juggling in `direct_reply`**

Replace the sentence-stripping block with straight composition, because `answer` and `question` are already separate planner fields:

```python
    elif mode == "plan_reply" and plan.get("ok"):
        answer = str(plan.get("answer") or "").strip()
        question = (state.get("clarification_question") or "") if state.get("next_action") in {
            "ask_critical_question", "answer_with_optional_question",
        } else ""
        parts = [part for part in (answer, question) if part]
        answer = "\n\n".join(parts) or "我先记录你描述的情况，如需进一步判断可以继续补充现场信息。"
        try:
            get_stream_writer()({"chunk": answer})
        except Exception:
            pass
```

Also delete the `_detect_direct_mode` call inside `route` (it no longer exists there) and the `"plan_reply"` fallback branch that calls the report LLM without retrieval, since `understand` now always sets a plan or `answer_now`.

- [ ] **Step 5: Run the full suite**

Run: `cd ai-module; python -m pytest tests/ -q --deselect tests/test_multi_hazard.py::test_report_writes_custom_chunks --deselect tests/test_vector_delete_api.py`
Expected: all pass. Tests asserting `clarify` / `meta_clarify` / `pending_categories` behavior are deleted together with the feature; tests asserting user-visible behavior (one question, report content, scope) must be retargeted, not deleted.

- [ ] **Step 6: Commit**

```bash
git add -A ai-module
git commit -m "refactor(graph): delete legacy clarify path and string-matched decisions"
```
---

### Task 4: Checkpointer as the single source of truth (C1)

**Files:**
- Modify: `ai-module/core/langgraph_state.py`
- Modify: `ai-module/core/assistant_graph.py` (`run_stream_events` :959, `build_graph` :873)
- Test: `ai-module/tests/test_graph_state_persistence.py`

**Interfaces:**
- Consumes: `merge_category_results` from Task 1.
- Produces: `append_messages(left, right) -> list`; `build_turn_input(session_id, message, vision_summary, selected_major_code) -> dict`; `seed_messages(history) -> list`; `begin_turn(state) -> dict`; `get_checkpointer()`.

- [ ] **Step 1: Write the failing test**

```python
from typing import Annotated

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

from core.assistant_graph import build_turn_input, seed_messages
from core.langgraph_state import append_messages


def test_append_messages_caps_the_thread():
    state = {"messages": [HumanMessage(content=f"m{i}") for i in range(30)]}
    result = append_messages(state["messages"], [HumanMessage(content="new")])
    assert len(result) == 20
    assert result[-1].content == "new"


def test_build_turn_input_carries_only_the_new_turn():
    payload = build_turn_input("s1", "楼下消防栓坏了", "", "fire")
    assert set(payload) == {"session_id", "messages", "vision_summary", "selected_major_code"}
    assert len(payload["messages"]) == 1
    assert payload["messages"][0].content == "楼下消防栓坏了"
    assert "categories" not in payload and "issues" not in payload


def test_seed_messages_maps_roles():
    seeded = seed_messages([
        {"role": "user", "content": "u"}, {"role": "assistant", "content": "a"},
    ])
    assert [getattr(m, "content") for m in seeded] == ["u", "a"]


def test_structured_state_survives_a_second_turn_with_real_reducers():
    class S(TypedDict, total=False):
        messages: Annotated[list, append_messages]
        issues: list

    def first(state):
        return {"issues": [{"subcategory_code": "fire_equipment_fault"}]}

    def second(state):
        return {}

    graph = StateGraph(S)
    graph.add_node("first", first)
    graph.add_node("second", second)
    graph.add_edge(START, "first")
    graph.add_edge("first", "second")
    graph.add_edge("second", END)
    app = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t"}}
    app.invoke({"messages": [HumanMessage(content="u1")]}, config)
    app.invoke({"messages": [HumanMessage(content="u2")]}, config)
    values = app.get_state(config).values
    assert [m.content for m in values["messages"]] == ["u1", "u2"]
    assert values["issues"] == [{"subcategory_code": "fire_equipment_fault"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai-module; python -m pytest tests/test_graph_state_persistence.py -v`
Expected: FAIL - `ImportError: cannot import name 'build_turn_input'`.

- [ ] **Step 3: Add the reducers and pure helpers**

In `ai-module/core/langgraph_state.py`:

```python
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

MAX_THREAD_MESSAGES = 20


def append_messages(left, right) -> list:
    return add_messages(left or [], right or [])[-MAX_THREAD_MESSAGES:]


class AssistantState(TypedDict, total=False):
    messages: Annotated[list, append_messages]
    category_results: Annotated[dict, merge_category_results]
    # ...remaining keys unchanged, legacy keys already removed in Task 3
```

In `ai-module/core/assistant_graph.py`:

```python
def build_turn_input(session_id: str, message: str, vision_summary: str,
                     selected_major_code: str) -> dict:
    """Only this turn's new facts. Structured state lives in the checkpoint."""
    return {
        "session_id": session_id,
        "messages": [HumanMessage(content=message)],
        "vision_summary": vision_summary,
        "selected_major_code": selected_major_code,
    }


_ROLE_BUILDERS = {
    "system": SystemMessage, "user": HumanMessage, "assistant": AIMessage,
}


def seed_messages(history) -> list:
    """Cold-start history for a thread the checkpointer has never seen."""
    seeded = []
    for item in history or []:
        builder = _ROLE_BUILDERS.get(item.get("role"))
        if builder is not None:
            seeded.append(builder(content=item.get("content", "")))
    return seeded


def begin_turn(state: AssistantState) -> dict:
    """Reset per-turn flags. Entered only from START, so a task_gate re-entry skips it."""
    return {"task_offered": False, "asked_question_last_turn": False}


def get_checkpointer():
    global _CHECKPOINTER
    if _CHECKPOINTER is None:
        from pathlib import Path
        from langgraph.checkpoint.sqlite import SqliteSaver
        path = Path(__file__).resolve().parent.parent / "data" / "checkpoints.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        _CHECKPOINTER = SqliteSaver.from_conn_string(str(path))
    return _CHECKPOINTER
```

`SqliteSaver.from_conn_string` returns a context manager in some versions. Verify at implementation time; if it does, use `SqliteSaver(sqlite3.connect(path, check_same_thread=False))` and keep one connection guarded by a lock, because LangGraph runs nodes on worker threads.

- [ ] **Step 4: Rewire `run_stream_events` and the entry point**

```python
    config = {"configurable": {"thread_id": session_id}}
    snapshot = app.get_state(config)
    seed = [] if snapshot.values.get("messages") else seed_messages(history)
    initial = build_turn_input(session_id, message, vision_summary, selected_major_code)
    if seed:
        initial["messages"] = seed + initial["messages"]
```

Remove the hand-built `hc_msgs` loop and the full `initial` literal, including the `categories: []` / `category_slots: {}` / `missing: []` resets that caused the write-only checkpointer.

In `build_graph`:

```python
    g.add_node("begin_turn", begin_turn)
    g.set_entry_point("begin_turn")
    g.add_edge("begin_turn", "understand")
    return g.compile(checkpointer=get_checkpointer())
```

- [ ] **Step 5: Run tests**

Run: `cd ai-module; python -m pytest tests/test_graph_state_persistence.py tests/test_parallel_retrieval.py tests/test_thin_route.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai-module/core/langgraph_state.py ai-module/core/assistant_graph.py ai-module/tests/test_graph_state_persistence.py
git commit -m "feat(state): checkpoint holds structured facts with reducers"
```

---

### Task 5: Task confirmation via `interrupt` (C3)

**Files:**
- Modify: `ai-module/core/assistant_graph.py` (`report` :806, `can_offer_task_creation` :796, `_is_confirmation` :912, `_asked_to_create` :933, `_handle_submit` :945, `run_stream_events` :959, `build_graph` :873)
- Test: `ai-module/tests/test_task_gate_interrupt.py`

**Interfaces:**
- Consumes: `begin_turn`, `build_turn_input`, `get_checkpointer` from Task 4; `tools/hazard_submit.submit_from_history(user_id, history, latest) -> dict`.
- Produces: `task_gate(state) -> Command`; `submit_task(state) -> Command`; `close_task(state) -> dict`; `classify_task_reply(message) -> str` returning `confirm` | `decline` | `other`; SSE event `interrupt` with payload `{"type": "confirm_create_task", "question": str}`.

- [ ] **Step 1: Write the failing test**

```python
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

from core.assistant_graph import classify_task_reply, close_task, task_gate
from core.langgraph_state import append_messages


def test_classify_task_reply_deterministic_cases():
    assert classify_task_reply("好的，帮我建") == "confirm"
    assert classify_task_reply("要") == "confirm"
    assert classify_task_reply("不用了") == "decline"
    assert classify_task_reply("先不用建") == "decline"


def test_classify_task_reply_falls_back_to_other():
    assert classify_task_reply("那这个是隔壁楼的问题") == "other"


def _gate_graph():
    class S(TypedDict, total=False):
        messages: Annotated[list, append_messages]
        task_phase: str
        task_offered: bool
        address_text: str
        submitted: dict

    graph = StateGraph(S)
    graph.add_node("task_gate", task_gate)
    graph.add_node("submit_task", lambda s: {"submitted": {"action": "created"}})
    graph.add_node("close_task", close_task)
    graph.add_edge(START, "task_gate")
    graph.add_edge("submit_task", END)
    graph.add_edge("close_task", END)
    return graph.compile(checkpointer=InMemorySaver())


def test_task_gate_pauses_then_resumes_into_submit():
    app = _gate_graph()
    config = {"configurable": {"thread_id": "g1"}}
    for _mode, _item in app.stream({"task_phase": "confirm"}, config, stream_mode=["updates"]):
        pass
    assert app.get_state(config).next == ("task_gate",)
    for _mode, _item in app.stream(
        Command(resume={"decision": "confirm"}), config, stream_mode=["updates"]
    ):
        pass
    assert app.get_state(config).values["submitted"] == {"action": "created"}


def test_task_gate_decline_closes_without_submitting():
    app = _gate_graph()
    config = {"configurable": {"thread_id": "g2"}}
    for _ in app.stream({"task_phase": "confirm"}, config):
        pass
    for _ in app.stream(Command(resume={"decision": "decline"}), config):
        pass
    values = app.get_state(config).values
    assert "submitted" not in values
    assert values["task_offered"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ai-module; python -m pytest tests/test_task_gate_interrupt.py -v`
Expected: FAIL - `ImportError: cannot import name 'classify_task_reply'`.

- [ ] **Step 3: Implement the gate**

```python
_TASK_CONFIRM_WORDS = ("要", "好", "可以", "建", "上报", "创建", "是的", "行", "没问题", "需要", "麻烦你")
_TASK_DECLINE_WORDS = ("不需要", "不用了", "不要", "取消", "不建", "不用", "先不用")


def classify_task_reply(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return "other"
    if any(word in text for word in _TASK_DECLINE_WORDS):
        return "decline"
    if len(text) <= 12 and any(word in text for word in _TASK_CONFIRM_WORDS):
        return "confirm"
    return "other"


def task_gate(state: AssistantState) -> Command:
    phase = state.get("task_phase") or "confirm"
    if phase == "address":
        answer = interrupt({
            "type": "ask_address",
            "question": "请提供具体地址（如 XX 市 XX 区 XX 路 XX 小区），我好帮你定位并创建隐患任务。",
        })
        return Command(goto="submit_task",
                       update={"address_text": str(answer or "").strip(), "task_offered": True})
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


def close_task(state: AssistantState) -> dict:
    answer = "好的，那我不建任务。如果还有其他现场情况，直接说就行。"
    try:
        get_stream_writer()({"chunk": answer})
    except Exception:
        pass
    return {"messages": [AIMessage(content=answer)]}
```

`submit_task` reuses the existing submit path but reads history from graph state:

```python
def submit_task(state: AssistantState) -> Command:
    from tools.hazard_submit import submit_from_history
    history = [
        {"role": "assistant" if isinstance(m, AIMessage) else "user", "content": m.content}
        for m in state.get("messages") or [] if isinstance(m, (AIMessage, HumanMessage))
    ]
    latest = state.get("address_text") or (history[-1]["content"] if history else "")
    result = submit_from_history(state.get("user_id"), history, latest)
    if result.get("action") == "created":
        _emit_chunk(f"✅ 已创建隐患任务，任务编号 {result.get('hazardId')}")
        return Command(goto=END, update={"address_text": ""})
    if result.get("action") == "ask_address":
        return Command(goto="task_gate", update={"task_phase": "address"})
    _emit_chunk("⚠️ " + str(result.get("message")))
    return Command(goto=END, update={"address_text": ""})
```

`user_id` must be added to `AssistantState` and to `build_turn_input`.

- [ ] **Step 4: Wire `report` and the bridge**

`report` no longer appends an invitation sentence and no longer checks `"建一条隐患任务" not in draft`. It returns `offer_task`:

```python
    return {"draft_report": draft, "offer_task": can_offer_task_creation(state)}
```

Edges:

```python
    g.add_node("task_gate", task_gate)
    g.add_node("submit_task", submit_task)
    g.add_node("close_task", close_task)
    g.add_edge("report", "after_report")
    g.add_node("after_report", lambda s: {})
    g.add_conditional_edges("after_report",
                            lambda s: "task_gate" if (s.get("offer_task") and not s.get("task_offered")) else END)
    g.add_edge("submit_task", END)
    g.add_edge("close_task", END)
```

Delete `_is_confirmation`, `_asked_to_create`, `_PENDING_ADDRESS`, `_handle_submit`.

Bridge, inside `produce`:

```python
        snapshot = app.get_state(config)
        if snapshot.next == ("task_gate",):
            phase = snapshot.values.get("task_phase") or "confirm"
            if phase == "address":
                payload = Command(resume=message, update={"messages": [HumanMessage(content=message)]})
            else:
                payload = Command(resume={"decision": classify_task_reply(message)},
                                  update={"messages": [HumanMessage(content=message)]})
        else:
            payload = initial
            if seed:
                payload = {**payload, "messages": seed + payload["messages"]}
        for mode, item in app.stream(payload, config, stream_mode=["updates", "custom"]):
            ...
            if mode == "updates" and isinstance(item, dict) and "__interrupt__" in item:
                interrupts = item["__interrupt__"]
                emit("interrupt", int_payload(interrupts[0].value))
                continue
```

The seed must only be applied when the checkpoint has no messages, so compute the "needs seed" decision once per request from the same `snapshot` read.

- [ ] **Step 5: Run tests**

Run: `cd ai-module; python -m pytest tests/test_task_gate_interrupt.py -v`
Expected: PASS.

- [ ] **Step 6: Run the retrieval/scope/report regression**

Run: `cd ai-module; python -m pytest tests/ -q --deselect tests/test_multi_hazard.py::test_report_writes_custom_chunks --deselect tests/test_vector_delete_api.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add -A ai-module
git commit -m "feat(task): durable interrupt-based task confirmation"
```

---

### Task 6: Cleanup and full regression

**Files:**
- Modify: `ai-module/server.py` (`get_assistant` :141)
- Delete: `ai-module/core/assistant_agent.py`
- Test: full suite

- [ ] **Step 1: Confirm nothing imports the dead modules**

Run: `cd ai-module; rg -n "assistant_agent|create_assistant_agent|get_assistant" --glob "**/*.py" .`
Expected: only `server.py` and `core/assistant_agent.py`. If any route actually serves it, stop and report instead of deleting.

- [ ] **Step 2: Delete them**

Remove `get_assistant`, `_assistant`, and the `create_assistant_agent` import from `server.py`, delete `core/assistant_agent.py`. Leave `Orchestrator` and `/api/ai/analyze` in place - their traffic is unverified.

- [ ] **Step 3: Run the whole suite**

Run: `cd ai-module; python -m pytest tests/ -q --deselect tests/test_multi_hazard.py::test_report_writes_custom_chunks --deselect tests/test_vector_delete_api.py`
Expected: PASS. Compare the count against the pre-change baseline of 179 passed, 3 skipped, 6 deselected; explain any delta rather than accepting it.

- [ ] **Step 4: Commit**

```bash
git add -A ai-module
git commit -m "chore(ai): drop unused ReAct assistant module"
```

---

### Task 7: Deploy and smoke

**Files:**
- Read: `docs/deployment/safety-platform-deployment.md`

- [ ] **Step 1: Run the local suite twice more**

Run: `cd ai-module; python -m pytest tests/ -q --deselect tests/test_multi_hazard.py::test_report_writes_custom_chunks --deselect tests/test_vector_delete_api.py`
Expected: PASS twice, to catch order dependence from the new shared checkpointer file.

- [ ] **Step 2: Package and upload**

Follow `docs/deployment/safety-platform-deployment.md` exactly: tar `ai-module`, back up to `/home/ubuntu/ai-deploy-backups/<stamp>`, extract, restart with `venv/bin/python3 -u server.py`.

- [ ] **Step 3: Confirm health and that the checkpointer file exists**

```bash
ssh ubuntu@106.53.219.214 'curl -fsS --max-time 5 http://127.0.0.1:8000/api/ai/health && ls -l /home/ubuntu/ai-module/data/checkpoints.db'
```

- [ ] **Step 4: Smoke the four flows over SSE**

```bash
ssh ubuntu@106.53.219.214 'curl -sS --max-time 90 -X POST http://127.0.0.1:8000/api/ai/assistant/stream -H "Content-Type: application/json" -d "{\"message\":\"楼下消火栓坏了算隐患吗\",\"session_id\":\"smoke-quick-1\"}" | tail -c 1200'
```

Then repeat with a full-detail message, a task-creation session (two turns: hazard, then `好的`), and an out-of-scope message. Assert: the quick judgment now retrieves and reports; the task turn emits an `interrupt` event on turn 1 and creates the task on turn 2; out-of-scope text still uses the fixed template.

- [ ] **Step 5: Roll back if the smoke fails**

Restore `/home/ubuntu/ai-deploy-backups/<stamp>/ai-module-before.tar.gz` and restart, then report the failing flow instead of patching live.