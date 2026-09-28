# Scope Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic scope guard between semantic understanding and dialogue policy so unrelated questions are refused, ambiguous questions are anchored once, emergencies get safety-first guidance, and hazard flows remain unchanged.

**Architecture:** Add `core/scope_policy.py` as a pure decision module, a `scope_guard` LangGraph node after `understand`, fixed direct-reply templates, and planner `scope` metadata. No new model call and no Java/front-end API change.

**Tech Stack:** Python, LangGraph, pytest, existing SSE bridge.

## Global Constraints

- Do not answer clearly unrelated questions, even partially.
- Do not refuse precise hazard or emergency messages.
- Emergency guidance is safety-first and precedes any hazard questionnaire.
- Scope-guard responses are fixed templates, not model output.
- Existing hazard planning, retrieval, reporting, and task creation must still pass.
- Do not add general web search or general knowledge tools.

---

### Task 1: Pure scope policy

**Files:**
- Create: `ai-module/core/scope_policy.py`
- Test: `ai-module/tests/test_scope_policy.py`

**Interfaces:**

```python
def decide_scope(plan: dict, user_text: str) -> dict
```

Return:

```json
{
  "scope": "hazard",
  "reason": "",
  "response": ""
}
```

- [ ] **Step 1: Write failing scope tests**

```python
from core.scope_policy import decide_scope


def test_hazard_text_is_in_scope():
    out = decide_scope({}, "消防设施老旧，无法正常使用")
    assert out["scope"] == "hazard"


def test_weather_question_is_out_of_scope():
    out = decide_scope({}, "今天天气怎么样")
    assert out["scope"] == "out_of_scope"
    assert out["response"]


def test_emergency_has_priority_over_scope():
    out = decide_scope({}, "楼下着火了，有人被困")
    assert out["scope"] == "emergency"
    assert "119" in out["response"]


def test_ambiguous_request_gets_anchoring_question():
    out = decide_scope({}, "我有个问题想问")
    assert out["scope"] == "ambiguous"
    assert "是否涉及" in out["response"]


def test_generic_fire_word_does_not_create_false_positive():
    out = decide_scope({"scope": "out_of_scope"}, "消防员招聘条件")
    assert out["scope"] == "out_of_scope"


def test_planner_issue_overrides_weak_text():
    out = decide_scope({"ok": True, "issues": [{"subcategory_code": "fire_equipment_fault"}]}, "你说的这个")
    assert out["scope"] == "hazard"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_scope_policy.py -q`
Expected: FAIL because `core.scope_policy` does not exist.

- [ ] **Step 3: Implement `scope_policy.py`**

Use precise domain markers:

```python
DOMAIN_KEYWORDS = (
    "隐患", "安全", "占道", "盲道", "消防通道", "消防设施", "消火栓",
    "灭火器", "喷淋", "消防水源", "危房", "裂缝", "倾斜", "沉降",
    "高空坠物", "外墙", "广告牌", "井盖", "窨井", "路面", "塌陷",
    "电线", "漏电", "电缆", "配电箱", "燃气", "管道", "施工", "工地",
    "围挡", "脚手架", "深基坑", "电梯", "垃圾堆积", "污水", "异味",
)
```

Emergency markers include:

```python
EMERGENCY_KEYWORDS = (
    "着火了", "起火", "有人被困", "燃气泄漏", "爆炸", "触电",
    "坍塌", "救命", "马上", "紧急",
)
```

- [ ] **Step 4: Run scope tests**

Run: `python -m pytest tests/test_scope_policy.py -q`
Expected: PASS.

### Task 2: Planner scope metadata

**Files:**
- Modify: `ai-module/core/dialogue_understanding.py`
- Test: `ai-module/tests/test_scope_policy.py`

**Interfaces:**

Plan gains:

```python
scope: str               # hazard|emergency|smalltalk|ambiguous|out_of_scope
scope_confidence: float
```

- [ ] **Step 1: Write failing planner tests**

```python
def test_plan_reads_scope_metadata():
    raw = (
        '{"intent":"other","scope":"out_of_scope","scope_confidence":0.92,'
        '"issues":[],"question":"","answer":"","needs_search":false}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["scope"] == "out_of_scope"
    assert plan["scope_confidence"] == 0.92


def test_invalid_scope_defaults_to_empty_hint():
    raw = (
        '{"intent":"other","scope":"invalid","issues":[],"question":"",'
        '"answer":"","needs_search":false}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["scope"] == ""
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_scope_policy.py -q`
Expected: FAIL because planner does not expose scope metadata.

- [ ] **Step 3: Extend the planner prompt and parser**

Prompt rules:

- hazard: hazard description, judgment, regulation, remediation, or reporting;
- emergency: ongoing fire, trapped people, gas leak, electric shock, collapse;
- smalltalk: greeting/thanks;
- ambiguous: cannot determine scope from the message;
- out_of_scope: clearly unrelated to city safety hazards.

Do not let the generic word `消防` make `消防员招聘条件` a hazard.

- [ ] **Step 4: Run planner and scope tests**

Run: `python -m pytest tests/test_scope_policy.py -q`
Expected: PASS.

### Task 3: Graph scope_guard node

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Modify: `ai-module/core/langgraph_state.py`
- Test: `ai-module/tests/test_scope_policy.py`

**Interfaces:**

State gains:

```python
scope: str
scope_reason: str
```

Graph:

```python
g.add_node("scope_guard", scope_guard)
g.add_edge("understand", "scope_guard")
g.add_edge("scope_guard", "route")
```

Mapping:

```python
hazard -> continue normally
emergency -> direct_reply("emergency_reply")
ambiguous -> direct_reply("anchor_domain")
out_of_scope -> direct_reply("out_of_scope")
smalltalk -> direct_reply("smalltalk")
```

- [ ] **Step 1: Write failing graph tests**

```python
def test_scope_guard_refuses_out_of_scope_without_search(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True, "intent": "other", "scope": "out_of_scope",
        "scope_confidence": 0.95, "issues": [], "categories": [],
        "category_slots": {}, "question": "", "answer": "今天多云",
        "needs_search": False,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="今天天气怎么样")],
    })
    update = assistant_graph.scope_guard({**understood})
    assert update["scope"] == "out_of_scope"
    assert update["direct_mode"] == "out_of_scope"


def test_scope_guard_keeps_hazard_flow(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda *_: {
        "ok": True, "intent": "report_hazard", "scope": "hazard",
        "scope_confidence": 0.95,
        "issues": [{"major_code": "fire", "subcategory_code": "fire_equipment_fault", "missing": []}],
        "categories": ["fire_equipment_fault"], "category_slots": {},
        "question": "", "answer": "", "needs_search": True,
    })
    understood = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
    })
    assert assistant_graph.scope_guard({**understood}) == {}
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_scope_policy.py -q`
Expected: FAIL because `scope_guard` does not exist.

- [ ] **Step 3: Implement `scope_guard`**

If `direct_mode` is already set by the smalltalk/quick-judgment fast path, return `{}` and let the existing route handle it.

- [ ] **Step 4: Add fixed direct replies**

`direct_reply` handles:

```python
emergency_reply
anchor_domain
out_of_scope
```

No model call for these modes.

- [ ] **Step 5: Run graph and existing dialogue tests**

Run: `python -m pytest tests/test_scope_policy.py tests/test_dialogue_policy.py tests/test_semantic_dialogue.py -q`
Expected: PASS.

### Task 4: Regression and deployment

**Files:**
- No additional source files.

- [ ] **Step 1: Run focused regression**

Run:

```text
python -m pytest tests/test_scope_policy.py tests/test_dialogue_policy.py tests/test_hazard_taxonomy.py tests/test_semantic_dialogue.py tests/test_agent_dialogue_optimization.py tests/test_adaptive_slots.py tests/test_multi_hazard.py tests/test_report_context.py -q -k "not test_report_writes_custom_chunks"
```

- [ ] **Step 2: Deploy AI files**

Back up and upload `scope_policy.py`, `dialogue_understanding.py`, `assistant_graph.py`, and `langgraph_state.py`; compile with the remote venv; restart only AI.

- [ ] **Step 3: Smoke test out-of-scope refusal**

```text
今天天气怎么样
```

Expected: fixed scope refusal, no retrieval, no task offer.

- [ ] **Step 4: Smoke test emergency**

```text
楼下着火了，有人被困
```

Expected: 119/110 safety guidance, no hazard questionnaire before safety.

- [ ] **Step 5: Smoke test domain regression**

```text
消防设施老旧，无法正常使用
```

Expected: existing hazard taxonomy and report flow unchanged.

## Execution Result

Implemented and deployed on 2026-09-24.

- Added core/scope_policy.py with deterministic scopes:
  hazard, emergency, smalltalk, ambiguous, out_of_scope.
- Added scope_guard between understand and route.
- Added fixed template responses for emergency, ambiguity, and out-of-scope cases.
- Planner now emits scope and scope_confidence.
- Emergency messages bypass the planner model and immediately return 119/110 safety guidance.
- The assistant refuses non-hazard examples without retrieval or task creation.
- Domain hazard messages continue through the existing taxonomy, policy, retrieval, report, and task flow.

Verification:

- Broad focused suite: 179 passed, 3 skipped, 6 deselected.
- AI deployment IDs: 20260924T155229, 20260924T155627, and 20260924T161225.
- Cloud health: mimo-v2.6-flash; ports 8000 and 8080 healthy.
- Smoke out-of-scope weather and recruitment questions: fixed refusal.
- Smoke emergency message: immediate 119/110 guidance.
- Smoke hazard message: normal taxonomy and one critical question.
- Naturalness follow-up: planner `smalltalk` no longer hijacks non-greetings,
  out-of-scope templates rotate by session/turn key, and greetings are contextual
  (`你好`, `在吗`, `嗨`, `谢谢`).
