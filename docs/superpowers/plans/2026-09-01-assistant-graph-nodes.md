# 新版 AI 助手图 —— 四节点代码讲解（A 篇）

> 本文档配合「新版链路引导」使用，只讲 Python 图的核心：`route / clarify / search / report` 四个节点。
> 代码取自 `ai-module/core/assistant_graph.py`（当前真实代码）。
> 阅读顺序：先读「图骨架」，再逐个节点。每个节点给了「职责 + 代码 + 逐行解读 + 你踩过的坑」。

---

## 0. 图骨架（build_graph）

```python
def build_graph():
    g = StateGraph(AssistantState)
    g.add_node("route", route)
    g.add_node("meta_clarify", meta_clarify)
    g.add_node("clarify", clarify)
    g.add_node("search", search)
    g.add_node("report", report)
    g.set_entry_point("route")                 # 每个新消息都从 route 进
    g.add_conditional_edges(
        "route", route_decider,
        {"meta_clarify": "meta_clarify", "clarify": "clarify", "search": "search"},
    )
    g.add_edge("meta_clarify", END)            # 问完"同一处/单独"本轮结束
    g.add_edge("clarify", END)                 # 问完缺槽本轮结束
    g.add_edge("search", "report")
    g.add_edge("report", END)
    return g.compile(checkpointer=InMemorySaver())
```

**关键点：**
- `set_entry_point("route")`：每个新消息都从 route 进（多轮澄清的"每轮从 route 开始"）。
- `route_decider` 决定 route 之后走 `meta_clarify` / `clarify` / `search`。
- `clarify` / `meta_clarify` 都连 `END`（问完就结束本轮），因为**它们只是问，没有拿到用户的回答**，不能继续检索。
- `checkpointer=InMemorySaver()`：跨轮状态续接靠它（thread_id = session_id）。

---

## 1. `route` —— 每轮的大门（算账）

### 职责
识别多个隐患类别 → 抽槽 → 重算 missing → 决定 clarify / search。

### 真实代码（两种路径）

```python
def route(state: AssistantState) -> dict:
    text = _join_text(state)                                              # 把 messages 拼成文本
    vision_cat = _extract_vision_category(state.get("vision_summary", ""))

    # ---- 兼容旧单类别路径 ----
    if state.get("categories") is None and state.get("category_slots") is None:
        new_cat = _infer_category(text, vision_cat)
        old_cat = state.get("category", "")
        slots = dict(state.get("slots", {}))
        if new_cat != old_cat and old_cat:
            old_keys = {s.key for s in SLOT_SCHEMAS.get(old_cat, [])}
            new_keys = {s.key for s in SLOT_SCHEMAS.get(new_cat, [])}
            common = old_keys & new_keys
            slots = {k: v for k, v in slots.items() if k in common}
        slots.update(_slots_from_text(text, new_cat))
        missing = _missing_in(new_cat, slots)
        decision = "search" if not missing else "clarify"
        return {"category": new_cat, "slots": slots, "missing": missing, "route_decision": decision}

    # ---- 多类别路径（新版）----
    new_cats = _infer_categories(text, vision_cat)                       # ① 识别(可能多个)类别
    old_cats = list(state.get("categories") or [])
    if not old_cats and state.get("category"):
        old_cats = [state["category"]]
    cats = _merge_categories(new_cats, old_cats)                          # ② 并进类别清单(去重按优先级)

    slot_keys = {c: [s.key for s in SLOT_SCHEMAS.get(c, [])] for c in cats}
    extracted = _llm_extract_slots(text, cats, slot_keys)                 # ③ LLM 抽槽
    category_slots = add_category_slots(cats, state.get("category_slots") or {}, extracted)

    categories_after = cats
    for from_cat in list(category_slots.keys()):                          # ④ 分流转发(防串类别)
        for key in list(category_slots[from_cat].keys()):
            val = category_slots[from_cat].get(key)
            if val:
                res = _relocate(str(val), from_cat, key, categories_after, category_slots)
                if res:
                    categories_after = res["categories"]
                    category_slots = res["category_slots"]

    missing = rebuild_missing(categories_after, category_slots)           # ⑤ 代码重算还缺啥
    can_search = (not missing) or (state.get("clarify_count", 0) >= 3) or state.get("clarify_stopped", False)

    ret = {
        "categories": categories_after,
        "category_slots": category_slots,
        "missing": missing,
        "route_decision": "search" if can_search else "clarify",
    }
    if categories_after and not state.get("active_category"):
        ret["active_category"] = categories_after[0]
        ret["category_index"] = 0
    if len(categories_after) == 1:
        c0 = categories_after[0]
        ret["category"] = c0
        ret["slots"] = category_slots.get(c0, {})
    return ret
```

### 逐行解读（多类别路径）

| 行 | 说明 |
|---|---|
| `_join_text` | 把 state 里的 messages 拼成一段文本，作为"这句话" |
| `_infer_categories` | 识别类别，返回 list（可能多个）。先关键词打分，打平才 LLM 兜底 |
| `_merge_categories` | 把新识别的类别并入已有 categories 清单（去重 + 按 CATEGORY_PRIORITY 排序） |
| `_llm_extract_slots` | **LLM 抽槽**：从用户话里抽出每个类别填的槽，返回 `{类别: {槽key: 值}}` |
| `add_category_slots` | 把抽到的槽合并进 `category_slots[类别]`（只加填了的） |
| `_relocate` | **分流转发**：如果某个槽值里出现其它类别关键词（如占道的值里含"消防"），把它转到消防的筐，不丢 |
| `rebuild_missing` | **纯代码**：看每个类别还有哪些 critical 槽没填，生成 `["占道_blocked", "消防通道_persistence"]` |
| `can_search` | `missing` 空 / 澄清满3次 / 用户说别问了 → 放行检索 |
| 返回 `route_decision` | `"search"` 或 `"clarify"`，供 `route_decider` 用 |

### 你要记住的坑（第 2 问）
- **识别类别**：代码关键词为主，打平才 LLM（不是每次都调 LLM）。
- **抽槽**：LLM 干（一次调用）。
- **重算 missing**：纯代码，不调 LLM。

---

## 2. `route_decider` —— 决定走哪个路口

```python
def route_decider(state: AssistantState) -> str:
    if state.get("relationship") == "pending" and state.get("missing"):
        return "meta_clarify"    # 跨轮新类别 → 问"同一处还是单独"
    if (not state.get("missing")) or state.get("clarify_count", 0) >= 3 or state.get("clarify_stopped"):
        return "search"          # 齐了/到上限/用户停 → 检索
    return "clarify"             # 还有缺槽 → 追问
```

**优先级**：跨轮新类别 > 齐了/上限 > 追问。

---

## 3. `clarify` —— 常规追问（说话）

### 职责
`missing` 有缺口但不是新类别时，**问一个缺失槽**。它只说话，不动账本。

### 真实代码

```python
def clarify(state: AssistantState) -> dict:
    # ---- 兼容旧单类别 ----
    if not state.get("categories") and not state.get("category_slots"):
        category = state.get("category", "其他")
        schema = SLOT_SCHEMAS.get(category) or SLOT_SCHEMAS["其他"]
        missing = state.get("missing") or [s.key for s in schema if not (state.get("slots", {}).get(s.key) or "").strip()]
        if not missing:
            return {"messages": list(state.get("messages", []))}
        slot = next((s for s in schema if s.key == missing[0]), schema[0])
        return {"messages": list(state.get("messages", [])) + [AIMessage(content=slot.question)]}

    # ---- 新版：代码选槽 + LLM 措辞 ----
    cats = state.get("categories") or []
    active = state.get("active_category") or (cats[0] if cats else "其他")
    missing = state.get("missing") or []
    active_slots = [m for m in missing if m.startswith(active + "_")]   # 只挑当前类别的缺槽
    chosen = active_slots[:2] if active_slots else missing[:2]          # 代码选 top1-2
    question = _llm_phrase(chosen, active)                              # LLM 措辞成自然问句
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]  # 追加追问
    return {"messages": msgs, "relationship": "", "clarify_count": state.get("clarify_count", 0) + 1}
```

### 关键点（第 5/6 问）
- **选槽 = 代码**：先挑当前 `active_category` 的缺槽，取 top1-2；不让 LLM 决定问哪个（避免不确定/漏高危）。
- **措辞 = LLM**：`_llm_phrase` 把选好的槽说成自然问句。
- **只返回 `messages`/`relationship`/`clarify_count`**：不返回 `category_slots`/`missing` → 根据"局部更新"，这俩**保留原值**，不会被覆盖。这正是跨轮能延续的原因。
- `clarify_count += 1`：每次追问 +1，到 3 次放行检索。

---

## 4. `meta_clarify` —— 新类别判别（说话）

### 职责
**跨轮出现新类别**时，问「这些是同一处的问题，还是另外单独一条？」，据此走 ADD / SWITCH。

### 真实代码

```python
def meta_clarify(state: AssistantState) -> dict:
    question = _llm_phrase(["判断关系"], state.get("active_category", ""))
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]
    return {"messages": msgs, "relationship": "pending"}   # 标记关系待定
```

### 关键
- `relationship = "pending"`：告诉 `route_decider` 下一轮要先处理这个关系判断。
- 它也连 `END`（问完本轮结束）。回答后下一轮 route 根据用户答"同一处/单独"决定 ADD / SWITCH。

---

## 5. `search` —— 检索（算账）

### 职责
对所有类别**分别**检索法规 + 案例，结果存进 `category_results[类别]`。

### 真实代码

```python
def search(state: AssistantState) -> dict:
    cats = state.get("categories") or ([state["category"]] if state.get("category") else [])
    results = dict(state.get("category_results") or {})
    for cat in cats:
        kw = _pick_keyword(cat, state.get("category_slots", {}).get(cat, {}))
        reg = _run_tool("search_regulation", kw)
        case = _run_tool("search_cases", kw)
        results[cat] = {"regulation": reg, "case": case}
    return {"category_results": results}
```

### `_pick_keyword`
```python
def _pick_keyword(category, slots):
    parts = [category]
    for key in ("structure", "behavior", "defect", "source", "blocker", "blocked"):
        v = (slots.get(key) or "").strip()
        if v:
            parts.append(v)
    return (" ".join(parts))[:8]   # 拼接后最多8字
```
> 用「类别 + 关键槽值」拼检索关键词，如 `占道 占盲道`。

---

## 6. `report` —— 生成合并报告（说话 + 算账）

### 职责
拿到所有类别的检索结果，**合成一份合并报告**（每类一节：法规/隐患/案例）。

### 真实代码

```python
def report(state: AssistantState) -> dict:
    messages = list(state.get("messages", []))
    cats = state.get("categories") or ([state["category"]] if state.get("category") else [])
    results = state.get("category_results") or {}
    vision = state.get("vision_summary") or ""
    lines = []
    for cat in cats:
        r = results.get(cat, {})
        reg = r.get("regulation") or "库内暂未检索到"
        case = r.get("case") or "库内暂未检索到"
        lines.append("[隐患类别] " + cat + "\n[视觉分析] " + vision + "\n[检索法规] " + reg + "\n[检索案例] " + case)
    ctx = (
        "\n\n".join(lines) +
        "\n请对每个隐患用一节输出：### 一、触犯法规 / ### 二、安全隐患 / ### 三、类似案例。" +
        "法规和案例必须来自上面检索结果，没有就写「库内暂未检索到」，不编造。" +
        "多隐患时每个隐患精炼、突出结论；法规引用完整准确。信息不足写「信息不足，未确认」。" +
        "最后加一句「需要我按这个情况生成一个整改建议吗？」"
    )
    dict_msgs = []
    _ROLE_MAP = {"system": "system", "human": "user", "ai": "assistant", "tool": "tool"}
    for m in messages:
        dict_msgs.append({"role": _ROLE_MAP.get(getattr(m, "type", "user"), "user"), "content": getattr(m, "content", "")})
    dict_msgs.append({"role": "user", "content": ctx})
    emit = getattr(_stream_local, "emit", None)
    buf = []
    for kind, text in _report_llm._call_llm_stream_events(dict_msgs, cancellation=None):
        if kind == "chunk":
            buf.append(text)
            if emit:
                emit("chunk", text)
    return {"draft_report": "".join(buf)}
```

### 关键坑（修复过的）
- **`_report_llm` 是无 tools 的 Agent**：report 是纯文本生成，不能带 `tools`（否则 400）。
- **role 映射**：`HumanMessage.type = "human"` 不是 `"user"`，必须映射 `human→user`，否则模型 400。
- 把 langchain 消息转成 `{"role","content"}` dict，再走 `_call_llm_stream_events`。
- 返回 `{"draft_report": "..."}`：只更新这个键，其它保留。

---

## 7. 一图看懂四个节点分工

| 节点 | 类型 | 职责 | 返回的关键字段 |
|---|---|---|---|
| `route` | 算账 | 识别类别+抽槽+重算 missing | categories/category_slots/missing/route_decision |
| `clarify` | 说话 | 问一个缺槽（代码选槽，LLM 措辞） | messages/relationship/clarify_count |
| `meta_clarify` | 说话 | 问"同一处还是单独"（新类别） | messages/relationship=pending |
| `search` | 算账 | 逐类别检索法规+案例 | category_results |
| `report` | 说话+出结果 | 合并生成三段式报告 | draft_report |

**心法**：算账节点碰状态字段，说话节点只加 messages + 标记，靠「局部更新」让状态跨轮延续。

---

## 8. 你已确认的理解点（回看核对）

- `clarify`/`meta_clarify` 是**图节点**，不是 route 里的函数。
- `missing` 每项格式 = `"{类别}_{槽key}"`，如 `"占道_blocked"`。
- `route` 里 LLM 只做「抽槽」，重算 missing 是**代码**。
- `clarify`/`meta_clarify` 连 `END`：问完结束本轮，下一轮用户回答再从 route 进。
- 多隐患新增靠 `_merge_categories` 并类别 + `meta_clarify` 判别 ADD/SWITCH。
- 两层记忆：memory（历史文本，手动管理）vs checkpointer（结构化 state，框架自动管理）。
- checkpointer = 存取 state 的**工具/仓库**，不是 state 本身。
- state 局部更新：**返回的键覆盖，没返回的保留**。

---

## 9. 下一步（B 篇预告）
看完 A，我们进 **B：`run_stream_events` 这个 SSE bridge**，讲清楚：
- 图跑完（status/chunk/done）怎么逐条吐给前端。
- `app.stream(updates)` 返回的 `{node: update}` 怎么被遍历。
- bridge 怎么把 `clarify` 的追问、`report` 的正文作为 `chunk` 流出去。
- 断连取消（CancellationToken）怎么掐掉正在跑的图。