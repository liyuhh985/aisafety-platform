> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 新版 AI 助手图 —— 四节点代码讲解（A 篇 · 已同步最新代码 v2）

> 本文档配合「新版链路引导」使用，只讲 Python 图的核心：`route / clarify / search / report` 四个节点。
> 代码取自 `ai-module/core/assistant_graph.py`（**当前最新版本，含 pending_categories 机制**）。
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

**关键点**：每个新消息从 `route` 进；`route_decider` 决定走 `meta_clarify`/`clarify`/`search`；`clarify`/`meta_clarify` 连 `END`（问完本轮结束）。

---

## 1. 一个核心机制：`pending_categories`（新增类别的判别）

这是 A 篇**最重要**、也是最容易被忽略的机制。它的作用：

> **当这一轮"首次出现一个新类别"（old_cats 里没有），先不直接合并，而是把新类别放进 `pending_categories`，走 `meta_clarify` 问用户"同一处还是单独"，下一轮根据回答决定 ADD 还是 SWITCH。**

### 为什么要先 pending？
跨轮新增类别有歧义：用户说"旁边消防通道也被堵了"，这个消防通道可能是：
- **跟占道同一处**（一个地方多个问题）→ ADD
- **单独另一条**（换个地方的问题）→ SWITCH

**不能直接合并**，要先问用户。所以先把新类别"挂起"到 `pending_categories`。

### 相关常量
```python
_SAME_PLACE_WORDS = ("同一处", "同一个地方", "同段", "同一", "一起")
_SEPARATE_WORDS = ("其它", "分开", "另一条", "新的一条", "另外一条", "另一条", "无关")
```
用户回答"同一处/一起" → `_is_same_place_answer`=True → ADD；回答"其它/分开/另一条" → `_is_separate_answer`=True → SWITCH。

---

## 2. `route` —— 每轮的大门（含 pending 判断）

### 职责
识别类别 → 处理否定/pending/新增 → 抽槽 → 重算 missing → 决定 clarify/search。

### 最新代码

```python
def route(state):
    user_text = _latest_user_text(state)      # 识别用最新句
    full_text = _join_text(state)             # 抽槽用全文
    vision_cat = _extract_vision_category(state.get("vision_summary", ""))

    new_cats = _infer_categories(user_text, vision_cat)   # 肯定类别
    old_cats = list(state.get("categories") or [])
    negated = _find_negated(user_text)                    # 被否定类别
    if negated:
        new_cats = [c for c in new_cats if c not in negated]

    pending_prev = list(state.get("pending_categories") or [])
    pending_out = pending_prev
    relationship_out = ""

    if pending_prev:
        # 上一轮 meta 在等用户确认关系
        if _is_separate_answer(user_text):
            cats = _merge_categories(new_cats, pending_prev)   # SWITCH
            pending_out = []; relationship_out = "switch"
        elif _is_same_place_answer(user_text):
            cats = _merge_categories(new_cats, old_cats + pending_prev)  # ADD
            pending_out = []; relationship_out = "add"
        elif negated:
            cats = [c for c in old_cats if c not in negated]
            cats = _merge_categories(new_cats, cats)
            pending_out = []; relationship_out = "switch"
        else:
            cats = _merge_categories([c for c in new_cats if c not in pending_prev], old_cats)
            relationship_out = "pending"                      # 回答模糊，继续挂起
    elif negated:
        cats = [c for c in old_cats if c not in negated]
        cats = _merge_categories(new_cats, cats)
        relationship_out = "switch"
    else:
        fresh = [c for c in new_cats if c not in old_cats]
        if old_cats and fresh:
            pending_out = fresh                               # 首现新类别 → 挂起
            relationship_out = "pending"
            cats = _sort_by_priority(_dedupe(old_cats))
        else:
            cats = _merge_categories(new_cats, old_cats)      # 直接 ADD
            relationship_out = ""

    # 清掉不在 cats 里的旧类别槽
    _prev = dict(state.get("category_slots") or {})
    _valid = {k: dict(v) for k, v in _prev.items() if k in cats}
    slot_keys = {c: [s.key for s in SLOT_SCHEMAS.get(c, [])] for c in cats}
    extracted = _llm_extract_slots(full_text, cats, slot_keys)
    category_slots = add_category_slots(cats, _valid, extracted)

    # 分流转发（防串类别，只登记）
    categories_after = cats
    for from_cat in list(category_slots.keys()):
        for key in list(category_slots[from_cat].keys()):
            val = category_slots[from_cat].get(key)
            if val:
                res = _relocate(str(val), from_cat, key, categories_after, category_slots)
                if res:
                    categories_after = res["categories"]; category_slots = res["category_slots"]

    missing = rebuild_missing(categories_after, category_slots)
    can_search = (not missing) or (state.get("clarify_count", 0) >= 3) or state.get("clarify_stopped", False)

    ret = {
        "categories": categories_after, "category_slots": category_slots,
        "missing": missing, "route_decision": "search" if can_search else "clarify",
        "pending_categories": pending_out, "relationship": relationship_out,
    }
    if categories_after and not state.get("active_category"):
        ret["active_category"] = categories_after[0]; ret["category_index"] = 0
    return ret
```

### 逐行解读（核心是"分支判断"）

| 分支 | 触发 | 结果 |
|---|---|---|
| `pending_prev` + 用户答"其它/分开" | 上轮挂起的类别，用户说**单独** | SWITCH（新类别顶替/并上） |
| `pending_prev` + 用户答"同一处/一起" | 上轮挂起的类别，用户说**同一处** | ADD（并到一起） |
| `pending_prev` + 否定 | 用户干脆否定 | 删被否定 + 并新 |
| `pending_prev` + 回答模糊 | 用户没说清 | **继续挂起**（pending 保留） |
| `negated`（无 pending） | 否定词 | 删被否定 + 并新（switch） |
| `old_cats and fresh` | **首现新类别** | **挂起 pending**，不直接合并 |
| 其他 | 正常新增 | 并集 ADD |

**⭐ 关键**：`pending_categories` 是**判别"新增 vs 切换"的中转站**。首现新类别不直接合并，先挂起等用户确认。

---

## 3. `route_decider` —— 决定走哪

```python
def route_decider(state):
    if state.get("pending_categories"):
        return "meta_clarify"        # 挂起新类别 → 先问"同一处还是单独"
    if state.get("relationship") == "pending" and state.get("missing"):
        return "meta_clarify"
    if (not state.get("missing")) or state.get("clarify_count", 0) >= 3 or state.get("clarify_stopped"):
        return "search"              # 齐了/到上限/用户停 → 检索（逃生口）
    return "clarify"
```

**优先级**：`pending_categories` > `relationship==pending` > `search`（逃生口） > `clarify`。

---

## 4. `clarify` —— 常规追问

```python
def clarify(state):
    cats = state.get("categories") or []
    active = state.get("active_category") or (cats[0] if cats else "其他")
    missing = state.get("missing") or []
    active_slots = [m for m in missing if m.startswith(active + "_")]
    chosen = active_slots[:2] if active_slots else missing[:2]
    # 推进 active_category（如果 chosen 属于另一个类别）
    next_active = active
    if chosen and "_" in chosen[0]:
        next_active = chosen[0].split("_", 1)[0] or active
    next_index = state.get("category_index", 0)
    if next_active in cats:
        next_index = cats.index(next_active)
    question = _llm_phrase(chosen, next_active)
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]
    ret = {"messages": msgs, "relationship": "", "clarify_count": state.get("clarify_count", 0) + 1}
    if next_active != state.get("active_category") or next_index != state.get("category_index", 0):
        ret["active_category"] = next_active; ret["category_index"] = next_index
    return ret
```

**⭐ 新增（v2）**：`clarify` 现在会**推进 `active_category`/`category_index`**——如果 `chosen` 属于另一个类别（比如从消防切到占道），就更新 `active_category`。这样多隐患能逐个类别的槽轮流问。

---

## 5. `meta_clarify` —— 新类别判别

```python
def meta_clarify(state):
    active = state.get("active_category", "")
    pending = state.get("pending_categories") or []
    if pending:
        context = f"{active}都涉及：{'、'.join(pending)}" if active else f"都涉及：{'、'.join(pending)}"
    else:
        context = active
    question = _llm_phrase(["判断关系"], context)
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]
    return {"messages": msgs, "relationship": "pending"}
```

**⭐ v2**：`meta_clarify` 会把 pending 的类别带进提问上下文（"占道都涉及：消防通道"），让问句更具体。

---

## 6. 其他辅助函数（最新）

### `_find_negated`（B 方案，识别两类否定）
```python
def _find_negated(text):
    neg = []
    for c in CATEGORIES:
        if ("不是" + c) in text or ("并非" + c) in text:   # 否定在前
            neg.append(c); continue
        pos_c = text.find(c)
        if pos_c == -1: continue
        for tail in ("不是问题", "不存在", "不对", "根本不是", "不是"):  # 类别在前、否定在后
            pos_t = text.find(tail)
            if pos_t != -1 and pos_c < pos_t:
                neg.append(c); break
    return _dedupe(neg)
```

### `_relocate`（简化版，只登记）
```python
def _relocate(value, from_cat, key, categories, category_slots):
    hit_cats = _detect_other_cats(value, from_cat)
    if not hit_cats:
        return None
    new_cats = _merge_categories(hit_cats, categories)   # 只登记类别
    return {"categories": new_cats, "category_slots": category_slots}
```

### `_infer_categories`（图文融合）
```python
def _infer_categories(text, vision_category=""):
    cats = []
    if vision_category:
        mapped = _VISION_CATEGORY_MAP.get(vision_category)
        if mapped: cats.append(mapped)
    hits = [c for c in CATEGORIES if _score_category(c, text) > 0]
    cats = _sort_by_priority(_dedupe(cats + hits))
    if cats: return cats
    return [_llm_classify(text) or "其他"]
```

### `_latest_user_text` / `_join_text`
```python
def _latest_user_text(state):
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage): return m.content or ""
    return ""

def _join_text(state):
    return " ".join(getattr(m, "content", "") for m in state.get("messages", [])
                    if isinstance(m, (HumanMessage, AIMessage)))
```

### `report`（v3：get_stream_writer 真流式）

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

    writer = get_stream_writer()          # 拿 writer（contextvar，跨线程可靠）
    buf = []
    for kind, text in _report_llm._call_llm_stream_events(dict_msgs, cancellation=None):
        if kind == "chunk":
            buf.append(text)
            try:
                writer({"chunk": text})   # 逐 token 写进 custom 流
            except Exception:
                pass                       # 非 custom 模式下 writer 可能不可用，忽略
    return {"draft_report": "".join(buf)}
```

**关键点（v3 新增）**：
- 用 `get_stream_writer()`（`contextvar`，**跨线程可靠**）取代旧的 `_stream_local.emit`（`threading.local()`，跨线程会空）。
- 每吐一个 token 就 `writer({"chunk": text})` → 走 `stream_mode="custom"` 流，**真·逐 token**。
- 仍返回 `draft_report`（整份），供非 custom 场景 / 测试用。

---

---

## 7. 一图看懂分工

| 节点 | 职责 | 返回字段 |
|---|---|---|
| `route` | 识别 + pending/否定/新增判断 + 抽槽 + 重算 | categories/category_slots/missing/route_decision/pending_categories/relationship |
| `meta_clarify` | 问"同一处还是单独"（pending 时） | messages/relationship=pending |
| `clarify` | 问一个缺槽（代码选槽 + 推进 active） | messages/relationship/clarify_count/active_category |
| `search` | 逐类别检索 | category_results |
| `report` | 合并三段式报告 | draft_report |

---

## 8. 你已确认的理解点（回看核对）

- `set_entry_point("route")`：每轮从 route 进。
- 识别用**最新句**、抽槽用**全文**。
- **否定 = 规则删除**（`_find_negated`，B 方案识别"不是X"和"X不是..."）。
- **`_relocate` 简化 = 只登记**（删了 `CROSS_SLOT_MAP`）。
- **`pending_categories`** = 首现新类别先挂起，走 meta_clarify 判别 ADD/SWITCH。
- **`route_decider` 优先级**：pending > search(逃生口) > clarify。
- 局部更新：返回的键覆盖，没返回的保留。
- 两层记忆：memory(历史) vs checkpointer(结构化 state)。

---

## 9. 下一步（B 篇）
- `run_stream_events` SSE bridge：图跑出 status/chunk/done 怎么逐条吐给前端。
- `app.stream(updates)` 返回 `{node: update}` 怎么被遍历。
- 断连取消（CancellationToken）。