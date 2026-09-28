# Next-Action Dialogue Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic next-best-action policy between semantic understanding and existing graph actions, so responses adapt to risk, user intent, and information value instead of a fixed clarification count.

**Architecture:** Keep LangGraph, SSE, tools, report generation, and Java task creation. Add `core/dialogue_policy.py` as a pure decision function. Extend the planner with `risk_level`; keep the existing plan fields. The graph consumes `next_action` and maps it to existing action nodes. Legacy route behavior remains the fallback when planning fails.

**Tech Stack:** Python, LangGraph, pytest, existing MiMo client, existing FastAPI SSE bridge.

## Global Constraints

- Do not replace LangGraph or the existing tool layer.
- Do not add a separate model call for policy.
- Do not remove the legacy fallback path.
- Preliminary reports must not invite task creation.
- Full reports may invite task creation.
- Multi-hazard issues are evaluated independently.
- All policy behavior must be tested without external API calls.

---

### Task 1: Pure next-action policy

**Files:**
- Create: `ai-module/core/dialogue_policy.py`
- Test: `ai-module/tests/test_dialogue_policy.py`

**Interfaces:**

```python
def decide_next_action(plan: dict, state: dict) -> dict
```

Returns:

```json
{
  "action": "answer_now",
  "reason": "",
  "question": "",
  "optional_question": false,
  "needs_search": false,
  "report_mode": "none"
}
```

- [ ] **Step 1: Write failing policy tests**

```python
from core.dialogue_policy import decide_next_action


def test_high_risk_missing_critical_asks_one_question():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": ["facility_type"],
        }],
        "question": "具体是哪一类消防设施？",
        "answer": "我先理解为消防设施故障。",
    }
    out = decide_next_action(plan, {"user_text": "消防设施有问题"})
    assert out["action"] == "ask_critical_question"
    assert out["question"] == "具体是哪一类消防设施？"
    assert out["needs_search"] is False


def test_low_risk_missing_noncritical_answers_with_optional_question():
    plan = {
        "ok": True,
        "intent": "quick_assessment",
        "issues": [{
            "major_code": "environment_other",
            "subcategory_code": "garbage_pile",
            "missing": [],
        }],
        "question": "如果方便，可以补充垃圾堆积范围。",
        "answer": "这通常属于需要清理的安全隐患。",
    }
    out = decide_next_action(plan, {"user_text": "垃圾堆着"})
    assert out["action"] == "answer_with_optional_question"
    assert out["question"]


def test_explicit_stop_questioning_skips_clarification():
    plan = {
        "ok": True,
        "intent": "ask_solution",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": ["facility_type"],
        }],
        "question": "具体是哪一类消防设施？",
        "answer": "可以先按消防设施失效处理。",
    }
    out = decide_next_action(plan, {"user_text": "别问了，直接说怎么办"})
    assert out["action"] in {"answer_now", "report_preliminary"}
    assert out["question"] == ""


def test_complete_report_uses_full_mode():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "missing": [],
        }],
        "answer": "已确认消防设施失效。",
    }
    out = decide_next_action(plan, {"user_text": "消防栓没水，灭火器过期"})
    assert out["action"] == "report_full"
    assert out["needs_search"] is True
    assert out["report_mode"] == "full"


def test_incomplete_explicit_report_uses_preliminary_mode():
    plan = {
        "ok": True,
        "intent": "ask_regulation",
        "issues": [{
            "major_code": "building",
            "subcategory_code": "dangerous_building",
            "missing": ["structure"],
        }],
        "question": "",
        "answer": "",
    }
    out = decide_next_action(plan, {"user_text": "帮我查危房法规"})
    assert out["action"] == "report_preliminary"
    assert out["report_mode"] == "preliminary"


def test_multi_hazard_complete_issue_can_still_report_full():
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "issues": [
            {"major_code": "fire", "subcategory_code": "fire_equipment_fault", "missing": []},
            {"major_code": "building", "subcategory_code": "dangerous_building", "missing": ["structure"]},
        ],
        "answer": "已记录两个问题。",
    }
    out = decide_next_action(plan, {"user_text": "消防设施坏了，旁边还有危房"})
    assert out["action"] in {"report_full", "report_preliminary"}
    assert out["needs_search"] is True
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_dialogue_policy.py -q`
Expected: FAIL because `core.dialogue_policy` does not exist.

- [ ] **Step 3: Implement the policy**

Implementation requirements:

- Add `HIGH_RISK_MAJORS = {"fire", "building", "utility"}`.
- Detect explicit stop phrases: `别问了`, `不用问了`, `直接说`, `直接查`, `直接出报告`.
- Detect report intent: `ask_regulation`, `report_hazard`, `ask_solution`.
- Compute `has_complete_issue` and `has_missing_critical`.
- Return a question only for `ask_critical_question`, and clear it for all other actions.
- Never set `needs_search` for `ask_critical_question`.

- [ ] **Step 4: Run policy tests**

Run: `python -m pytest tests/test_dialogue_policy.py -q`
Expected: PASS.

### Task 2: Planner emits risk level and preserves answer/question

**Files:**
- Modify: `ai-module/core/dialogue_understanding.py`
- Test: `ai-module/tests/test_dialogue_policy.py`

**Interfaces:**

Planner plan gains:

```python
risk_level: str  # "high" | "medium" | "low"
```

- [ ] **Step 1: Write failing planner tests**

```python
def test_plan_parser_reads_risk_level():
    raw = (
        '{"intent":"report_hazard","risk_level":"high","issues":[{"major_code":"fire",'
        '"subcategory_code":"fire_equipment_fault","slots":{},"confidence":0.9}],'
        '"question":"","answer":"","needs_search":false,"relationship_hint":""}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["risk_level"] == "high"


def test_plan_parser_defaults_invalid_risk_level_to_medium():
    raw = (
        '{"intent":"other","risk_level":"unknown","categories":[],"category_slots":{},'
        '"question":"","answer":"","needs_search":false,"relationship_hint":""}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["risk_level"] == "medium"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_dialogue_policy.py -q`
Expected: FAIL because `risk_level` is missing.

- [ ] **Step 3: Add risk level to the planner prompt and parser**

Add `"risk_level":"high|medium|low"` to the JSON contract and explain:

- high: fire, building structural risk, electrical hazard, gas leak;
- medium: traffic, municipal, construction, elevator;
- low: environment/other.

- [ ] **Step 4: Run planner and policy tests**

Run: `python -m pytest tests/test_dialogue_policy.py -q`
Expected: PASS.

### Task 3: Graph consumes next_action

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Modify: `ai-module/core/langgraph_state.py`
- Test: `ai-module/tests/test_dialogue_policy.py`

**Interfaces:**

State gains:

```python
next_action: str
report_mode: str
policy_reason: str
```

Mapping:

```python
answer_now -> direct_reply
answer_with_optional_question -> direct_reply
ask_critical_question -> direct_reply
report_full/report_preliminary -> search
```

- [ ] **Step 1: Write failing graph tests**

```python
def test_route_uses_policy_action_for_short_high_risk_input(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
            "slots": {},
            "missing": ["facility_type", "condition"],
        }],
        "categories": ["fire_equipment_fault"],
        "category_slots": {"fire_equipment_fault": {}},
        "question": "具体是哪一类消防设施？",
        "answer": "我先理解为消防设施故障。",
        "needs_search": False,
    })
    update = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="消防设施有问题")],
    })
    assert update["dialogue_plan"]["risk_level"] == "high"


def test_policy_mapping_prefers_report_action(monkeypatch):
    plan = {
        "ok": True,
        "intent": "report_hazard",
        "risk_level": "high",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_equipment_fault", "missing": ["facility_type"]}],
        "categories": ["fire_equipment_fault"],
        "category_slots": {},
        "question": "具体是哪一类消防设施？",
        "answer": "先按消防设施失效处理。",
        "needs_search": False,
    }
    state = {"messages": [], "dialogue_plan": plan, "categories": [], "category_slots": {}}
    update = assistant_graph.route(state)
    assert update["next_action"] == "ask_critical_question"
    assert update["route_decision"] == "direct_reply"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_dialogue_policy.py -q`
Expected: FAIL because graph has no `next_action`.

- [ ] **Step 3: Integrate policy**

In `route`:

- call `decide_next_action(plan, state)` when a valid plan exists;
- store `next_action`, `report_mode`, `policy_reason`;
- map to `route_decision`;
- for `ask_critical_question` and optional-question actions, use `plan_reply` direct reply;
- for report actions, enter `search`;
- preserve existing legacy branch when no valid plan exists.

In `route_decider`:

- return `direct_reply` for answer/question actions;
- return `search` for report actions;
- keep legacy logic after these checks.

- [ ] **Step 4: Run graph and existing tests**

Run: `python -m pytest tests/test_dialogue_policy.py tests/test_semantic_dialogue.py tests/test_multi_hazard.py -q -k "not test_report_writes_custom_chunks"`
Expected: PASS.

### Task 4: Preliminary and full report modes

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Test: `ai-module/tests/test_dialogue_policy.py`

**Interfaces:**

Report prompt uses `report_mode`:

```text
full         -> current 3-section report
preliminary  -> preliminary judgment / still to verify / recommended action
```

- [ ] **Step 1: Write failing report-mode tests**

```python
def test_preliminary_report_does_not_offer_task_creation(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(
        assistant_graph._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation: iter([("chunk", "初步判断")]),
    )
    update = assistant_graph.report({
        "messages": [], "categories": ["fire_equipment_fault"],
        "category_results": {"fire_equipment_fault": {"regulation": "法", "case": "案例"}},
        "missing": ["facility_type"], "issues": [{"subcategory_code": "fire_equipment_fault"}],
        "report_mode": "preliminary",
    })
    assert "初步判断" in update["draft_report"]
    assert "建一条隐患任务" not in update["draft_report"]


def test_full_report_offers_task_creation_when_complete(monkeypatch):
    chunks = []
    monkeypatch.setattr(assistant_graph, "get_stream_writer", lambda: chunks.append)
    monkeypatch.setattr(
        assistant_graph._report_llm, "_call_llm_stream_events",
        lambda messages, cancellation: iter([("chunk", "完整报告")]),
    )
    update = assistant_graph.report({
        "messages": [], "categories": ["fire_equipment_fault"],
        "category_results": {"fire_equipment_fault": {"regulation": "法", "case": "案例"}},
        "missing": [], "issues": [{"subcategory_code": "fire_equipment_fault"}],
        "report_mode": "full",
    })
    assert "建一条隐患任务" in update["draft_report"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_dialogue_policy.py -q`
Expected: FAIL because report mode is ignored.

- [ ] **Step 3: Implement report modes**

- `report_full` keeps the current retrieval/report prompt and task offer.
- `report_preliminary` uses the three preliminary headings and forbids fabricated facts.
- `report` reads `state["report_mode"]`, defaulting to `full` for backward compatibility.
- `can_offer_task_creation` requires `report_mode == "full"`.

- [ ] **Step 4: Run report and policy tests**

Run: `python -m pytest tests/test_dialogue_policy.py tests/test_semantic_dialogue.py -q`
Expected: PASS.

### Task 5: Evaluation scenarios and fallback

**Files:**
- Modify: `ai-module/tests/test_dialogue_policy.py`
- Test: same file.

- [ ] **Step 1: Add data-driven scenario tests**

Cover:

- `消防设施有问题` -> one critical question;
- `垃圾堆着没人管` -> answer with optional question;
- `别问了，直接说怎么办` -> no further question;
- `帮我查危房法规` -> preliminary report;
- `消防栓没水，灭火器也过期了` -> full report;
- `消防通道被堵，旁边还有危房` -> multi-hazard behavior;
- planner returns `{}` -> legacy route still works.

- [ ] **Step 2: Run all focused tests**

Run: `python -m pytest tests/test_dialogue_policy.py tests/test_hazard_taxonomy.py tests/test_semantic_dialogue.py tests/test_agent_dialogue_optimization.py tests/test_adaptive_slots.py tests/test_multi_hazard.py tests/test_report_context.py -q -k "not test_report_writes_custom_chunks"`
Expected: PASS.

### Task 6: Deploy and smoke test

**Files:**
- No additional source files.

- [ ] **Step 1: Run the full focused suite**

Run the command from Task 5 Step 2.

- [ ] **Step 2: Deploy changed AI files**

Back up remote AI files, upload the new/changed `core` files, compile with the remote venv, and restart only the AI service.

- [ ] **Step 3: Smoke test short, high-risk input**

```text
消防设施有问题
```

Expected: one high-value question, no premature retrieval.

- [ ] **Step 4: Smoke test full evidence**

```text
消防栓没水，灭火器也过期了
```

Expected: retrieval, full report, and a task-creation offer.

- [ ] **Step 5: Smoke test explicit stop**

```text
消防设施有问题，别问了，直接说怎么办
```

Expected: answer or preliminary report without another question.

## Execution Result

Implemented and deployed on 2026-09-24.

- Added `core/dialogue_policy.py` with deterministic actions:
  `answer_now`, `answer_with_optional_question`, `ask_critical_question`,
  `report_preliminary`, `report_full`, `meta_clarify`.
- Planner now emits `risk_level`; graph maps policy actions onto the existing
  `direct_reply`, `search`, and `meta_clarify` route literals.
- Preliminary reports use the new three-section uncertainty format and do not
  invite task creation.
- Full reports keep the existing report format and task-creation offer.
- Confirmation detection now rejects negative phrases such as `不需要` and
  avoids matching ordinary sentences such as `我要投诉物业`.
- A normal high-risk answer now emits at most one question mark.
- Added independent verification findings and regression tests for legacy
  fallback, mixed multi-hazard completeness, report offers, stop phrases,
  quick assessments without answers, and confirmation false positives.

Verification:

- Broad focused suite: 159 passed, 3 skipped, 6 deselected.
- AI deployment IDs: `20260924T134700`, `20260924T134825`, `20260924T135049`, and `20260924T140919`.
- Cloud health: `mimo-v2.6-flash`, port 8000 healthy; Java port 8080 healthy.
- Smoke `消防设施有问题`: one high-value question, no premature retrieval.
- The final invariant fix keeps the response to exactly one question mark and prevents `answer_now` from attaching a planner leftover question.
- Smoke `消防栓没水，灭火器也过期了`: retrieval, full report, task-creation offer.
- Smoke `消防设施有问题，别问了，直接说怎么办`: retrieval and preliminary report,
  no further clarification question.
- Final determinism fix: a complete, detailed hazard description now produces a
  full report even when conversation history was lost after a service restart.
  Casual judgment questions such as `盲道被车占了，算安全隐患吗？` still stay on
  the fast-answer path.
