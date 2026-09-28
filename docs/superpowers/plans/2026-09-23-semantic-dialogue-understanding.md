# Semantic Dialogue Understanding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one structured semantic-understanding stage to the existing LangGraph assistant so context, object type, and clarification questions are decided by the model while business rules and side effects remain deterministic.

**Architecture:** Keep LangGraph, SSE, retrieval, report generation, and the Java task-creation flow. Add `core/dialogue_understanding.py`, route the graph entry through an `understand` node, validate its plan in the existing `route`, and make clarification use the plan's single question. Leave the legacy Orchestrator image-report endpoints unchanged.

**Tech Stack:** Python, FastAPI, LangGraph, pytest, MiMo OpenAI-compatible client.

## Global Constraints

- Do not redesign the retrieval store, Java service, or SSE contract.
- Consultation categories may grow; task-creation categories remain the existing four.
- `消防设施故障` and `消防通道占用` must remain distinct.
- Normal consultation asks at most one question per turn.
- Planner failure must fall back to existing routing behavior.
- Do not modify credentials, external endpoints, Java modules, or unrelated working-tree changes.

---

### Task 1: Add the semantic understanding contract and category boundary

**Files:**
- Create: `ai-module/core/dialogue_understanding.py`
- Modify: `ai-module/core/hazard_categories.py`
- Modify: `ai-module/core/assistant_graph.py`
- Test: `ai-module/tests/test_semantic_dialogue.py`

**Interfaces:**
- `core.hazard_categories.CONSULT_CATEGORIES`: includes `消防设施`.
- `core.dialogue_understanding.parse_plan(raw: str) -> dict`: returns a validated plan or `{}`.
- `core.dialogue_understanding.build_planner_messages(messages, vision_summary) -> list[dict]`.
- `core.dialogue_understanding.understand(messages, vision_summary) -> dict`: calls the planner and returns a validated plan.

- [ ] **Step 1: Write the failing test for the category boundary**

```python
def test_fire_facilities_are_distinct_from_fire_lanes():
    from core.hazard_categories import CONSULT_CATEGORIES
    assert "消防设施" in CONSULT_CATEGORIES
    assert "消防通道" in CONSULT_CATEGORIES
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m pytest tests/test_semantic_dialogue.py::test_fire_facilities_are_distinct_from_fire_lanes -q`
Expected: FAIL because `消防设施` is absent.

- [ ] **Step 3: Add `消防设施` and its slot schema**

Add the category to `CONSULT_CATEGORIES`, `CATEGORY_PRIORITY`, `_CATEGORY_KEYWORDS`, and `SLOT_SCHEMAS`.

```python
"消防设施": [
    Slot("facility_type", "具体是哪一类消防设施，例如消火栓、喷淋、报警器还是灭火器？"),
    Slot("condition", "目前是老旧、损坏还是完全无法使用？"),
    Slot("function_impact", "是否影响整栋建筑的消防报警或灭火功能？", critical=False),
]
```

- [ ] **Step 4: Add the planner contract test**

```python
def test_plan_parser_rejects_unknown_categories_and_extra_questions():
    raw = '{"intent":"report_hazard","categories":["消防通道","不存在"],'
    raw += '"category_slots":{"消防通道":{"blocker":"车辆"}},"question":"第一个？",'
    raw += '"answer":"收到","needs_search":false,"confidence":0.9}'
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["categories"] == ["消防通道"]
    assert plan["question"].count("？") <= 1
```

- [ ] **Step 5: Run the planner test and verify it fails**

Run: `python -m pytest tests/test_semantic_dialogue.py::test_plan_parser_rejects_unknown_categories_and_extra_questions -q`
Expected: FAIL because `core.dialogue_understanding` does not exist.

- [ ] **Step 6: Implement `dialogue_understanding.py`**

The planner prompt must include:

- allowed category values;
- the slot schema for each category;
- the rule that `消防设施` and `消防通道` are different;
- the rule that a normal consultation asks at most one question;
- the rule that already answered facts are not asked again;
- the rule that retrieval is requested only when the user wants regulations, cases, or a report.

`parse_plan` must:

- accept markdown-fenced JSON;
- reject non-JSON output;
- drop unknown categories;
- keep only known slot keys;
- keep at most one question;
- coerce `needs_search` and `confidence`.

- [ ] **Step 7: Run the focused tests**

Run: `python -m pytest tests/test_semantic_dialogue.py -q`
Expected: PASS.

### Task 2: Route through understanding without adding a second extraction call

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Modify: `ai-module/core/langgraph_state.py`
- Test: `ai-module/tests/test_semantic_dialogue.py`

**Interfaces:**

- `understand` graph node stores `dialogue_plan`, `intent`, `categories`, `category_slots`, `missing`, and `clarification_question`.
- `route` uses a valid plan instead of calling `_llm_extract_slots` a second time.
- `clarify` uses `clarification_question` when present and otherwise asks one slot.

- [ ] **Step 1: Write failing tests**

```python
def test_screenshot_utterance_uses_fire_facility_not_fire_lane(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_understand_plan", lambda messages, vision: {
        "ok": True,
        "intent": "quick_assessment",
        "categories": ["消防设施"],
        "category_slots": {"消防设施": {
            "condition": "老旧", "function_impact": "不能正常使用",
        }},
        "question": "具体是哪一类消防设施？",
        "answer": "我理解为消防设施老旧、无法正常使用。",
        "needs_search": False,
        "confidence": 0.95,
    })
    update = assistant_graph.understand({
        "messages": [assistant_graph.HumanMessage(
            content="三明市万达广场对面的消防设施过于老旧，不能正常使用"
        )],
        "vision_summary": "",
    })
    assert update["categories"] == ["消防设施"]
    assert update["clarification_question"] == "具体是哪一类消防设施？"

def test_route_does_not_re_extract_when_plan_is_present(monkeypatch):
    monkeypatch.setattr(assistant_graph, "_llm_extract_slots", lambda *_: pytest.fail("duplicate extraction"))
    state = {
        "messages": [assistant_graph.HumanMessage(content="消防设施老旧")],
        "dialogue_plan": {
            "ok": True, "categories": ["消防设施"],
            "category_slots": {"消防设施": {"condition": "老旧"}},
            "question": "", "answer": "", "needs_search": False,
        },
        "categories": [], "category_slots": {}, "vision_summary": "",
    }
    update = assistant_graph.route(state)
    assert update["categories"] == ["消防设施"]

def test_clarify_asks_only_one_question(monkeypatch):
    seen = {}
    monkeypatch.setattr(assistant_graph, "_llm_phrase", lambda slots, ctx: seen.setdefault("slots", list(slots)) or "只问一个问题？")
    update = assistant_graph.clarify({
        "messages": [], "categories": ["消防设施"], "active_category": "消防设施",
        "missing": ["消防设施_facility_type", "消防设施_condition"],
        "category_slots": {"消防设施": {}}, "clarify_count": 0,
    })
    assert len(seen["slots"]) == 1
    assert update["messages"][-1].content == "只问一个问题？"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m pytest tests/test_semantic_dialogue.py -q`
Expected: FAIL because `understand` and the plan-aware path do not exist.

- [ ] **Step 3: Add `understand` as the graph entry node**

Add the node before `route`, store the validated plan, and keep the existing `route` as fallback.

```python
g.add_node("understand", understand)
g.set_entry_point("understand")
g.add_edge("understand", "route")
```

- [ ] **Step 4: Make `route` consume the plan**

When `dialogue_plan["ok"]` is true, use its categories and slots instead of calling `_infer_categories` and `_llm_extract_slots`.

- [ ] **Step 5: Make `clarify` use one plan question**

Use `state["clarification_question"]` when available. Otherwise select one slot and call `_llm_phrase` with one key.

- [ ] **Step 6: Run focused and existing graph tests**

Run: `python -m pytest tests/test_semantic_dialogue.py tests/test_agent_dialogue_optimization.py tests/test_multi_hazard.py tests/test_adaptive_slots.py -q -k "not test_report_writes_custom_chunks"`
Expected: PASS.

### Task 3: Send the intended system prompt and preserve image-report compatibility

**Files:**
- Modify: `ai-module/core/agent.py`
- Test: `ai-module/tests/test_semantic_dialogue.py`

**Interfaces:**
- `Agent._build_payload` prepends `self.system_prompt` when the caller supplied no system message.

- [ ] **Step 1: Write failing tests**

```python
def test_payload_includes_system_prompt_when_absent():
    from core.agent import Agent
    agent = Agent(name="x", system_prompt="SYSTEM", tools=[],
                  base_url="http://example", api_key="k", model="m")
    payload = agent._build_payload([{"role": "user", "content": "hi"}], stream=False)
    assert payload["messages"][0] == {"role": "system", "content": "SYSTEM"}

def test_payload_does_not_duplicate_existing_system_message():
    from core.agent import Agent
    agent = Agent(name="x", system_prompt="SYSTEM", tools=[],
                  base_url="http://example", api_key="k", model="m")
    payload = agent._build_payload(
        [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "hi"}],
        stream=False,
    )
    assert payload["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert len([m for m in payload["messages"] if m["role"] == "system"]) == 1
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m pytest tests/test_semantic_dialogue.py -q`
Expected: FAIL because the prompt is absent.

- [ ] **Step 3: Implement the payload guard**

Prepend the prompt only when no system message is already present. This avoids sending two conflicting system messages to the report model.

- [ ] **Step 4: Verify the image-report compatibility import**

Run: `python -c "import server; server.get_orch(); print('orchestrator ok')"`
Expected: prints `orchestrator ok` without contacting external services.

### Task 4: Verify, deploy, and smoke test

**Files:**
- No additional source files.

- [ ] **Step 1: Run the full focused test set**

Run: `python -m pytest tests/test_semantic_dialogue.py tests/test_agent_dialogue_optimization.py tests/test_multi_hazard.py tests/test_adaptive_slots.py tests/test_report_context.py -q -k "not test_report_writes_custom_chunks"`
Expected: PASS.

- [ ] **Step 2: Deploy only the changed Python files**

Back up the remote files, upload the staged files, compile them with the remote virtual environment, and restart the AI service.

- [ ] **Step 3: Smoke test the screenshot utterance**

Call `/api/ai/assistant/stream` with:

> 三明市万达广场对面的消防设施过于老旧，不能正常使用

Expected: the response mentions `消防设施` and asks at most one relevant question; it does not ask about a blocked fire lane.

- [ ] **Step 4: Smoke test a detailed request**

Call `/api/ai/assistant/stream` with:

> 长期堵住盲道，帮我查法规和案例

Expected: the request still reaches retrieval and report generation.

## Execution Result

All four tasks were executed on 2026-09-23. Cloud deployment IDs were `20260923T202213` and `20260923T202717`.

- Focused regression: 67 passed, 1 pre-existing test deselected.
- Broad regression: 105 passed, 3 skipped, 6 deselected.
- Screenshot smoke passed and returned one facility-type question in about 10.6 seconds.
- The final prompt tightening removed the extra location sub-question from that response.
- Detailed smoke passed and returned a regulation/case report in about 65 seconds.
- Multi-turn smoke kept the original fire-facility issue and the newly added dangerous-building issue.
- The legacy Orchestrator and image-report endpoints remain available.
