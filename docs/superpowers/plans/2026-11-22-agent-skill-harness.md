# Agent Skill Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add eight canonical hazard Skills with metadata-only startup scanning, hybrid routing, on-demand body loading, and `active_skills` reuse in the fixed LangGraph workflow.

**Architecture:** Add `skill_route` before `understand`; routing uses locked/frontend/vision/keyword signals first and a metadata-only LLM fallback only for low-confidence text. `understand` and `report` load Skill bodies locally from `SkillRegistry`; only `active_skills`, route metadata, and versions enter checkpoint state.

**Tech Stack:** Python 3.11, PyYAML, pytest, existing LangGraph, existing OpenAI-compatible Agent wrapper.

## Global Constraints

- Skill codes equal the eight `HAZARD_TAXONOMY` major codes.
- Maximum active majors is 3; maximum active issues remains 3.
- `active_skills = locked_majors` once locked.
- Frontend explicit selection is a hard scope; auto mode lets backend route.
- Maximum three comma-separated selected major codes.
- YAML frontmatter never enters model prompts.
- `allowed_tools` is Harness-only and does not enter prompts.
- Full Skill bodies never enter Redis checkpoint state.
- No `focus_skill`; `issues[0]` is ordering/display only.
- Skill does not decide A-class completeness, report mode, or task creation.
- Java, MySQL, and SSE contracts do not change.
- Current shared tools keep behavior unchanged; no category-tool performance claim.

---

## File Structure

- Create: `ai-module/skills/README.md`
- Create: `ai-module/skills/{traffic,municipal,fire,building,utility,construction,elevator_special,environment_other}/SKILL.md`
- Create: `ai-module/core/skill_registry.py`
- Create: `ai-module/core/skill_router.py`
- Modify: `ai-module/requirements.txt`
- Modify: `ai-module/core/assistant_graph.py`
- Modify: `ai-module/core/dialogue_understanding.py`
- Modify: `ai-module/core/langgraph_state.py`
- Create: `ai-module/tests/test_skill_registry.py`
- Create: `ai-module/tests/test_skill_routing.py`
- Create: `ai-module/tests/test_skill_prompt_assembly.py`
- Create: `ai-module/tests/test_skill_graph_integration.py`
- Modify: `.frontend-work/src/views/HomeView.vue`

---

### Task 1: Add YAML Dependency And Create Eight Canonical Skills

**Files:**
- Modify: `ai-module/requirements.txt`
- Create: `ai-module/skills/README.md`
- Create: eight `ai-module/skills/<category>/SKILL.md`
- Test: `ai-module/tests/test_skill_registry.py`

**Interfaces:**
- Produces: eight directories whose names match `HAZARD_TAXONOMY` codes.

- [ ] **Step 1: Write failing structure test**

```python
from pathlib import Path
from core.hazard_taxonomy import MAJOR_LABELS

SKILL_ROOT = Path(__file__).parents[1] / "skills"


def test_all_major_skills_exist():
    for code in MAJOR_LABELS:
        assert (SKILL_ROOT / code / "SKILL.md").is_file(), code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skill_registry.py::test_all_major_skills_exist -q`

Expected: FAIL because `skills/` does not exist.

- [ ] **Step 3: Add dependency and create the eight files**

Add to `requirements.txt`:

```text
PyYAML>=6.0
```

Create `skills/README.md` with the frontmatter/body contract from the design. Create each `SKILL.md` with this exact category matrix:

| category | description seed | routing keywords |
|---|---|---|
| `traffic` | 交通与通行隐患 | 占道经营, 车辆占道, 盲道, 交通标志, 交通设施 |
| `municipal` | 市政设施隐患 | 井盖, 路面塌陷, 积水, 排水, 路灯杆 |
| `fire` | 消防安全隐患 | 消防通道, 消防设施, 消火栓, 灭火器, 防火门, 消防水源 |
| `building` | 建筑安全隐患 | 危房, 墙体开裂, 外立面脱落, 高空坠物, 违规搭建 |
| `utility` | 电气与燃气隐患 | 裸露电线, 私拉乱接, 配电箱, 燃气泄漏, 煤气味 |
| `construction` | 施工安全隐患 | 围挡, 安全警示, 脚手架, 深基坑, 临时用电 |
| `elevator_special` | 电梯与特种设备隐患 | 电梯困人, 电梯停运, 电梯异响, 超期未检 |
| `environment_other` | 环境与其他隐患 | 垃圾堆积, 污水, 异味, 其他安全隐患 |

Every body uses:

```markdown
## 适用范围
## 追问 SOP
## 法规引用约束
## 报告约束
## 建单注意事项
## 危险升级与禁止行为
```

`fire/SKILL.md` must match the full example in the approved design. The other seven use the same headings and list the canonical subcategories from `HAZARD_TAXONOMY`; they do not redefine A/B/C classes.

- [ ] **Step 4: Run structure test**

Run: `python -m pytest tests/test_skill_registry.py::test_all_major_skills_exist -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/requirements.txt ai-module/skills ai-module/tests/test_skill_registry.py
git commit -m "feat(ai): add canonical hazard skill files"
```

---
### Task 2: Implement SkillRegistry Metadata Scan And Body Loader

**Files:**
- Create: `ai-module/core/skill_registry.py`
- Test: `ai-module/tests/test_skill_registry.py`

**Interfaces:**
- Produces: `SkillRegistry(skills_dir, valid_tool_names)`
- Produces: `scan_metadata()`, `load_body(category)`, `load_section(category, heading)`, `resolve_tools(categories)`, `metadata_catalog()`

- [ ] **Step 1: Write failing registry tests**

```python
from pathlib import Path
import pytest
from core.skill_registry import SkillRegistry


def _write_skill(root: Path, code: str, **extra):
    path = root / code / "SKILL.md"
    path.parent.mkdir(parents=True)
    front = {"name": code, "category": code, "description": f"{code} description", "version": "1"}
    front.update(extra)
    lines = ["---"]
    for key, value in front.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines.extend(["---", f"# {code}", "## 报告约束", f"{code} report rule"])
    path.write_text("\n".join(lines), encoding="utf-8")


def test_scan_and_load(tmp_path):
    _write_skill(tmp_path, "fire", allowed_tools=["search_cases"])
    registry = SkillRegistry(tmp_path, valid_tool_names={"search_cases"})
    registry.scan_metadata()
    assert registry.get_metadata("fire")["category"] == "fire"
    assert "## 报告约束" not in registry.get_metadata("fire")
    assert "fire report rule" in registry.load_section("fire", "报告约束")


def test_duplicate_category_fails(tmp_path):
    _write_skill(tmp_path, "fire")
    _write_skill(tmp_path, "fire_copy", category="fire")
    registry = SkillRegistry(tmp_path, valid_tool_names={"search_cases"})
    with pytest.raises(ValueError, match="duplicate"):
        registry.scan_metadata()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_skill_registry.py -q -k "scan_and_load or duplicate"`

Expected: FAIL because registry is missing.

- [ ] **Step 3: Implement registry**

```python
from dataclasses import asdict, dataclass
from pathlib import Path
import yaml


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    category: str
    description: str
    allowed_tools: tuple[str, ...]
    routing_keywords: tuple[str, ...]
    version: str
    body_path: Path


class SkillRegistry:
    def __init__(self, skills_dir, valid_tool_names):
        self.skills_dir = Path(skills_dir)
        self.valid_tool_names = set(valid_tool_names)
        self._metadata = {}

    def scan_metadata(self):
        loaded = {}
        for path in sorted(self.skills_dir.glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            parts = text.split("---", 2)
            if len(parts) != 3 or not parts[2].strip():
                raise ValueError(f"invalid SKILL.md body: {path}")
            meta = yaml.safe_load(parts[1]) or {}
            code = str(meta.get("category") or "").strip()
            name = str(meta.get("name") or "").strip()
            if name != path.parent.name or code != path.parent.name:
                raise ValueError(f"name/category mismatch: {path}")
            if code in loaded:
                raise ValueError(f"duplicate category {code}")
            tools = tuple(str(item).strip() for item in (meta.get("allowed_tools") or []))
            unknown = set(tools) - self.valid_tool_names
            if unknown:
                raise ValueError(f"unknown tools for {code}: {sorted(unknown)}")
            loaded[code] = SkillMetadata(
                name=name,
                category=code,
                description=str(meta.get("description") or "").strip(),
                allowed_tools=tools,
                routing_keywords=tuple(meta.get("routing_keywords") or []),
                version=str(meta.get("version") or "1"),
                body_path=path,
            )
        self._metadata = loaded

    def get_metadata(self, category):
        return asdict(self._metadata[category])

    def load_body(self, category):
        meta = self._metadata[category]
        parts = meta.body_path.read_text(encoding="utf-8").split("---", 2)
        return parts[2].strip()

    def load_section(self, category, heading):
        body = self.load_body(category)
        marker = f"## {heading}"
        if marker not in body:
            raise KeyError(f"missing section {heading!r} in {category}")
        section = body.split(marker, 1)[1].split("\n## ", 1)[0]
        return section.strip()

    def resolve_tools(self, categories):
        names = []
        for category in categories or []:
            for name in self._metadata[category].allowed_tools:
                if name not in names:
                    names.append(name)
        return names

    def metadata_catalog(self):
        return [
            {"category": item.category, "description": item.description,
             "routing_keywords": list(item.routing_keywords)}
            for item in self._metadata.values()
        ]

    def versions_for(self, categories):
        return {code: self._metadata[code].version for code in categories or []}


def get_skill_registry(skills_dir, valid_tool_names):
    registry = SkillRegistry(skills_dir, valid_tool_names)
    registry.scan_metadata()
    return registry
```

Instantiate the singleton once in `assistant_graph.py` after `ASSISTANT_TOOLS` is defined:

```python
_skill_registry = get_skill_registry(
    Path(__file__).parents[1] / "skills",
    {tool.name for tool in ASSISTANT_TOOLS},
)
```

- [ ] **Step 4: Run registry tests**

Run: `python -m pytest tests/test_skill_registry.py -q -k "scan_and_load or duplicate"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/skill_registry.py ai-module/tests/test_skill_registry.py
git commit -m "feat(ai): add skill registry"
```

---

### Task 3: Implement Deterministic Keyword Router

**Files:**
- Create: `ai-module/core/skill_router.py`
- Test: `ai-module/tests/test_skill_routing.py`

**Interfaces:**
- Produces: `route_by_keywords(text, metadata_catalog, max_skills=3) -> dict`
- Produces: `route_skills(..., route_llm=None) -> dict`

- [ ] **Step 1: Write failing keyword tests**

```python
from core.skill_router import route_by_keywords

CATALOG = [
    {"category": "fire", "routing_keywords": ["消防通道", "消火栓"], "description": "消防"},
    {"category": "utility", "routing_keywords": ["配电箱", "燃气泄漏"], "description": "电气燃气"},
    {"category": "municipal", "routing_keywords": ["井盖", "路面积水"], "description": "市政"},
]


def test_single_and_multi_major_are_high_confidence():
    assert route_by_keywords("消防通道被私家车占了", CATALOG)["active_skills"] == ["fire"]
    result = route_by_keywords("消防通道被占，旁边配电箱冒火花", CATALOG)
    assert result["active_skills"] == ["fire", "utility"]


def test_weak_text_needs_llm():
    assert route_by_keywords("那个东西一直响，不太安全", CATALOG)["source"] == "need_llm"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_skill_routing.py -q -k "single_and_multi or weak_text"`

Expected: FAIL because router is missing.

- [ ] **Step 3: Implement keyword scoring**

```python
STRONG_WEIGHT = 3

def route_by_keywords(text, metadata_catalog, max_skills=3):
    normalized = normalize_text(text)
    candidates = []
    for meta in metadata_catalog:
        hits = [
            keyword for keyword in (meta.get("routing_keywords") or [])
            if normalize_text(keyword) and normalize_text(keyword) in normalized
        ]
        if not hits:
            continue
        candidates.append({
            "category": meta["category"],
            "score": STRONG_WEIGHT * len(hits),
            "has_strong": True,
        })
    if 1 <= len(candidates) <= max_skills:
        return {
            "active_skills": [item["category"] for item in candidates],
            "source": "keyword",
            "confidence": 0.9,
        }
    return {"active_skills": [], "source": "need_llm", "confidence": 0.0}
```

The final `route_skills()` order is locked majors, frontend selection, vision categories, keyword result, then injected `route_llm` fallback. It must enforce `max_skills=3`.

Define the production fallback callback in `skill_router.py`:

```python
_skill_router_agent = Agent(
    name="skill_route",
    system_prompt="你是城市安全隐患大类路由器，只返回 JSON。",
    tools=[],
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
    slot="small",
)


def route_llm_with_agent(text, metadata_catalog):
    prompt = (
        "只判断用户文本属于哪些城市安全隐患大类。"
        "只返回 JSON：{\"active_skills\": [...], \"confidence\": 0.0}。"
        "最多三个 category，不允许自造。\n"
        f"metadata={metadata_catalog}\n用户文本={text}"
    )
    response = _skill_router_agent._call_llm([{"role": "user", "content": prompt}])
    content = (response or {}).get("content") or ""
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end < start:
        return {}
    return json.loads(content[start:end + 1])
```

Import `json`, `Agent`, `MIMO_BASE_URL`, `MIMO_API_KEY`, and `MIMO_MODEL` into `skill_router.py`. Export `_skill_route_llm = route_llm_with_agent` for `assistant_graph.py`.

- [ ] **Step 4: Run routing tests**

Run: `python -m pytest tests/test_skill_routing.py -q -k "single_and_multi or weak_text"`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/skill_router.py ai-module/tests/test_skill_routing.py
git commit -m "feat(ai): add deterministic skill keyword router"
```

---
### Task 4: Add Metadata-Only LLM Fallback Routing

**Files:**
- Modify: `ai-module/core/skill_router.py`
- Test: `ai-module/tests/test_skill_routing.py`

**Interfaces:**
- Produces: `route_skills(text, metadata_catalog, selected_major_codes, locked_majors, vision_categories, route_llm=None) -> dict`

- [ ] **Step 1: Write failing fallback tests**

```python
from core.skill_router import route_skills


def test_frontend_and_locked_skip_llm():
    calls = []
    result = route_skills(
        "小区有隐患", CATALOG,
        selected_major_codes=["fire"], locked_majors=[],
        vision_categories=[], route_llm=lambda *a, **k: calls.append(1),
    )
    assert result["active_skills"] == ["fire"]
    assert result["source"] == "frontend"
    assert calls == []


def test_weak_keyword_calls_llm_and_caps_three():
    result = route_skills(
        "那个东西一直响", CATALOG,
        selected_major_codes=[], locked_majors=[], vision_categories=[],
        route_llm=lambda text, catalog: {
            "active_skills": ["fire", "utility", "municipal", "traffic"],
            "confidence": 0.8,
        },
    )
    assert result["active_skills"] == ["fire", "utility", "municipal"]
    assert result["source"] == "llm"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_skill_routing.py -q -k "skip_llm or weak_keyword"`

Expected: FAIL because `route_skills()` is incomplete.

- [ ] **Step 3: Implement priority routing**

```python
def route_skills(text, metadata_catalog, selected_major_codes=None,
                 locked_majors=None, vision_categories=None, route_llm=None,
                 max_skills=3):
    if locked_majors:
        return {"active_skills": locked_majors[:max_skills],
                "source": "locked", "confidence": 1.0}
    selected = [item for item in (selected_major_codes or []) if item]
    if selected:
        return {"active_skills": selected[:max_skills],
                "source": "frontend", "confidence": 1.0}
    vision = [item for item in (vision_categories or []) if item]
    if vision:
        return {"active_skills": vision[:max_skills],
                "source": "vision", "confidence": 0.9}
    keyword = route_by_keywords(text, metadata_catalog, max_skills=max_skills)
    if keyword["active_skills"]:
        return keyword
    if route_llm:
        llm = route_llm(text, metadata_catalog) or {}
        skills = [item for item in (llm.get("active_skills") or [])
                  if item in {meta["category"] for meta in metadata_catalog}]
        if skills and float(llm.get("confidence") or 0.0) >= 0.7:
            return {"active_skills": skills[:max_skills],
                    "source": "llm",
                    "confidence": float(llm.get("confidence") or 0.0)}
    return {"active_skills": [], "source": "fallback", "confidence": 0.0}
```

- [ ] **Step 4: Run all router tests**

Run: `python -m pytest tests/test_skill_routing.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/skill_router.py ai-module/tests/test_skill_routing.py
git commit -m "feat(ai): add metadata-only skill routing fallback"
```

---

### Task 5: Add Skill State And `skill_route` Node

**Files:**
- Modify: `ai-module/core/langgraph_state.py`
- Modify: `ai-module/core/assistant_graph.py`
- Test: `ai-module/tests/test_skill_graph_integration.py`

**Interfaces:**
- Consumes: `selected_major_codes`, `vision_summary`, `locked_majors`
- Produces: `active_skills`, `skill_route_source`, `skill_route_confidence`, `skill_versions`

- [ ] **Step 1: Write failing graph tests**

```python
import core.assistant_graph as ag


def test_skill_route_reuses_locked_majors(monkeypatch):
    monkeypatch.setattr(ag, "_skill_route_llm", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called")))
    out = ag.skill_route({
        "messages": [],
        "locked_majors": ["fire", "utility"],
        "selected_major_codes": [],
        "vision_summary": "",
    })
    assert out["active_skills"] == ["fire", "utility"]
    assert out["skill_route_source"] == "locked"


def test_skill_route_caps_frontend_selection():
    out = ag.skill_route({
        "messages": [],
        "locked_majors": [],
        "selected_major_codes": ["fire", "utility", "municipal", "traffic"],
        "vision_summary": "",
    })
    assert out["active_skills"] == ["fire", "utility", "municipal"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_skill_graph_integration.py -q -k skill_route`

Expected: FAIL because the node and state fields are missing.

- [ ] **Step 3: Add state fields and node**

Add to `AssistantState`:

```python
active_skills: list[str]
skill_route_source: str
skill_route_confidence: float
skill_versions: dict[str, str]
```

Add node:

```python
def _vision_major_codes(vision_summary):
    value = str(vision_summary or "")
    found = []
    for label, code in MAJOR_LABEL_TO_CODE.items():
        if label in value or code in value:
            found.append(code)
    return list(dict.fromkeys(found))[:MAX_ACTIVE_MAJORS]


def skill_route(state):
    selected = _major_codes(state.get("selected_major_codes") or state.get("selected_major_code"))
    result = _skill_router.route_skills(
        text=_latest_user_text(state),
        metadata_catalog=_skill_registry.metadata_catalog(),
        selected_major_codes=selected,
        locked_majors=_locked_majors(state),
        vision_categories=_vision_major_codes(state.get("vision_summary") or ""),
        route_llm=_skill_route_llm,
    )
    return {
        "active_skills": result["active_skills"],
        "skill_route_source": result["source"],
        "skill_route_confidence": result["confidence"],
        "skill_versions": _skill_registry.versions_for(result["active_skills"]),
    }
```

In `build_graph()`:

```python
g.add_node("skill_route", skill_route)
g.add_edge("begin_turn", "skill_route")
g.add_edge("skill_route", "understand")
```

- [ ] **Step 4: Run graph integration tests**

Run: `python -m pytest tests/test_skill_graph_integration.py -q -k skill_route`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/langgraph_state.py ai-module/core/assistant_graph.py ai-module/tests/test_skill_graph_integration.py
git commit -m "feat(ai): route active skills before understand"
```

---

### Task 6: Inject Skill Bodies Into understand Prompt

**Files:**
- Modify: `ai-module/core/dialogue_understanding.py`
- Modify: `ai-module/core/assistant_graph.py`
- Test: `ai-module/tests/test_skill_prompt_assembly.py`

**Interfaces:**
- Consumes: `active_skills`
- Produces: planner messages containing only active Skill bodies

- [ ] **Step 1: Write failing prompt test**

```python
from langchain_core.messages import HumanMessage
from core.dialogue_understanding import build_planner_messages


def test_prompt_contains_only_active_skill_body():
    built = build_planner_messages(
        [HumanMessage(content="消防通道被占，旁边配电箱冒火花")],
        skill_bodies={"fire": "FIRE BODY", "utility": "UTILITY BODY"},
    )
    combined = "\n".join(item["content"] for item in built)
    assert "FIRE BODY" in combined and "UTILITY BODY" in combined
    assert "allowed_tools" not in combined
    assert "routing_keywords" not in combined
    assert "MUNICIPAL BODY" not in combined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skill_prompt_assembly.py -q`

Expected: FAIL because skill bodies are not accepted.

- [ ] **Step 3: Extend planner builder and understand call**

Add `skill_bodies: dict[str, str] | None = None` to `build_planner_messages()` and `understand()`. Insert one system block per active Skill body before dialog history:

```python
for code, body in (skill_bodies or {}).items():
    if body.strip():
        out.append({"role": "system", "content": f"【Skill: {code}】\n{body.strip()}"})
```

In `assistant_graph.understand()`, load bodies locally:

```python
skill_bodies = {
    code: _skill_registry.load_body(code)
    for code in (state.get("active_skills") or [])
}
```

Pass `skill_bodies=skill_bodies` to `_understand_plan()`. Do not return skill bodies in the node update.

- [ ] **Step 4: Run prompt and dialogue tests**

Run: `python -m pytest tests/test_skill_prompt_assembly.py tests/test_semantic_dialogue.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/dialogue_understanding.py ai-module/core/assistant_graph.py ai-module/tests/test_skill_prompt_assembly.py
git commit -m "feat(ai): inject active skill bodies into understanding"
```

---

### Task 7: Reuse Active Skills In Retrieval And Report

**Files:**
- Modify: `ai-module/core/assistant_graph.py`
- Test: `ai-module/tests/test_skill_graph_integration.py`

**Interfaces:**
- Consumes: `active_skills`
- Produces: effective tool list and report guidance

- [ ] **Step 1: Write failing integration test**

```python
import core.assistant_graph as ag


def test_retrieval_uses_only_allowed_tools(monkeypatch):
    monkeypatch.setattr(ag._skill_registry, "resolve_tools", lambda skills: ["search_regulation"])
    state = {
        "categories": ["fire_lane_blocked"],
        "category_slots": {},
        "retrieval_keyword_override": {},
        "active_skills": ["fire"],
    }
    sends = ag.plan_retrieval(state)
    assert {send.arg["tool"] for send in sends} == {"search_regulation"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skill_graph_integration.py::test_retrieval_uses_only_allowed_tools -q`

Expected: FAIL because retrieval ignores `active_skills`.

- [ ] **Step 3: Implement tool intersection and report guidance**

In `plan_retrieval()`:

```python
allowed = _skill_registry.resolve_tools(state.get("active_skills") or [])
allowed_retrieval = [name for name in _RESULT_FIELD if name in allowed]
```

Use `allowed_retrieval` instead of iterating `_RESULT_FIELD` directly. If no Skills are active, fall back to the current `_RESULT_FIELD` keys.

In `report()` append active Skill report sections:

```python
skill_report_rules = "\n\n".join(
    _skill_registry.load_section(code, "报告约束")
    for code in (state.get("active_skills") or [])
)
```

Add `skill_report_rules` to `ctx` only when non-empty.

- [ ] **Step 4: Run integration and report tests**

Run: `python -m pytest tests/test_skill_graph_integration.py tests/test_report_sections.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai-module/core/assistant_graph.py ai-module/tests/test_skill_graph_integration.py
git commit -m "feat(ai): reuse active skills in retrieval and report"
```

---
### Task 8: Update Frontend Major Selector To Multi-Select With Cap Three

**Files:**
- Modify: `.frontend-work/src/views/HomeView.vue`

**Interfaces:**
- Consumes: SSE `taxonomy.locked_majors`
- Produces: `selected_major_code=fire,utility,municipal`

- [ ] **Step 1: Write failing frontend expectation**

Add this comment-backed assertion to the existing frontend test/manual checklist:

```text
Select fire, utility, municipal.
Attempt to select traffic.
Traffic remains unselected and a "最多选择 3 个领域" hint is shown.
Submit and verify FormData contains selected_major_code=fire,utility,municipal.
```

- [ ] **Step 2: Run the current frontend build**

Run: `npm run build` in the frontend working directory.

Expected: current build passes before edits.

- [ ] **Step 3: Replace single selection state**

In `HomeView.vue`:

```javascript
const selectedMajorCodes = ref([])
const maxSelectedMajors = 3

function toggleMajor(code) {
  if (majorLocked.value) return
  if (!code) {
    selectedMajorCodes.value = []
    return
  }
  const current = selectedMajorCodes.value
  if (current.includes(code)) {
    selectedMajorCodes.value = current.filter(item => item !== code)
    return
  }
  if (current.length >= maxSelectedMajors) {
    majorLimitHint.value = '最多选择 3 个领域'
    return
  }
  selectedMajorCodes.value = [...current, code]
}
```

Update the selector chips to compare against `selectedMajorCodes.includes(m.code)` and send:

```javascript
const majorCodes = selectedMajorCodes.value.slice(0, 3)
if (majorCodes.length) {
  fd.append('selected_major_code', majorCodes.join(','))
}
```

Update labels and the clear button to derive from `selectedMajorCodes`. Preserve the existing `majorLocked` behavior.

- [ ] **Step 4: Run frontend build and manual selection check**

Run: `npm run build`

Expected: PASS. Manually verify the four-selection case keeps only three.

- [ ] **Step 5: Commit**

```bash
git add .frontend-work/src/views/HomeView.vue
git commit -m "feat(ui): allow up to three hazard majors"
```

---

### Task 9: Full Regression And Routing Evaluation

**Files:**
- Test: all new and existing AI tests
- Create: no new fixture; routing cases live inline in `tests/test_skill_routing.py`

**Interfaces:**
- Validates the complete Skill flow

- [ ] **Step 1: Add routing cases covering positives and negatives**

Include at least these cases in `tests/test_skill_routing.py`:

```python
CASES = [
    ("消防通道被私家车占用", ["fire"]),
    ("消防通道被占，配电箱冒火花", ["fire", "utility"]),
    ("井盖缺失，旁边路灯杆歪了", ["municipal"]),
    ("电梯困人且有异响", ["elevator_special"]),
    ("那个东西歪了，我觉得不安全", None),
    ("消防员招聘条件是什么", []),
]
```

`None` means LLM fallback expected; `[]` means no Skill activated.

- [ ] **Step 2: Run the full AI test suite**

Run: `python -m pytest tests -q`

Expected: PASS with no new failures and no regression in task-gate, uncertainty, checkpoint, report, or multi-hazard tests.

- [ ] **Step 3: Run a manual token/latency comparison**

Run five text-only first-turn conversations with and without Skill loading. Record:

```text
input token estimate
loaded skill count
route source
route latency
understand latency
retrieval latency
```

Expected: active Skill bodies reduce unrelated taxonomy context; low-confidence text is the only path that adds one metadata-only LLM call.

- [ ] **Step 4: Verify checkpoint payload**

Create a two-turn session, inspect the Redis checkpoint or in-memory state, and confirm:

```text
active_skills exists
skill_versions exists
skill_route_source exists
no full Skill Markdown exists
```

- [ ] **Step 5: Commit**

```bash
git add ai-module/tests .frontend-work/src/views/HomeView.vue
git commit -m "test: cover skill routing and regression flow"
```

---

## Self-Review Checklist

- [ ] Eight canonical Skill files exist and match taxonomy codes.
- [ ] Registry startup scan does not cache full bodies.
- [ ] Frontmatter and `allowed_tools` never enter model prompts.
- [ ] Locked majors, frontend selection, vision, keyword, and LLM fallback are ordered correctly.
- [ ] Maximum active majors and active issues remain three.
- [ ] `skill_route` executes before `understand`.
- [ ] `understand` loads Skill bodies locally and does not persist them.
- [ ] Retrieval falls back to current tools if no Skill is active.
- [ ] Report uses only the `报告约束` section.
- [ ] No `focus_skill` is added.
- [ ] SSE, Java, MySQL, and task-gate contracts remain unchanged.
- [ ] Frontend can send up to three comma-separated major codes.
- [ ] Full pytest suite and frontend build pass.