# 多隐患（Multi-Hazard）Agent 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把新版 AI 助手从「单类别槽位」升级为「多隐患并行补齐 + 一次检索 + 合并报告」。

**Architecture:** 在现有 LangGraph `StateGraph`（route→clarify→search→report）上扩展状态为 `categories/category_slots/active_category/category_index`。识别多类别用 `_infer_categories`（关键词打分 + LLM 兜底），「新增/切换」分流用 `meta_clarify` 追问 + `_merge_categories`；**抽槽在 route 节点**（每个新用户消息都从 route 进），**生成问题在 clarify 节点**（代码选槽、LLM 措辞）。`missing` 为全局并集列表（带 `{cat}_{key}` 前缀），抽槽后**重算**而非删除；串台信息先登记类别再按 `CROSS_SLOT_MAP` 分流。

**Tech Stack:** Python 3.13 / LangGraph `>=1.2` / langchain-core `>=1.0` / pytest / SSE 真流式（asyncio.Queue + checkpointer）。

## Global Constraints

- 项目根：`E:\java\newProject\ai-module`（Python 工作目录）。
- 主模型 `MIMO_MODEL = "mimo-v2.5-pro"`（对话文本），备 `MIMO_MODEL_BACKUP = "mimo-v2.5"`（全模态/视觉）；降级逻辑在 `Agent._call_llm`，不在这里改。
- **抽槽是 LLM 调用，测试必须 `monkeypatch` 掉**，不能发真实请求。已用 `AGENT._llm` 单例；测试用 `monkeypatch.setattr(ag, "_llm_extract_slots", fake)` / `_llm_phrase`。
- **保留兼容字段**：`category`（=active_category 别名）、`slots`（=当前 active_category 的 `category_slots[active_category]` 别名），让现有 `test_adaptive_slots.py` 的 13 个用例继续通过（单类别行为不变），新增字段只在多类别时启用。
- `SLOT_SCHEMAS` 里中文键（类别名）是唯一 id，不得改名；`CROSS_SLOT_MAP` 只放语义真正等价的对，宁缺毋滥。
- 每轮 `clarify` 最多触发 2 次 LLM（措辞 1 + 抽槽 1），澄清上限 `MAX_CLARIFY=3`；到上限 / `clarify_stopped` 放行检索。
- 状态序列化：`AssistantState` 只能是 msgpack 可序列化类型，**不能放函数/回调**；`emit` 已放 `threading.local()`（`assistant_graph.py` 的 `_stream_local`），本次不改。

---

## 文件结构

| 文件 | 职责 | 改动 |
|---|---|---|
| `core/langgraph_state.py` | 定义 `AssistantState` 状态字段 | 新增多隐患字段 |
| `core/assistant_graph.py` | 图 + `SLOT_SCHEMAS` + 类别函数 + 节点 | 重写 `route`/`clarify`/`search`/`report`，加 `meta_clarify` |
| `core/assistant_agent.py` | 系统提示 | 补充多隐患 + 防串类别说明 |
| `tests/test_multi_hazard.py` | 多隐患新用例 | 新建 |
| `tests/test_adaptive_slots.py` | 旧单类别用例 | 仅微调 import（若必要） |

---

### Task 1: 状态结构扩展（`langgraph_state.py`）

**Files:**
- Modify: `core/langgraph_state.py`
- Test: `tests/test_multi_hazard.py`（新建文件，本 task 只加一个默认字段构造测试）

**Interfaces:**
- Consumes: 无。
- Produces: `AssistantState` 新增字段（后面任务全部依赖）：`categories: list[str]`、`active_category: str`、`category_index: int`、`category_slots: dict[str, dict]`、`category_results: dict[str, dict]`、`missing: list[str]`、`relationship: str`、`clarify_count: int`、`clarify_stopped: bool`。保留旧字段 `category`、`slots`。

- [ ] **Step 1: 写失败的默认字段测试**

```python
# tests/test_multi_hazard.py
from core.langgraph_state import AssistantState

def test_state_has_multi_hazard_fields():
    s: AssistantState = {
        "categories": ["消防通道", "占道"],
        "active_category": "消防通道",
        "category_index": 0,
        "category_slots": {"消防通道": {}, "占道": {}},
        "category_results": {},
        "missing": ["消防通道_blocker", "占道_blocked"],
        "relationship": "add",
        "clarify_count": 0,
        "clarify_stopped": False,
    }
    assert s["categories"][0] == "消防通道"
    assert s["missing"][0] == "消防通道_blocker"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py::test_state_has_multi_hazard_fields -v`
Expected: FAIL（`KeyError` 不会出现，因为 TypedDict 只做提示；但导入 `AssistantState` 需成功）。本步如果导入失败则失败，导入成功则直接过。

- [ ] **Step 3: 实现状态字段**

```python
# core/langgraph_state.py
from typing import TypedDict

class AssistantState(TypedDict, total=False):
    session_id: str                     # checkpointer 的 thread_id
    messages: list
    # 旧兼容字段（单类别路径仍用）
    slots: dict[str, str]
    category: str
    # 多隐患字段
    categories: list[str]               # 有序、去重
    active_category: str                # 当前正在补哪张表
    category_index: int                 # 指向 categories 下标
    category_slots: dict[str, dict]     # {类别: {slot_key: value}}
    category_results: dict[str, dict]   # {类别: {regulation, case}}
    missing: list[str]                  # 全局并集，形如 "{cat}_{key}"
    relationship: str                   # "add"|"switch"|""
    clarify_count: int
    clarify_stopped: bool
    vision_summary: str
    regulation_results: str
    case_results: str
    draft_report: str
    grade_feedback: str
    attempts: int
    route_decision: str
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py::test_state_has_multi_hazard_fields -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/langgraph_state.py ai-module/tests/test_multi_hazard.py
git commit -m "feat(multi-hazard): extend AssistantState with categories/category_slots/missing"
```

---

### Task 2: 类别数据 + 纯函数（`_infer_categories`、`_merge_categories`、`CATEGORY_PRIORITY`、`CROSS_SLOT_MAP`、critical 标注）

**Files:**
- Modify: `core/assistant_graph.py`（`SLOT_SCHEMAS` 加 critical、新增 `CATEGORY_PRIORITY`、`CROSS_SLOT_MAP`、`_infer_categories`、`_merge_categories`、`_score_category`）
- Test: `tests/test_multi_hazard.py`

**Interfaces:**
- Consumes: 现有 `_infer_category`/`_llm_classify`/`_CATEGORY_KEYWORDS`。
- Produces: `_infer_categories(text, vision_category="") -> list[str]`（有序去重，按优先级）；`_merge_categories(new_cats, old_cats) -> list[str]`；`CATEGORY_PRIORITY: dict`；`CROSS_SLOT_MAP: dict[tuple, tuple]`。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_multi_hazard.py 追加
import core.assistant_graph as ag

def test_infer_categories_two_hits_no_llm(monkeypatch):
    monkeypatch.setattr(ag, "_llm_classify", lambda t: (_ for _ in ()).throw(AssertionError("双命中不该调 LLM")))
    cats = ag._infer_categories("消防被堵，长期占道")
    assert "消防通道" in cats and "占道" in cats
    # 优先级消防(1) < 占道(5)，消防应排前
    assert cats.index("消防通道") < cats.index("占道")

def test_merge_categories_dedupe_and_sort():
    merged = ag._merge_categories(["占道", "消防通道"], ["占道", "危房"])
    assert merged[0] == "危房"          # 优先级 0 最前
    assert merged.count("占道") == 1
    assert merged[-1] == "占道"

def test_critical_flag_present():
    # 高空坠物 target/exposure 应为非 critical
    slots = ag.SLOT_SCHEMAS["高空坠物"]
    d = {s.key: s.critical for s in slots}
    assert d["source"] is True and d["target"] is False and d["exposure"] is False

def test_cross_slot_map_has_blocked_to_impact():
    assert ag.CROSS_SLOT_MAP.get(("占道", "blocked")) == ("消防通道", "impact")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py -v`
Expected: FAIL（`_infer_categories`/`_merge_categories`/`CROSS_SLOT_MAP` 不存在）

- [ ] **Step 3: 实现**

```python
# core/assistant_graph.py 顶部常量区（SLOT_SCHEMAS 之后）
CATEGORY_PRIORITY = {
    "危房": 0, "消防通道": 1, "高空坠物": 2, "电气": 3,
    "施工": 4, "占道": 5, "井盖/道路": 6, "其他": 9,
}

# SLOT_SCHEMAS 里把可有可无槽标 critical=False（示例，按 §3 设计全文改）
#   "消防通道": [Slot("blocker",...,critical=True), Slot("persistence",...,critical=True), Slot("impact",...,critical=False)]
#   "高空坠物": [Slot("source",...,critical=True), Slot("target",...,critical=False), Slot("exposure",...,critical=False)]
#   "施工":    [Slot("site",...,critical=True), Slot("safety",...,critical=True), Slot("impact",...,critical=False)]

CROSS_SLOT_MAP = {
    ("占道", "blocked"): ("消防通道", "impact"),
    ("占道", "persistence"): ("消防通道", "persistence"),
}

def _score_category(cat: str, text: str) -> int:
    return sum(1 for k in _CATEGORY_KEYWORDS.get(cat, ()) if k in text)

def _sort_by_priority(cats: list) -> list:
    return sorted(cats, key=lambda c: CATEGORY_PRIORITY.get(c, 9))

def _infer_categories(text: str, vision_category: str = "") -> list[str]:
    if vision_category:
        mapped = _VISION_CATEGORY_MAP.get(vision_category)
        if mapped:
            return [mapped]
    hits = [c for c in CATEGORIES if _score_category(c, text) > 0]
    if hits:
        return _sort_by_priority(dedupe(hits))
    return [_llm_classify(text) or "其他"]

def _merge_categories(new_cats, old_cats) -> list[str]:
    return _sort_by_priority(dedupe(list(old_cats or []) + list(new_cats or [])))
```

> `dedupe` 用 `list(dict.fromkeys(...))` 保序去重。若文件已有 `dedupe` 直接用，否则在文件加一个小工具函数。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/assistant_graph.py ai-module/tests/test_multi_hazard.py
git commit -m "feat(multi-hazard): add category inference, merge, priority, cross-slot map, critical flags"
```
---

### Task 3: `missing` 重算 + 槽位合并 + 分流转发（纯函数）

**Files:**
- Modify: `core/assistant_graph.py`
- Test: `tests/test_multi_hazard.py`

**Interfaces:**
- Consumes: `SLOT_SCHEMAS`、`CATEGORY_PRIORITY`、`_CATEGORY_KEYWORDS`、`CROSS_SLOT_MAP`。
- Produces:
  - `rebuild_missing(categories, category_slots) -> list[str]`（仅 critical 且为空，带 `{cat}_{key}` 前缀，按优先级排序）
  - `add_category_slots(state_categories, category_slots, extracted) -> dict`（把抽槽结果按类别合并进 `category_slots`）
  - `_relocate(value, from_cat, key, categories, category_slots) -> dict`（分流：返回新的 `categories` 和 `category_slots`，或 None）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_multi_hazard.py 追加
def test_rebuild_missing_only_critical_and_empty():
    slots = {"消防通道": {"blocker": "杂物"}}   # persistence 缺、impact 非 critical
    miss = ag.rebuild_missing(["消防通道"], slots)
    assert "消防通道_persistence" in miss
    assert "消防通道_blocker" not in miss        # 已填
    assert "消防通道_impact" not in miss         # critical=False 不进 missing

def test_add_category_slots_merges_per_cat():
    state_cats = ["消防通道", "占道"]
    cs = {"消防通道": {}, "占道": {}}
    extracted = {"消防通道": {"impact": "影响通行"}, "占道": {"persistence": "长期"}}
    out = ag.add_category_slots(state_cats, cs, extracted)
    assert out["消防通道"]["impact"] == "影响通行"
    assert out["占道"]["persistence"] == "长期"

def test_relocate_redirects_not_drops():
    cats = ["占道", "消防通道"]
    cs = {"占道": {"blocked": "消防通道被堵"}, "消防通道": {}}
    out = ag._relocate("消防通道被堵", "占道", "blocked", cats, cs)
    # 命中消防通道类别、已有映射 → 转发到 impact
    assert "消防通道" in out["categories"]
    assert out["category_slots"]["消防通道"].get("impact") is not None
    # 原占道应该清掉这个污染值
    assert "blocked" not in out["category_slots"].get("占道", {})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py -k "rebuild or add_category or relocate" -v`
Expected: FAIL（函数不存在）

- [ ] **Step 3: 实现**

```python
# core/assistant_graph.py
def rebuild_missing(categories, category_slots) -> list[str]:
    out = []
    for cat in categories:
        for s in SLOT_SCHEMAS.get(cat, []):
            if s.critical and not (category_slots.get(cat, {}).get(s.key) or "").strip():
                out.append(f"{cat}_{s.key}")
    return _sort_by_priority(out)

def add_category_slots(state_categories, category_slots, extracted) -> dict:
    cs = {k: dict(v) for k, v in (category_slots or {}).items()}
    for cat, slots in (extracted or {}).items():
        if cat not in state_categories:
            continue
        cs.setdefault(cat, {})
        for k, v in slots.items():
            if v and str(v).strip():
                cs[cat][k] = v
    return cs

def _detect_other_cats(value: str, from_cat: str) -> list[str]:
    if not value:
        return []
    return [c for c in CATEGORIES if c != from_cat
            and any(k in value for k in _CATEGORY_KEYWORDS.get(c, ()))]

def _relocate(value, from_cat, key, categories, category_slots):
    hit_cats = _detect_other_cats(value, from_cat)
    if not hit_cats:
        return None
    new_cats = _merge_categories(hit_cats, categories)
    cs = {k: dict(v) for k, v in (category_slots or {}).items()}
    target = CROSS_SLOT_MAP.get((from_cat, key))
    if target and target[0] in hit_cats:
        tcat, tkey = target
        cs.setdefault(tcat, {})[tkey] = value
        # 从源筐清掉污染值
        if from_cat in cs and key in cs[from_cat]:
            del cs[from_cat][key]
    return {"categories": new_cats, "category_slots": cs}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py -k "rebuild or add_category or relocate" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/assistant_graph.py ai-module/tests/test_multi_hazard.py
git commit -m "feat(multi-hazard): add missing rebuild, per-cat slot merge, relocate"
```

---

### Task 4: `route` 重构（多类别识别 + 抽槽 + 重算 missing + can_search）

**Files:**
- Modify: `core/assistant_graph.py`（`route`、`route_decider`）
- Test: `tests/test_multi_hazard.py`

**Interfaces:**
- Consumes: `_infer_categories`、`_merge_categories`、`rebuild_missing`、`_llm_extract_slots`（新增 LLM 抽槽函数，测试 monkeypatch）、`add_category_slots`、`_relocate`。
- Produces: 更新后的 state 字段 `categories/active_category/category_index/category_slots/missing/route_decision`。

**关键约定：抽槽在 `route` 节点做**（每个新用户消息都从 route 进）。新增 LLM 抽槽函数 `_llm_extract_slots(message, categories, category_slot_keys) -> dict{cat:{key:val}}`，测试用 monkeypatch 替换。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_multi_hazard.py 追加
def test_route_multi_hazard_extract_and_rebuild(monkeypatch):
    monkeypatch.setattr(ag, "_infer_categories", lambda t, v="": ["消防通道", "占道"])
    monkeypatch.setattr(ag, "_llm_extract_slots",
        lambda msg, cats, keys: {"消防通道": {"impact": "影响通行"}, "占道": {"persistence": "长期"}})
    st = {"messages": [HumanMessage(content="消防被堵，长期占道")],
          "categories": ["消防通道", "占道"],
          "active_category": "消防通道", "category_index": 0,
          "category_slots": {"消防通道": {}, "占道": {}},
          "missing": ["消防通道_blocker", "消防通道_persistence", "占道_blocked"],
          "clarify_count": 0, "clarify_stopped": False, "vision_summary": ""}
    up = ag.route(st)
    assert up["category_slots"]["占道"]["persistence"] == "长期"   # 抽槽合并
    assert "占道_persistence" not in up["missing"]                 # 重算后已填
    assert "占道_blocked" in up["missing"]                         # 仍缺

def test_route_can_search_when_missing_empty(monkeypatch):
    monkeypatch.setattr(ag, "_infer_categories", lambda t, v="": ["占道"])
    monkeypatch.setattr(ag, "_llm_extract_slots",
        lambda msg, cats, keys: {"占道": {"behavior": "占道", "persistence": "长期", "blocked": "完全堵死"}})
    st = {"messages": [HumanMessage(content="长期占着盲道完全堵死")],
          "categories": ["占道"], "active_category": "占道", "category_index": 0,
          "category_slots": {}, "missing": ["占道_behavior","占道_persistence","占道_blocked"],
          "clarify_count": 0, "clarify_stopped": False, "vision_summary": ""}
    up = ag.route(st)
    assert up["missing"] == []
    assert up["route_decision"] == "search"

def test_route_can_search_at_limit(monkeypatch):
    monkeypatch.setattr(ag, "_infer_categories", lambda t, v="": ["占道"])
    monkeypatch.setattr(ag, "_llm_extract_slots", lambda msg, cats, keys: {})   # 没抽到
    st = {"messages": [HumanMessage(content="占道")], "categories": ["占道"],
          "active_category": "占道", "category_index": 0, "category_slots": {},
          "missing": ["占道_behavior"], "clarify_count": 3, "clarify_stopped": False,
          "vision_summary": ""}
    up = ag.route(st)
    assert up["route_decision"] == "search"      # 到上限放行
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py -k "route_multi or route_can_search" -v`
Expected: FAIL（`route` 仍返回旧字段/单类别）

- [ ] **Step 3: 实现**

```python
# core/assistant_graph.py —— 新增抽槽（LLM）
def _llm_extract_slots(message: str, categories: list[str], category_slot_keys: dict) -> dict:
    prompt = (
        "请从用户消息中，按类别抽取能填的槽位。只返回 JSON，没提到的填空字符串。\n"
        "类别槽位定义：\n" +
        "\n".join(f"{cat}: {keys}" for cat, keys in category_slot_keys.items()) +
        f"\n用户消息：{message}"
    )
    try:
        resp = _llm._call_llm([SystemMessage(content="你是槽位抽取器"), HumanMessage(content=prompt)], cancellation=None)
        content = (resp.get("content") or "").strip()
        return json.loads(content)
    except Exception:
        return {}

# core/assistant_graph.py —— route 重构
def route(state: AssistantState) -> dict:
    text = _join_text(state)
    vision_cat = _extract_vision_category(state.get("vision_summary", ""))
    new_cats = _infer_categories(text, vision_cat)
    old_cats = state.get("categories", []) or ([""] if state.get("category") else [])
    cats = _merge_categories(new_cats, old_cats if old_cats != [""] else [])

    category_slots = {k: dict(v) for k, v in (state.get("category_slots") or {}).items()}
    # 类别切换只留公共槽（保留旧逻辑：从 active_category 切到新 active 时清专属）
    # 这里简化：仅当只有一个新增类别且和当前 active 不同才清；多类别时不清。
    slot_keys = {c: [s.key for s in SLOT_SCHEMAS.get(c, [])] for c in cats}
    extracted = _llm_extract_slots(text, cats, slot_keys)
    category_slots = add_category_slots(cats, category_slots, extracted)

    # 分流转发：对每个已有类别槽里出现别类关键词的，转发
    for from_cat in list(category_slots.keys()):
        for key in list(category_slots[from_cat].keys()):
            val = category_slots[from_cat].get(key)
            if val:
                res = _relocate(str(val), from_cat, key, cats, category_slots)
                if res:
                    cats = res["categories"]
                    category_slots = res["category_slots"]

    missing = rebuild_missing(cats, category_slots)
    active = state.get("active_category") or (cats[0] if cats else "")
    can_search = (not missing) or (state.get("clarify_count", 0) >= 3) or state.get("clarify_stopped", False)
    # 兼容单类别：写回 category/slots 别名
    ret = {
        "categories": cats,
        "category_slots": category_slots,
        "missing": missing,
        "route_decision": "search" if can_search else "clarify",
        "category": active,
        "slots": category_slots.get(active, {}),
    }
    if not state.get("active_category") and cats:
        ret["active_category"] = cats[0]
        ret["category_index"] = 0
    return ret
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py -k "route_multi or route_can_search" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/assistant_graph.py ai-module/tests/test_multi_hazard.py
git commit -m "feat(multi-hazard): rewrite route for multi-category extraction+rebuild+can_search"
```

---

### Task 5: `meta_clarify` + `clarify` 重构（代码选槽 + LLM 措辞）

**Files:**
- Modify: `core/assistant_graph.py`（`clarify`、新增 `meta_clarify`、`_llm_phrase`）
- Test: `tests/test_multi_hazard.py`

**Interfaces:**
- Consumes: `missing`、`SLOT_SCHEMAS`、`_llm_phrase`（新增，测试 monkeypatch）。
- Produces: `clarify(state) -> dict`（返回含问题的 `messages` + `relationship` 清空）；`meta_clarify(state) -> dict`（写 `relationship`）。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_multi_hazard.py 追加
def test_clarify_chooses_top_slots_and_phrases(monkeypatch):
    monkeypatch.setattr(ag, "_llm_phrase",
        lambda slots, ctx: "消防通道是被什么东西堵的？")
    st = {"messages": [HumanMessage(content="消防被堵")],
          "missing": ["消防通道_blocker", "消防通道_persistence", "占道_blocked"],
          "categories": ["消防通道", "占道"], "active_category": "消防通道",
          "category_index": 0, "category_slots": {"消防通道": {}, "占道": {}},
          "relationship": "", "clarify_count": 1, "clarify_stopped": False}
    up = ag.clarify(st)
    assert up["messages"][-1].content == "消防通道是被什么东西堵的？"
    assert up["relationship"] == ""           # 抽槽后清空

def test_meta_clarify_add(monkeypatch):
    monkeypatch.setattr(ag, "_llm_phrase", lambda slots, ctx: "这些是同一个地方的问题，还是另外单独一条？")
    st = {"messages": [HumanMessage(content="那消防被堵呢")],
          "missing": ["消防通道_blocker"], "categories": ["占道"],
          "active_category": "占道", "category_index": 0,
          "category_slots": {}, "relationship": "", "clarify_count": 0, "clarify_stopped": False}
    up = ag.meta_clarify(st)
    assert up["messages"][-1].content == "这些是同一个地方的问题，还是另外单独一条？"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py -k "clarify_ or meta_clarify" -v`
Expected: FAIL（`_llm_phrase`/`meta_clarify` 不存在）

- [ ] **Step 3: 实现**

```python
# core/assistant_graph.py
def _llm_phrase(slot_keys, context) -> str:
    prompt = (
        "请把下面要问的槽位，措辞成一句自然、友好、一次只问一个问题的中文问句（不要列序号）。\n"
        f"当前上下文：{context}\n要问的槽：{'、'.join(slot_keys)}\n只输出问句。"
    )
    try:
        resp = _llm._call_llm([SystemMessage(content="你是澄清问句生成器"), HumanMessage(content=prompt)], cancellation=None)
        return (resp.get("content") or "").strip() or "能再具体说说吗？"
    except Exception:
        return "能再具体说说吗？"

def clarify(state: AssistantState) -> dict:
    cats = state.get("categories") or ([state["category"]] if state.get("category") else [])
    active = state.get("active_category") or (cats[0] if cats else "其他")
    missing = state.get("missing") or []
    active_slots = [m for m in missing if m.startswith(active + "_")]
    chosen = active_slots[:2] if active_slots else missing[:2]
    question = _llm_phrase(chosen, active)
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]
    return {"messages": msgs, "relationship": ""}

def meta_clarify(state: AssistantState) -> dict:
    question = _llm_phrase(["判断关系"], state.get("active_category", ""))
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]
    return {"messages": msgs}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py -k "clarify_ or meta_clarify" -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/assistant_graph.py ai-module/tests/test_multi_hazard.py
git commit -m "feat(multi-hazard): clarify=code-select+llm-phrase, add meta_clarify"
```

---

### Task 6: `search` 循环 + `report` 合并模板

**Files:**
- Modify: `core/assistant_graph.py`（`search`、`report`、`_pick_keyword`）
- Test: `tests/test_multi_hazard.py`

**Interfaces:**
- Consumes: `category_slots`、`_run_tool`、`category_results`。
- Produces: `category_results: dict{cat:{regulation,case}}`；`report` 合并成 `draft_report`。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_multi_hazard.py 追加
def test_search_loops_categories(monkeypatch):
    monkeypatch.setattr(ag, "_run_tool", lambda name, kw: f"[{name}] {kw}")
    st = {"categories": ["消防通道", "占道"], "category_index": 1,
          "category_slots": {"消防通道": {"blocker": "杂物"}, "占道": {"blocked": "完全堵死"}},
          "category_results": {}, "messages": []}
    up = ag.search(st)
    assert set(up["category_results"].keys()) == {"消防通道", "占道"}
    assert "完全堵死" in up["category_results"]["占道"]["case"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py::test_search_loops_categories -v`
Expected: FAIL（`search` 只处理单类别）

- [ ] **Step 3: 实现**

```python
# core/assistant_graph.py
def search(state: AssistantState) -> dict:
    cats = state.get("categories") or ([state["category"]] if state.get("category") else [])
    results = dict(state.get("category_results") or {})
    for cat in cats:
        kw = _pick_keyword(cat, state.get("category_slots", {}).get(cat, {}))
        reg = _run_tool("search_regulation", kw)
        case = _run_tool("search_cases", kw)
        results[cat] = {"regulation": reg, "case": case}
    return {"category_results": results}

# report 改合并模板
def report(state: AssistantState) -> dict:
    messages = list(state.get("messages", []))
    cats = state.get("categories") or ([state["category"]] if state.get("category") else [])
    results = state.get("category_results") or {}
    vision = state.get("vision_summary") or ""
    lines = []
    for cat in cats:
        r = results.get(cat, {})
        lines.append(
            f"[隐患类别] {cat}\n"
            f"[视觉分析] {vision}\n"
            f"[检索法规] {r.get('regulation') or '库内暂未检索到'}\n"
            f"[检索案例] {r.get('case') or '库内暂未检索到'}"
        )
    ctx = (
        "\n\n".join(lines) +
        "\n请对每个隐患用一节输出：### 一、触犯法规 / ### 二、安全隐患 / ### 三、类似案例。" +
        "法规和案例必须来自上面检索结果，没有就写「库内暂未检索到」，不编造。" +
        "多隐患时每个隐患精炼、突出结论；法规引用完整准确。信息不足写「信息不足，未确认」。" +
        "最后加一句「需要我按这个情况生成一个整改建议吗？」"
    )
    final_messages = messages + [HumanMessage(content=ctx)]
    emit = getattr(_stream_local, "emit", None)
    buf = []
    for tok in _llm._call_llm_stream_events(final_messages, cancellation=None):
        buf.append(tok)
        if emit:
            emit("chunk", tok)
    return {"draft_report": "".join(buf)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py::test_search_loops_categories -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/assistant_graph.py ai-module/tests/test_multi_hazard.py
git commit -m "feat(multi-hazard): search loops categories, report merges template"
```

---

### Task 7: 图接线（`build_graph` 加 `meta_clarify`）+ 系统提示 + 冒烟

**Files:**
- Modify: `core/assistant_graph.py`（`build_graph`、`get_app`）、`core/assistant_agent.py`（`ASSISTANT_SYSTEM`）
- Test: `tests/test_multi_hazard.py`（图冒烟）

**Interfaces:**
- Consumes: 前面所有节点。
- Produces: `build_graph()` 返回含 `meta_clarify` 的 `StateGraph`。

- [ ] **Step 1: 写失败/冒烟测试**

```python
# tests/test_multi_hazard.py 追加
def test_graph_builds_with_meta_clarify():
    g = ag.build_graph()
    nodes = set(g.get_graph().nodes.keys())
    assert "meta_clarify" in nodes
    assert {"route", "clarify", "search", "report"} <= nodes
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py::test_graph_builds_with_meta_clarify -v`
Expected: FAIL（`meta_clarify` 节点不存在）

- [ ] **Step 3: 实现**

```python
# core/assistant_graph.py
def build_graph():
    g = StateGraph(AssistantState)
    g.add_node("route", route)
    g.add_node("meta_clarify", meta_clarify)
    g.add_node("clarify", clarify)
    g.add_node("search", search)
    g.add_node("report", report)
    g.set_entry_point("route")
    # route: 多类别时先 meta_clarify 判断关系（存在 relationship 待定），否则 clarify/search
    g.add_conditional_edges(
        "route", route_decider,
        {"meta_clarify": "meta_clarify", "clarify": "clarify", "search": "search"},
    )
    g.add_edge("meta_clarify", "clarify")
    g.add_conditional_edges(
        "clarify",
        lambda s: "search" if (not s.get("missing") or s.get("clarify_count", 0) >= 3 or s.get("clarify_stopped")) else "route",
        {"search": "search", "route": "route"},
    )
    g.add_edge("search", "report")
    g.add_edge("report", END)
    return g.compile(checkpointer=InMemorySaver())
```

> `route_decider` 改为：若 `state["relationship"]` 为 `"pending"` 且 `missing` 非空 → `meta_clarify`；否则按 `can_search` 返回 `clarify/search`。实现如下：

```python
def route_decider(state):
    if state.get("relationship") == "pending" and state.get("missing"):
        return "meta_clarify"
    return "search" if (not state.get("missing") or state.get("clarify_count", 0) >= 3 or state.get("clarify_stopped")) else "clarify"
```

系统提示（`core/assistant_agent.py` `ASSISTANT_SYSTEM`）追加一段：

```
【多隐患】用户可能在一个地方或一句话里反应多个安全隐患（如“占道+消防通道”）。
- 多个类别同时出现时，直接分别补齐各自的槽位，不要只处理一个。
- 每个类别各自查询法规和案例，最后合成一份合并报告（每类一节）。
- 串台信息（回答占道时提到消防）不要丢失，转到对应的类别去处理。
- 若信息不足，如实写「信息不足，未确认」，不要编造。
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/ -q`
Expected: PASS（含旧 `test_adaptive_slots.py` 13 个 + 新增多隐患用例）

> 旧用例若因 `route` 返回值结构变化而失败，需在 `route` 里补齐旧字段 `category`/`slots`/`missing`（Task 4 已做），必要时在旧测试里补 `category_slots` 相关状态字段。

- [ ] **Step 5: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/assistant_graph.py ai-module/core/assistant_agent.py ai-module/tests/test_multi_hazard.py
git commit -m "feat(multi-hazard): wire meta_clarify into graph + system prompt + regression"
```

---

### Task 8: 端到端冒烟 + 安全回退说明

**Files:**
- 无新增代码；运行验证。
- 触发：`server.py` 的 `assistant_stream` 已接入 `run_stream_events`（Task 7 后不改接口）。

**Interfaces:**
- Consumes: `core/assistant_graph.run_stream_events`。

- [ ] **Step 1: 导入冒烟**

Run: `cd E:\java\newProject\ai-module; python -c "from core.assistant_graph import build_graph, get_app; print('IMPORT OK')"`
Expected: `IMPORT OK`

- [ ] **Step 2: 真实 API 走查（需启动 Python server）**

Run: `cd E:\java\newProject\ai-module; uvicorn server:app --port 8000`
然后（另一终端）：
```bash
curl -N -X POST http://localhost:8000/api/ai/assistant/stream -H "Content-Type: application/json" -d "{\"message\":\"消防被堵，长期占道\",\"session_id\":\"demo\"}"
```
Expected: SSE 依次返回 `status:正在分析/正在补充信息`、`status:正在检索法规与案例`、`status:正在生成结论`，最后 `chunk` 输出包含「消防通道」「占道」两节的合并报告，`done` 收尾。

- [ ] **Step 3: 可选——多类别追问走查**

消息序列（同一 `session_id`）：
1. `"路边摆摊占盲道"` → 追问占道 `blocked`
2. `"完全堵死，消防通道也被杂物堵了"` → 占道补 `blocked`，消防登记为新增类别并补 `blocker`，不重复问已答项
3. `"长期"` → 消防 `persistence` 补齐 → 放行检索 → 合并报告

- [ ] **Step 4: 提交调试过程中的修复**（如有）

```bash
cd E:\java\newProject
git add -A ai-module
git commit -m "fix(multi-hazard): e2e smoke fixes"
```

---

## 自检清单（写作完成后对照）

- [ ] 是否覆盖设计文档 §0-§12 全部决策？（categories、meta_clarify、先补齐再检索、公共槽、CATEGORY_PRIORITY、选槽=代码/措辞=LLM、critical 门槛vs识别、多类别并行抽槽、防误填分流、全局 missing 重算、上限逃生口、合并报告）
- [ ] 是否无占位符（无 TBD/TODO/「类似 Task N」）？
- [ ] 命名一致性：`categories/category_slots/active_category/category_index/missing/relationship/clarify_count/clarify_stopped` 在所有 task 中一致。
- [ ] 旧单类别用例仍通过（兼容 `category`/`slots` 别名）。

## 执行交接

计划已保存到 `docs/superpowers/plans/2026-09-01-multi-hazard-agent.md`。两种执行方式：

**1. Subagent-Driven（推荐）** — 每个 task 派发一个子 agent，任务间双重评审，迭代快。

**2. Inline Execution** — 在本会话按 executing-plans 批量执行，带检查点。

选哪种？
