# Two-Level Hazard Taxonomy Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat four-category task model with a shared two-level hazard taxonomy where the frontend supplies an optional major-category hint and the AI backend resolves the subcategory, facts, multi-hazard list, retrieval need, and task-creation eligibility.

**Architecture:** Add one shared taxonomy module for codes, labels, legacy mapping, and slot profiles. Extend the structured planner to emit `major_code` and `subcategory_code` per issue. Keep LangGraph as the policy and execution layer, keep SSE event types backward-compatible, and make task creation accept every canonical subcategory.

**Tech Stack:** Python, FastAPI, LangGraph, pytest, MiMo OpenAI-compatible client, Spring Boot controller/service passthrough.

The frontend contract and canonical codes live in `docs/superpowers/specs/2026-09-23-two-level-hazard-taxonomy-frontend.md`. Code values in these two documents must stay identical.

## Global Constraints

- The frontend major selection is a hint, never a hard whitelist.
- The AI backend resolves the final major and subcategory.
- Consultation, retrieval, reporting, and task creation use the same taxonomy codes.
- Task creation does not require one of the old four categories.
- Every issue stores `major_code` and `subcategory_code`.
- `tb_hazard.hazard_type` stores `<major_code>/<subcategory_code>` for new records.
- Legacy values remain readable.
- Existing SSE types `status`, `chunk`, `done`, and `error` must keep working.
- Planner failure falls back to keyword routing.
- Do not modify credentials, external endpoints, or task status transitions.

---

### Task 1: Shared taxonomy module

**Files:**

- Create: `ai-module/core/hazard_taxonomy.py`
- Modify: `ai-module/core/hazard_categories.py`
- Test: `ai-module/tests/test_hazard_taxonomy.py`

**Interfaces:**

- `HAZARD_TAXONOMY: tuple[dict, ...]`
- `MAJOR_LABELS: dict[str, str]`
- `SUBCATEGORY_LABELS: dict[str, str]`
- `SUBCATEGORY_TO_MAJOR: dict[str, str]`
- `LEGACY_CATEGORY_MAP: dict[str, tuple[str, str]]`
- `ALL_SUBCATEGORY_CODES: frozenset[str]`
- `normalize_taxonomy(value: str) -> tuple[str, str] | None`
- `format_hazard_type(major_code: str, subcategory_code: str) -> str`
- `parse_hazard_type(value: str) -> tuple[str, str] | None`

Taxonomy values:

```python
HAZARD_TAXONOMY = (
    {"code": "traffic", "label": "交通与通行", "subcategories": (
        ("road_occupancy", "占道经营/乱堆乱放"),
        ("vehicle_occupancy", "车辆占道"),
        ("blind_path_occupied", "盲道占用"),
        ("traffic_facility_damage", "交通设施损坏"),
    )},
    {"code": "municipal", "label": "市政设施", "subcategories": (
        ("manhole_damage", "井盖缺失/破损"),
        ("road_surface_collapse", "路面塌陷"),
        ("drainage_flood", "排水/积水"),
        ("street_light_pole", "路灯/线杆损坏"),
    )},
    {"code": "fire", "label": "消防安全", "subcategories": (
        ("fire_lane_blocked", "消防通道占用"),
        ("fire_equipment_fault", "消防设施故障"),
        ("fire_water_abnormal", "消防水源异常"),
    )},
    {"code": "building", "label": "建筑安全", "subcategories": (
        ("dangerous_building", "危房"),
        ("wall_crack_lean", "墙体开裂/倾斜"),
        ("facade_fall", "外立面脱落"),
        ("falling_object", "高空坠物"),
        ("illegal_structure", "违规搭建"),
    )},
    {"code": "utility", "label": "电气与燃气", "subcategories": (
        ("exposed_wire", "裸露/老化电线"),
        ("distribution_box_fault", "配电设施故障"),
        ("illegal_wiring", "私拉乱接"),
        ("gas_leak", "燃气泄漏"),
        ("gas_pipe_aging", "燃气管道老化"),
    )},
    {"code": "construction", "label": "施工安全", "subcategories": (
        ("no_barrier", "未设置围挡"),
        ("no_warning", "无安全警示"),
        ("scaffold_guard", "脚手架/临边防护"),
        ("deep_pit", "深基坑风险"),
        ("temporary_power", "施工临时用电"),
    )},
    {"code": "elevator_special", "label": "电梯与特种设备", "subcategories": (
        ("elevator_trapped", "电梯困人"),
        ("elevator_stopped", "停运/异响"),
        ("elevator_inspection", "超期未检"),
    )},
    {"code": "environment_other", "label": "环境与其他", "subcategories": (
        ("garbage_pile", "垃圾堆积"),
        ("sewage_odor", "污水/异味"),
        ("other", "其他"),
    )},
)
```

- [ ] **Step 1: Write failing taxonomy tests**

```python
from core.hazard_taxonomy import (
    ALL_SUBCATEGORY_CODES,
    format_hazard_type,
    normalize_taxonomy,
    parse_hazard_type,
)


def test_equipment_fault_and_lane_block_are_distinct():
    assert normalize_taxonomy("utility/exposed_wire") == ("utility", "exposed_wire")
    assert normalize_taxonomy("fire/fire_equipment_fault") == (
        "fire", "fire_equipment_fault"
    )
    assert normalize_taxonomy("fire/fire_lane_blocked") == (
        "fire", "fire_lane_blocked"
    )


def test_legacy_mapping_is_supported():
    assert normalize_taxonomy("消防设施") == ("fire", "fire_equipment_fault")
    assert normalize_taxonomy("占道") == ("traffic", "road_occupancy")


def test_task_storage_format_round_trips():
    value = format_hazard_type("fire", "fire_equipment_fault")
    assert value == "fire/fire_equipment_fault"
    assert parse_hazard_type(value) == ("fire", "fire_equipment_fault")
    assert parse_hazard_type("消防设施") == ("fire", "fire_equipment_fault")


def test_every_subcategory_code_is_unique():
    assert len(ALL_SUBCATEGORY_CODES) == sum(
        len(item["subcategories"]) for item in HAZARD_TAXONOMY
    )
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_hazard_taxonomy.py -q`
Expected: FAIL because `core.hazard_taxonomy` does not exist.

- [ ] **Step 3: Implement `hazard_taxonomy.py`**

`hazard_categories.py` becomes a compatibility facade:

```python
from core.hazard_taxonomy import MAJOR_LABELS, ALL_SUBCATEGORY_CODES

CONSULT_CATEGORIES = tuple(MAJOR_LABELS.values())
SUBMIT_CATEGORIES = tuple(ALL_SUBCATEGORY_CODES)
```

Keep `normalize_vision_category` in `hazard_categories.py` for one release, but map vision labels to canonical subcategory codes.

- [ ] **Step 4: Run taxonomy tests**

Run: `python -m pytest tests/test_hazard_taxonomy.py -q`
Expected: PASS.

### Task 2: Planner emits issue-level taxonomy and retrieval policy

**Files:**

- Modify: `ai-module/core/dialogue_understanding.py`
- Modify: `ai-module/core/slot_schemas.py`
- Test: `ai-module/tests/test_semantic_dialogue.py`

**Interfaces:**

Planner output:

```json
{
  "intent": "report_hazard",
  "selected_major_code": "fire",
  "major_mismatch": false,
  "issues": [
    {
      "major_code": "fire",
      "subcategory_code": "fire_equipment_fault",
      "slots": {
        "facility_type": "消火栓和灭火器",
        "condition": "老旧",
        "function_impact": "无法正常使用"
      },
      "confidence": 0.95
    }
  ],
  "question": "",
  "answer": "",
  "needs_search": true,
  "relationship_hint": "add"
}
```

Planner rule changes:

- Include `selected_major_code` in the request.
- If it is missing, use `自动判断`.
- If the selected major and resolved major differ, set `major_mismatch=true`.
- For `intent in {"report_hazard", "quick_assessment"}`, if all critical slots are filled, set `needs_search=true`.
- Keep `question` to one information point and do not ask for location unless task creation is confirmed.
- Return all active issues, including an added issue from a later turn.

- [ ] **Step 1: Write failing planner tests**

```python
def test_planner_resolves_subcategory_under_selected_major(monkeypatch):
    raw = (
        '{"intent":"report_hazard","selected_major_code":"fire",'
        '"major_mismatch":false,"issues":[{"major_code":"fire",'
        '"subcategory_code":"fire_equipment_fault","slots":{'
        '"facility_type":"消火栓和灭火器","condition":"老旧",'
        '"function_impact":"无法正常使用"},"confidence":0.95}],'
        '"question":"","answer":"","needs_search":true,'
        '"relationship_hint":"add"}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["ok"] is True
    assert plan["issues"][0]["major_code"] == "fire"
    assert plan["issues"][0]["subcategory_code"] == "fire_equipment_fault"
    assert plan["needs_search"] is True


def test_planner_marks_major_mismatch():
    raw = (
        '{"intent":"report_hazard","selected_major_code":"municipal",'
        '"major_mismatch":true,"issues":[{"major_code":"fire",'
        '"subcategory_code":"fire_equipment_fault","slots":{},'
        '"confidence":0.9}],"question":"","answer":"",'
        '"needs_search":false,"relationship_hint":""}'
    )
    plan = dialogue_understanding.parse_plan(raw)
    assert plan["major_mismatch"] is True
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_semantic_dialogue.py -q`
Expected: FAIL because the planner contract has no issue-level taxonomy.

- [ ] **Step 3: Change the planner prompt**

The prompt must include:

- the canonical taxonomy codes and labels;
- the selected major as a hint;
- the rule that the model may correct a mismatched major;
- the rule that all active issues are returned;
- the retrieval rule for `report_hazard`.

- [ ] **Step 4: Change `parse_plan`**

Drop unknown codes, deduplicate issues, require a valid `major_code/subcategory_code` pair, and derive compatibility fields:

```python
plan["categories"] = [issue["subcategory_code"] for issue in issues]
plan["category_slots"] = {
    issue["subcategory_code"]: issue.get("slots", {}) for issue in issues
}
```

- [ ] **Step 5: Add subcategory slot profiles**

Key `SLOT_SCHEMAS` by subcategory code. Examples:

```python
"fire_equipment_fault": [
    Slot("facility_type", "具体是哪一类消防设施，例如消火栓、喷淋、报警器还是灭火器？"),
    Slot("condition", "目前是老旧、损坏还是完全无法使用？"),
    Slot("function_impact", "是否影响整栋建筑的消防报警或灭火功能？", critical=False),
],
"fire_lane_blocked": [
    Slot("blocker", "被什么东西占用了？"),
    Slot("persistence", "是长期还是临时？"),
    Slot("impact", "是否影响消防车或人员通行？", critical=False),
],
"dangerous_building": [
    Slot("structure", "房屋有没有裂缝、倾斜或沉降？"),
    Slot("occupancy", "现在有人在里面居住或使用吗？"),
    Slot("risk", "有没有明显的即时坍塌风险？"),
],
```

Provide a fallback profile by major code.

- [ ] **Step 6: Run planner and slot tests**

Run: `python -m pytest tests/test_hazard_taxonomy.py tests/test_semantic_dialogue.py -q`
Expected: PASS.

### Task 3: Graph uses taxonomy issues and removes the four-category task gate

**Files:**

- Modify: `ai-module/core/assistant_graph.py`
- Modify: `ai-module/core/langgraph_state.py`
- Test: `ai-module/tests/test_semantic_dialogue.py`

**Interfaces:**

New state fields:

```python
issues: list[dict]                 # canonical issue list from the planner
selected_major_code: str           # frontend hint
major_mismatch: bool               # planner correction flag
```

Task eligibility:

```python
ask_create = (not missing) and bool(issues)
```

There is no `all(category in SUBMIT_CATEGORIES)` gate. For multiple issues, ask for all eligible tasks or list them explicitly.

- [ ] **Step 1: Write failing graph tests**

```python
def test_fire_equipment_fault_can_offer_task_creation(monkeypatch):
    state = {
        "messages": [],
        "issues": [{
            "major_code": "fire",
            "subcategory_code": "fire_equipment_fault",
        }],
        "missing": [],
        "categories": ["fire_equipment_fault"],
        "dialogue_plan": {"ok": True, "issues": state["issues"]},
    }
    # Report prompt must not contain a task-creation prohibition.
    assert "fire_equipment_fault" in assistant_graph.report_prompt_context(state)


def test_multiple_issues_do_not_block_each_other(monkeypatch):
    state = {
        "issues": [
            {"major_code": "traffic", "subcategory_code": "vehicle_occupancy"},
            {"major_code": "fire", "subcategory_code": "fire_equipment_fault"},
        ],
        "missing": [],
    }
    assert assistant_graph.can_offer_task_creation(state) is True
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_semantic_dialogue.py -q`
Expected: FAIL because the graph still uses the old flat categories.

- [ ] **Step 3: Convert plan issues into graph categories**

For each issue, store:

```python
{
    "major_code": "fire",
    "subcategory_code": "fire_equipment_fault",
    "slots": {...},
}
```

Use `subcategory_code` as the internal slot key and the subcategory label in prompts and reports.

- [ ] **Step 4: Replace the task gate**

Use:

```python
def can_offer_task_creation(state) -> bool:
    return bool(state.get("issues")) and not state.get("missing")
```

If one issue is missing critical information, still allow an offer for another complete issue.

- [ ] **Step 5: Emit optional taxonomy metadata**

In the SSE bridge, after understanding succeeds, emit once:

```python
emit("taxonomy", {
    "selected_major_code": state.get("selected_major_code", ""),
    "major_mismatch": state.get("major_mismatch", False),
    "issues": state.get("issues", []),
})
```

The event content must be JSON-serializable and may be ignored by older clients.

- [ ] **Step 6: Run graph tests**

Run: `python -m pytest tests/test_semantic_dialogue.py tests/test_multi_hazard.py -q -k "not test_report_writes_custom_chunks"`
Expected: PASS.

### Task 4: Task extraction and Java payload use canonical category strings

**Files:**

- Modify: `ai-module/tools/hazard_submit.py`
- Modify: `ai-module/tools/java_client.py` only if a field name changes
- Test: `ai-module/tests/test_hazard_taxonomy.py`

**Interfaces:**

`submit_from_history` keeps its return contract:

```text
created | ask_address | no_category | fail
```

The payload sent to Java:

```json
{
  "category": "fire/fire_equipment_fault",
  "address": "三明市万达广场对面",
  "description": "消防设施老旧、无法正常使用",
  "severity": 1
}
```

- [ ] **Step 1: Write failing extraction tests**

```python
def test_extractor_accepts_new_subcategories(monkeypatch):
    monkeypatch.setattr(
        hazard_submit._extractor,
        "_call_llm",
        lambda *_, **__: {"content": (
            '{"category":"fire/fire_equipment_fault",'
            '"address":"三明市万达广场对面","district":"三明市",'
            '"description":"消防设施老旧","severity":1}'
        )},
    )
    info = hazard_submit._extract([], "消防设施老旧")
    assert info["category"] == "fire/fire_equipment_fault"


def test_legacy_category_is_normalized_before_submit(monkeypatch):
    monkeypatch.setattr(
        hazard_submit._extractor,
        "_call_llm",
        lambda *_, **__: {"content": (
            '{"category":"消防设施","address":"三明市万达广场对面",'
            '"district":"三明市","description":"消防设施老旧","severity":1}'
        )},
    )
    info = hazard_submit._extract([], "消防设施老旧")
    assert info["category"] == "fire/fire_equipment_fault"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_hazard_taxonomy.py -q`
Expected: FAIL because the extractor still maps to four Chinese words.

- [ ] **Step 3: Replace the extractor prompt**

The prompt must list all canonical subcategory codes and labels, and must instruct the model to return `<major_code>/<subcategory_code>`.

- [ ] **Step 4: Normalize legacy output**

In `_extract`, call `normalize_taxonomy` for both old Chinese values and new canonical pairs. If normalization fails, set `category=""`.

- [ ] **Step 5: Run task extraction tests**

Run: `python -m pytest tests/test_hazard_taxonomy.py -q`
Expected: PASS.

### Task 5: API and Java passthrough of the selected major hint

**Files:**

- Modify: `ai-module/server.py`
- Modify: `safety-web/src/main/java/com/safety/web/controller/AiController.java`
- Modify: `safety-web/src/main/java/com/safety/web/service/AiService.java`
- Test: `ai-module/tests/test_semantic_dialogue.py`

**Interfaces:**

The Python endpoint accepts:

```text
selected_major_code: str = Form(None)
```

JSON compatibility:

```json
{
  "message": "...",
  "session_id": "...",
  "selected_major_code": "fire"
}
```

Java forwards the field to both the JSON and multipart calls.

- [ ] **Step 1: Write a failing Python passthrough test**

```python
def test_assistant_stream_passes_selected_major(monkeypatch, tmp_path):
    import asyncio
    import server
    from core.memory import WorkingMemory

    seen = {}
    mem = WorkingMemory(session_id="taxonomy-test")
    monkeypatch.setattr(server, "get_session", lambda _: mem)
    monkeypatch.setattr(server, "get_assistant", lambda: object())

    async def fake_stream(**kwargs):
        seen.update(kwargs)
        yield "done", ""

    monkeypatch.setattr(server, "assistant_graph_stream", fake_stream)

    class Request:
        async def is_disconnected(self):
            return False

    async def collect():
        response = await server.assistant_stream(
            Request(), message="消防设施老旧", session_id="taxonomy-test",
            selected_major_code="fire",
        )
        return [event async for event in response.body_iterator]

    asyncio.run(collect())
    assert seen["selected_major_code"] == "fire"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_semantic_dialogue.py -q`
Expected: FAIL because the endpoint has no selected-major parameter.

- [ ] **Step 3: Add the Python parameter**

Add the parameter to `assistant_stream`, parse it from JSON when present, and add it to the `run_stream_events` call.

- [ ] **Step 4: Add Java passthrough**

`AiController` accepts:

```java
@RequestParam(value = "selected_major_code", required = false) String selectedMajorCode
```

and passes it to both overloads of `assistantStream`.

`AiService.assistantStream(String message, String sessionId, Long userId)` adds the field to the JSON body.

`AiService.assistantStream(String message, String sessionId, Long userId, MultipartFile file)` adds:

```java
body.add("selected_major_code", selectedMajorCode == null ? "" : selectedMajorCode);
```

- [ ] **Step 5: Run Python tests and Java compile**

Run:

```text
python -m pytest tests/test_semantic_dialogue.py -q
mvn -q -pl safety-web -am -DskipTests compile
```

Expected: Python PASS; Java compile succeeds.

### Task 6: Frontend contract integration check

**Files:**

- No production files changed in this task.

- [ ] **Step 1: Verify the frontend payload**

Confirm the frontend sends:

```text
selected_major_code=fire
```

and that `不确定，自动判断` sends an empty value.

- [ ] **Step 2: Verify the taxonomy event**

Confirm the frontend can consume:

```json
{"type":"taxonomy","content":{"issues":[{"major_code":"fire","subcategory_code":"fire_equipment_fault"}]}}
```

and that older clients ignoring the event still render the report text.

### Task 7: Full verification and deployment

**Files:**

- No new files.

- [ ] **Step 1: Run the focused backend suite**

Run:

```text
python -m pytest tests/test_hazard_taxonomy.py tests/test_semantic_dialogue.py tests/test_agent_dialogue_optimization.py tests/test_adaptive_slots.py tests/test_multi_hazard.py tests/test_report_context.py -q -k "not test_report_writes_custom_chunks"
```

Expected: PASS.

- [ ] **Step 2: Run the Java build**

Run:

```text
mvn -q -pl safety-web -am -DskipTests compile
```

Expected: PASS.

- [ ] **Step 3: Deploy the AI files**

Back up and upload the changed `ai-module` files, compile them with the remote virtual environment, restart only the AI service, and verify:

```text
GET /api/ai/health
```

- [ ] **Step 4: Smoke test the screenshot flow**

Send:

```text
selected_major_code=fire
message=三明市万达广场对面的消防设施过于老旧，无法正常使用
```

Then send:

```text
message=消防栓和灭火器都有
```

Expected:

- The resolved issue is `fire/fire_equipment_fault`.
- The response eventually enters regulation and case retrieval.
- The report asks whether to create a task, or the assistant offers it after the report.
- The response does not ask a fire-lane blocker question.

- [ ] **Step 5: Smoke test a mismatched major**

Send:

```text
selected_major_code=municipal
message=消防设施老旧，无法正常使用
```

Expected:

- The backend resolves `fire/fire_equipment_fault`.
- `major_mismatch` is true.
- The user gets one lightweight confirmation, not a full questionnaire.

- [ ] **Step 6: Smoke test multi-hazard**

Send the fire-facility issue first, then:

```text
message=旁边还有一处危房，有裂缝
```

Expected:

- Both issues remain in the taxonomy event.
- The existing issue is not overwritten.
- Task creation can be offered for each complete issue.

## Self-Review

- Taxonomy codes are defined once and shared by planner, graph, task submission, and frontend contract.
- The four-category gate is removed.
- The selected major is a hint with mismatch handling.
- Multi-hazard issues are additive.
- Retrieval happens after hazard facts are complete for a report intent.
- Legacy records remain readable.
- The plan preserves the existing SSE event types and task-creation confirmation flow.

## Execution Result

Backend implementation and cloud deployment completed on 2026-09-23.

- Added core/hazard_taxonomy.py with canonical major/subcategory codes, labels, and legacy mapping.
- Planner now returns issue-level taxonomy, subcategory slots, selected_major_code, major_mismatch, and deterministic search policy.
- The graph emits an optional taxonomy SSE event, asks at most one question when critical facts are missing, and forces retrieval when a hazard issue is complete.
- Task submission accepts every canonical subcategory and stores major_code/subcategory_code in hazard_type.
- Python /api/ai/assistant/stream accepts selected_major_code; Java AiController and AiService forward it for both JSON and multipart requests.
- Focused Python regression: 92 passed, 1 pre-existing test deselected.
- Java compile and package succeeded.
- AI deployment: 20260923T211739; cloud health returns mimo-v2.6-flash.
- Java deployment SHA256: bd5d9fca988d80ab5e9eab86c75d3f4a9f8a498c410e731bb65d15185cd3910f; 8080 is listening and the deployed classes contain selected_major_code.
- Cloud smoke: the fire-facility flow resolved fire/fire_equipment_fault, entered regulation/case retrieval after the issue became complete, and asked whether to create a hazard task.

Java configuration note: the service must be started through start-backend.sh or with /home/ubuntu/.backend.env sourced. Starting the Jar without that environment causes Redis authentication to fail.

## Post-Deployment Fix: hazard_type Column Width

The first task-creation confirmation after deployment returned the global fallback message `系统繁忙，请稍后再试`.

Root cause: `tb_hazard.hazard_type` was `VARCHAR(20)`, while the canonical task value `fire/fire_equipment_fault` is 25 characters. MySQL raised `DataIntegrityViolationException: Data too long for column 'hazard_type'`, and the global handler converted it to the generic busy message.

Fix:

- Added `ai-module/db/migrate_hazard_type_length.sql`.
- Applied `ALTER TABLE tb_hazard MODIFY COLUMN hazard_type VARCHAR(64) NOT NULL` on the cloud database.
- Verified inside a transaction that `fire/fire_equipment_fault` inserts as 25 characters, then rolled the transaction back.
- Also fixed retry handling: a failed creation message no longer hides the earlier task-creation offer, so the user can say `需要` again after the database fix without starting a new session.
