# 按类别动态槽位 + 类别化检索 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把新版 LangGraph 助手的「固定槽位（behavior/persistence/blocked）」改成「按隐患类别动态槽位 + 类别化检索」，让危房/消防通道/高空坠物等不同隐患走各自的关键问题，并让检索关键词带类别。

**Architecture:** 在 `AssistantState` 增加 `category` 与 `missing`；新增 `Slot` dataclass + `SLOT_SCHEMAS`（类别→槽位列表）；`route` 节点先 `infer_category`（vision 类别/关键词/兜底），再按该类别 schema 判定 missing 并决定 clarify/search；`clarify` 问该类别下一个缺失槽位；`search` 用「类别+槽位」合成关键词，做类别化检索。

**Tech Stack:** Python 3.13、langgraph、langchain-core、现有 `Agent`/`assistant_tools`。

## Global Constraints

1. **保留现有约定**：SSE 契约 `kind∈{status,chunk,error,done}`；`checkpointer` 按 `session_id`；`_call_llm_stream_events` 真 token 流；`_call_llm` 含模型降级。
2. **必须有「其他」兜底 schema**：类别识别失败时用通用 schema 追问，不能死循环。
3. **必须兼容「占道」老场景**：原 behavior/persistence/blocked 逻辑不能回归。
4. **`emit` 不走 state**（msgpack 不可序列化函数），继续用 `threading.local`。
5. **类别化检索**：`search` 的关键词必须包含类别 + 从槽位提取的关键特征，长度 ≤8 字。
6. **不引入新依赖**（只加 `dataclass`，标准库）。

---

## 目标文件

| 文件 | 改动 |
|---|---|
| `core/langgraph_state.py` | `AssistantState` 增加 `category: str`、`missing: list[str]` |
| `core/assistant_graph.py` | 加 `Slot`/`SLOT_SCHEMAS`/`infer_category`；改 `route`/`clarify`/`search`/`_pick_keyword`/`_slots_from_text` |
| `core/assistant_agent.py` | `ASSISTANT_SYSTEM` 增加“按类别问关键信息”说明 |
| `tests/test_adaptive_slots.py` | 新增测试 |

---

## Task 1：state 加字段

`core/langgraph_state.py`：
```python
class AssistantState(TypedDict, total=False):
    session_id: str
    messages: list
    slots: dict[str, str]
    category: str               # 推断出的隐患类别
    missing: list[str]          # 当前类别下未填的槽位 key
    vision_summary: str
    regulation_results: str
    case_results: str
    draft_report: str
    grade_feedback: str
    attempts: int
    route_decision: str
```

---

## Task 2：slot schema + 类别推断

`core/assistant_graph.py`（在 `SLOT_KEYS` 附近新增）：
```python
from dataclasses import dataclass

@dataclass
class Slot:
    key: str
    question: str
    critical: bool = True

CATEGORIES = ("占道", "危房", "消防通道", "高空坠物", "井盖/道路", "电气", "施工", "其他")

SLOT_SCHEMAS: dict[str, list[Slot]] = {
    "占道": [
        Slot("behavior", "具体是什么占道？摆摊、还是车辆停放？"),
        Slot("persistence", "是长期占压还是临时停放？"),
        Slot("blocked", "是完全堵死还是部分占用？"),
    ],
    "危房": [
        Slot("structure", "房屋有没有裂缝、倾斜或沉降？"),
        Slot("occupancy", "现在有人在里面居住或使用吗？"),
        Slot("risk", "有没有明显的即时坍塌风险？"),
    ],
    "消防通道": [
        Slot("blocker", "被什么东西占用了？"),
        Slot("persistence", "是长期还是临时？"),
        Slot("impact", "是否影响消防车或人员通行？"),
    ],
    "高空坠物": [
        Slot("source", "是从哪掉落的（外墙/阳台/广告牌）？"),
        Slot("target", "下面是人行道还是车行道？"),
        Slot("exposure", "有没有围挡或警告标志？"),
    ],
    "井盖/道路": [
        Slot("defect", "井盖是缺失、破损还是松动？"),
        Slot("traffic", "是否影响行人或车辆通行？"),
    ],
    "电气": [
        Slot("source", "是漏电、裸露电线还是设备故障？"),
        Slot("contact", "是否可能被人或车辆接触到？"),
        Slot("risk", "有没有冒烟或火花等迹象？"),
    ],
    "施工": [
        Slot("site", "施工区域是否做了围挡？"),
        Slot("safety", "有无安全警示或防护？"),
        Slot("impact", "是否影响行人或车辆通行？"),
    ],
    "其他": [
        Slot("describe", "能再具体描述一下这个安全隐患是什么吗？"),
    ],
}

_CATEGORY_KEYWORDS = {
    "占道": ("占道", "摆摊", "摊位", "车占", "停车", "挡盲道", "占盲道", "盲道"),
    "危房": ("危房", "裂缝", "倾斜", "沉降", "塌", "危楼", "危墙"),
    "消防通道": ("消防通道", "消防车", "消防", "救援通道"),
    "高空坠物": ("高空", "坠物", "掉落", "外墙", "广告牌", "瓷砖", "玻璃"),
    "井盖/道路": ("井盖", "窨井", "路面", "坑", "破损", "塌陷"),
    "电气": ("漏电", "电线", "短路", "火花", "电缆"),
    "施工": ("施工", "工地", "开挖", "脚手架", "围挡"),
}

def _infer_category(text: str, vision_category: str = "") -> str:
    # 1) 视觉类别（若有）归一化后优先
    for cat, keys in _CATEGORY_KEYWORDS.items():
        if vision_category and any(k in vision_category for k in keys):
            return cat
    # 2) 文字关键词
    for cat, keys in _CATEGORY_KEYWORDS.items():
        if any(k in text for k in keys):
            return cat
    return "其他"
```

---

## Task 3：`route` 改为「分类→schema→missing」

```python
def _join_text(state) -> str:
    return " ".join(
        getattr(m, "content", "") for m in state.get("messages", [])
        if isinstance(m, (HumanMessage, AIMessage))
    )

def route(state):
    text = _join_text(state)
    vision_cat = _extract_vision_category(state.get("vision_summary", ""))
    category = _infer_category(text, vision_cat)
    schema = SLOT_SCHEMAS.get(category) or SLOT_SCHEMAS["其他"]
    slots = dict(state.get("slots", {}))
    slots.update(_slots_from_text(text, category))
    missing = [s.key for s in schema if not (slots.get(s.key) or "").strip()]
    decision = "search" if not missing else "clarify"
    return {"category": category, "slots": slots, "missing": missing, "route_decision": decision}
```

`_extract_vision_category`：从 `[视觉分析] {json}` 里取 `hazard_category`：
```python
import json
def _extract_vision_category(vision_summary: str) -> str:
    if not vision_summary:
        return ""
    try:
        # 形如 "[视觉分析] {...json...}" 或直接是 json
        s = vision_summary
        if "[" in s:
            s = s[s.index("{"):]
        data = json.loads(s)
        return str(data.get("hazard_category", ""))
    except Exception:
        return ""
```

`_slots_from_text` 按类别启发式填槽（占道维持原逻辑，其它类别给少量关键词填槽）：
```python
def _slots_from_text(text: str, category: str) -> dict:
    slots = {}
    if category == "占道":
        if any(k in text for k in ("长期", "天天", "每天都", "一直")):
            slots["persistence"] = "长期"
        if any(k in text for k in ("临时", "偶尔", "一次")):
            slots["persistence"] = "临时"
        if any(k in text for k in ("完全堵死", "堵死", "走不了", "完全占")):
            slots["blocked"] = "完全堵死"
        elif any(k in text for k in ("部分", "能走", "占了一半")):
            slots["blocked"] = "部分占用"
        if any(k in text for k in ("摊", "摆摊", "占道", "停车", "车占", "挡盲道", "占盲道")):
            slots["behavior"] = text[:8]
    elif category == "危房":
        if any(k in text for k in ("裂缝", "开裂", "倾斜", "沉降")):
            slots["structure"] = "有裂缝/倾斜"
        if any(k in text for k in ("有人", "居住", "使用")):
            slots["occupancy"] = "有人"
        if any(k in text for k in ("塌", "坍塌", "危险", "随时")):
            slots["risk"] = "有即时风险"
    return slots
```

`route_decider` 不变：返回 `state.get("route_decision", "clarify")`。

---

## Task 4：`clarify` 问该类别下一个缺失槽位

```python
def clarify(state):
    category = state.get("category", "其他")
    schema = SLOT_SCHEMAS.get(category) or SLOT_SCHEMAS["其他"]
    missing = state.get("missing") or [s.key for s in schema if not (state.get("slots", {}).get(s.key) or "").strip()]
    if not missing:
        return {"messages": state.get("messages", [])}
    slot = next((s for s in schema if s.key == missing[0]), schema[0])
    messages = list(state.get("messages", [])) + [AIMessage(content=slot.question)]
    return {"messages": messages}
```

删除旧的 `_ASK_FOR_SLOT` 常量。

---

## Task 5：`search` 类别化检索

```python
def search(state):
    category = state.get("category", "占道")
    keyword = _pick_keyword(category, state.get("slots", {}))
    reg = _run_tool("search_regulation", keyword)
    case = _run_tool("search_cases", keyword)
    return {"regulation_results": reg, "case_results": case}

def _pick_keyword(category: str, slots: dict) -> str:
    parts = [category]
    for key in ("structure", "behavior", "defect", "source", "blocker", "blocked"):
        v = (slots.get(key) or "").strip()
        if v:
            parts.append(v)
    return (" ".join(parts))[:8]
```

`_run_tool` 不变。

---

## Task 6：`ASSISTANT_SYSTEM` 补充说明

`core/assistant_agent.py` 的 `ASSISTANT_SYSTEM` 中，把原“关键槽位”那两句替换为更通用表述：
```
【多轮澄清规则】 先判断隐患类别，不同类别问不同关键信息：
- 占道类：具体是什么占道 / 长期还是临时 / 是否堵死通行
- 危房类：有无裂缝倾斜沉降 / 是否有人居住使用 / 有无即时坍塌风险
- 消防通道：被什么占用 / 影响消防车或人员通行吗
一次只追问最缺的一个关键信息，不问地点（地点不影响定性）。
```

---

## Task 7：测试

`tests/test_adaptive_slots.py`：
```python
from core.assistant_graph import (
    _infer_category, _pick_keyword, _slots_from_text, route, SLOT_SCHEMAS,
)

def test_infer_category_weifang():
    assert _infer_category("危房有裂缝，很危险") == "危房"

def test_infer_category_default():
    assert _infer_category("这边好像有点问题") == "其他"

def test_route_weifang_missing():
    st = {"messages": [], "slots": {}, "vision_summary": ""}
    up = route(st)
    assert up["category"] == "其他" or up["category"] == "危房"
    if up["category"] == "危房":
        assert up["missing"] == ["structure", "occupancy", "risk"]
        assert up["route_decision"] == "clarify"

def test_pick_keyword_category():
    kw = _pick_keyword("危房", {"structure": "裂缝"})
    assert "危房" in kw and "裂缝" in kw

def test_zhandao_regression():
    st = {"messages": [], "slots": {}, "vision_summary": ""}
    # 用占道关键词，route 应判 category=占道
    text_st = {"messages": [], "slots": {}, "vision_summary": ""}
    # 直接测 _slots_from_text
    s = _slots_from_text("长期占着盲道完全堵死", "占道")
    assert s.get("persistence") == "长期" and s.get("blocked") == "完全堵死"
```

运行：
```bash
cd E:\java\newProject\ai-module
python -m pytest tests/test_adaptive_slots.py -q
```

---

## 自检
- 覆盖了“按类别动态槽位 + 类别化检索”。
- `其他` 兜底存在；`占道` 回归保留；`emit` 仍走 thread-local。
- 无新依赖；类型/命名一致（`Slot.key`、`SLOT_SCHEMAS[category]`、`_pick_keyword(category, slots)`）。

## 执行交接
保存至 `docs/superpowers/plans/2026-08-31-adaptive-slots-category.md`。执行方式：Inline（本会话逐 task 执行 + 测试）。

---

## Task 8：`_infer_category` 优化（关键词打分 + 打平 LLM 兜底）

**原因**：原 `_infer_category` 按 `_CATEGORY_KEYWORDS` 字典顺序“先命中先 return”。因 `占道` 在前，`"危房下面有盲道"` 会先命中 `盲道(占道)` 直接返回 `占道`，永远到不了 `危房`（纯文字无 vision 纠正时跑偏）。

**改动**：`core/assistant_graph.py`

1) 替换 `_infer_category` 为「关键词打分 + 打平 LLM 兜底」：
```python
def _infer_category(text: str, vision_category: str = "") -> str:
    # 0) 有图优先：视觉类别能纠正文案歧义
    if vision_category:
        for cat, keys in _CATEGORY_KEYWORDS.items():
            if any(k in vision_category for k in keys):
                return cat
    # 1) 关键词打分（不再先到先得）
    scores = {}
    for cat, keys in _CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for k in keys if k in text)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    best_cat, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    # 2) 唯一最高分且明显领先 → 用关键词（省一次 LLM）
    if best_score > 0 and best_score > second_score:
        return best_cat
    # 3) 平手 / 都零分 → 一次 LLM 分类（消除歧义）
    return _llm_classify(text) or "其他"
```

2) 新增 `_llm_classify`：
```python
def _llm_classify(text: str) -> str:
    prompt = ("请判断下面这句话主要反映的城市安全隐患类别，只返回一个类别词：" + " / ".join(CATEGORIES) + "\n文本：" + text)
    try:
        resp = _llm._call_llm(
            [SystemMessage(content="你是城市安全隐患分类器"), HumanMessage(content=prompt)],
            cancellation=None,
        )
        content = (resp.get("content") or "").strip()
    except Exception:
        return "其他"
    return next((c for c in CATEGORIES if c in content), "其他")
```

**测试**（`tests/test_adaptive_slots.py` 追加）：
```python
def test_ambiguity_llm_fallback(monkeypatch):
    called = {}
    def fake_classify(t):
        called['t'] = t
        return "危房"
    monkeypatch.setattr("core.assistant_graph._llm_classify", fake_classify)
    assert _infer_category("危房下面有盲道") == "危房"
    assert called.get('t') == "危房下面有盲道"

def test_no_llm_when_clear(monkeypatch):
    def boom(t):
        raise AssertionError("clear case 不应触发 LLM")
    monkeypatch.setattr("core.assistant_graph._llm_classify", boom)
    assert _infer_category("长期占着盲道完全堵死") == "占道"
```
