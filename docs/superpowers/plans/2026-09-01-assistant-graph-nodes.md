# 新版 AI 助手图 —— 四节点代码讲解（A 篇 · 已同步最新代码）

> 本文档配合「新版链路引导」使用，只讲 Python 图的核心：`route / clarify / search / report` 四个节点。
> 代码取自 `ai-module/core/assistant_graph.py`（**当前最新版本**）。
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
- `clarify` / `meta_clarify` 都连 `END`（问完就结束本轮），因为**它们只是问，没拿到用户的回答**，不能继续检索。
- `checkpointer=InMemorySaver()`：跨轮状态续接靠它（thread_id = session_id）。

---

## 1. `route` —— 每轮的大门（算账）

### 职责
识别多个隐患类别 → 处理否定/新增 → 抽槽 → 重算 missing → 决定 clarify / search。

### 最新代码

```python
def route(state: AssistantState) -> dict:
    # 识别只拿本轮最新用户消息（避免历史旧类别被全文捞回）
    user_text = _latest_user_text(state)
    full_text = _join_text(state)
    vision_cat = _extract_vision_category(state.get("vision_summary", ""))

    # 识别（可能多个）类别，并并进已有清单（去重 + 按优先级）
    new_cats = _infer_categories(user_text, vision_cat)
    old_cats = list(state.get("categories") or [])
    negated = _find_negated(user_text)      # 被否定的旧类别（"不是占道" -> ["占道"]）
    # 被否定的类别不应出现在"肯定识别"结果里（"不是占道"里的"占道"被关键词误命中）
    if negated:
        new_cats = [c for c in new_cats if c not in negated]
    if negated:
        # 替换/删除：先删掉被否定的旧类别，再并上本句肯定的新类别
        cats = [c for c in old_cats if c not in negated]
        cats = _merge_categories(new_cats, cats)
    else:
        # 新增：并集
        cats = _merge_categories(new_cats, old_cats)

    # 同步清理 category_slots 里已不在 cats 中的旧类别（切换/删除时清旧槽）
    _prev = dict(state.get("category_slots") or {})
    _valid = {k: dict(v) for k, v in _prev.items() if k in cats}
    # LLM 抽槽：用全文（含历史），信息越全越好
    slot_keys = {c: [s.key for s in SLOT_SCHEMAS.get(c, [])] for c in cats}
    extracted = _llm_extract_slots(full_text, cats, slot_keys)
    category_slots = add_category_slots(cats, _valid, extracted)

    # 分流转发：防止串类别（如占道槽值里提到 "消防" -> 转到消防）
    categories_after = cats
    for from_cat in list(category_slots.keys()):
        for key in list(category_slots[from_cat].keys()):
            val = category_slots[from_cat].get(key)
            if val:
                res = _relocate(str(val), from_cat, key, categories_after, category_slots)
                if res:
                    categories_after = res["categories"]
                    category_slots = res["category_slots"]

    # 代码重算还缺哪些 critical 槽
    missing = rebuild_missing(categories_after, category_slots)
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
    return ret
```

### 逐行解读

| 行 | 说明 |
|---|---|
| `_latest_user_text` | **只拿本轮最新用户消息**（不是全文），避免历史旧类别被重新捞回 |
| `_join_text` | 全文（含历史），**专门给抽槽用**（信息越全越好） |
| `_infer_categories` | 识别**肯定**类别（关键词 + 图文融合 + LLM 兜底） |
| `_find_negated` | 识别**被否定**类别（"不是占道" -> `["占道"]`） |
| `if negated` | 有否定 → 删掉被否定的旧类别 + 并上新类别 = **替换/删除**；无否定 → 并集 = **新增** |
| `_valid` | 同步清掉 `category_slots` 里已不在 `cats` 的旧类别键（残留槽清除） |
| `_llm_extract_slots(full_text,...)` | **抽槽用全文**（含历史上下文） |
| `_relocate` | 分流转发：防止串类别 |
| `rebuild_missing` | 纯代码重算还缺哪些 critical 槽 |
| `can_search` | missing 空 / 澄清满3次 / 用户说别问了 → 放行 |

### 你要记住的坑（本版新增）
- **识别 vs 抽槽的两条文本**：识别用**最新句**（聚焦、不捞回历史），抽槽用**全文**（信息全）。两边分开。
- **否定 = 规则删除**：不靠 LLM 判 action，`_find_negated` 找出被否定类别，直接删。确定性、快、可测。
- **切换要清槽**：删旧类别时，`category_slots` 里旧类别键也要清，不然残留。

---

## 2. 几个关键辅助函数

### `_infer_categories`（识别肯定类别）

```python
def _infer_categories(text, vision_category=""):
    # 晚融合：图算图的类别，文本算文本的类别，最后合并（不再图覆盖文）
    cats = []
    # 1) 图算一票
    if vision_category:
        mapped = _VISION_CATEGORY_MAP.get(vision_category)
        if mapped:
            cats.append(mapped)
    # 2) 文本算一票（关键词打分命中>0）
    hits = [c for c in CATEGORIES if _score_category(c, text) > 0]
    cats = _sort_by_priority(_dedupe(cats + hits))
    if cats:
        return cats
    # 3) 两者都无命中 → 才 LLM 兜底
    return [_llm_classify(text) or "其他"]
```

> 新增：**图文融合**（图一票 + 文一票合并），不再是"图覆盖文"。

### `_find_negated`（识别被否定类别）

```python
def _find_negated(text):
    """找出被"不是X/并非X"否定的类别。"""
    return [c for c in CATEGORIES if ("不是" + c) in text or ("并非" + c) in text]
```

### `_merge_categories`（并集合并 = 新增）

```python
def _merge_categories(new_cats, old_cats):
    return _sort_by_priority(_dedupe(list(old_cats or []) + list(new_cats or [])))
```

### `_latest_user_text`（取最新一句）

```python
def _latest_user_text(state) -> str:
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage):
            return m.content or ""
    return ""
```

### `route_decider`（决定走哪）

```python
def route_decider(state: AssistantState) -> str:
    if state.get("relationship") == "pending" and state.get("missing"):
        return "meta_clarify"    # 跨轮新类别 → 问"同一处还是单独"
    if (not state.get("missing")) or state.get("clarify_count", 0) >= 3 or state.get("clarify_stopped"):
        return "search"
    return "clarify"
```

---

## 3. `clarify` —— 常规追问（说话）

```python
def clarify(state: AssistantState) -> dict:
    cats = state.get("categories") or []
    active = state.get("active_category") or (cats[0] if cats else "其他")
    missing = state.get("missing") or []
    # 代码选槽：优先当前类别缺槽，取 top1-2
    active_slots = [m for m in missing if m.startswith(active + "_")]
    chosen = active_slots[:2] if active_slots else missing[:2]
    # LLM 措辞成自然问句
    question = _llm_phrase(chosen, active)
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]
    return {"messages": msgs, "relationship": "", "clarify_count": state.get("clarify_count", 0) + 1}
```

**关键**：选槽=代码（优先当前 active 类别），措辞=LLM。只返回 `messages`/`relationship`/`clarify_count`，不动 `category_slots`/`missing` → 局部更新保留账本。

---

## 4. `meta_clarify` —— 新类别判别（说话）

```python
def meta_clarify(state: AssistantState) -> dict:
    question = _llm_phrase(["判断关系"], state.get("active_category", ""))
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]
    return {"messages": msgs, "relationship": "pending"}
```

---

## 5. `search` —— 检索（算账）

```python
def search(state: AssistantState) -> dict:
    cats = state.get("categories") or []
    results = dict(state.get("category_results") or {})
    for cat in cats:
        kw = _pick_keyword(cat, state.get("category_slots", {}).get(cat, {}))
        reg = _run_tool("search_regulation", kw)
        case = _run_tool("search_cases", kw)
        results[cat] = {"regulation": reg, "case": case}
    return {"category_results": results}
```

---

## 6. `report` —— 生成合并报告（说话 + 算账）

```python
def report(state: AssistantState) -> dict:
    messages = list(state.get("messages", []))
    cats = state.get("categories") or []
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

**关键坑（修复过的）**：
- 用**无 tools 的 `_report_llm`**（纯文本生成避免 400）。
- **role 映射**：`human→user, ai→assistant`（不然 `"human"` 非法 → 400）。
- langchain 消息转 dict 再给流式接口。

---

## 7. 一图看懂分工

| 节点 | 类型 | 职责 | 返回的关键字段 |
|---|---|---|---|
| `route` | 算账 | 识别 + 处理否定/新增 + 抽槽 + 重算 missing | categories/category_slots/missing/route_decision |
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
- 识别用**最新消息**（不捞回历史），抽槽用**全文**（信息全）。
- **否定 = 规则删除**（`_find_negated`），不靠 LLM 判 action。
- 多隐患新增靠 `_merge_categories` 并集 + `meta_clarify` 判别 ADD/SWITCH。
- 两层记忆：memory（历史文本）vs checkpointer（结构化 state）。
- checkpointer = 存取 state 的**工具/仓库**。
- state 局部更新：**返回的键覆盖，没返回的保留**。

---

## 9. 下一步（B 篇预告）
看完 A，我们进 **B：`run_stream_events` 这个 SSE bridge**，讲清楚：
- 图跑完（status/chunk/done）怎么逐条吐给前端。
- `app.stream(updates)` 返回的 `{node: update}` 怎么被遍历。
- bridge 怎么把 `clarify` 的追问、`report` 的正文作为 `chunk` 流出去。
- 断连取消（CancellationToken）怎么掐掉正在跑的图。