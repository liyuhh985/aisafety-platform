> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 多隐患（Multi-Hazard）Agent 设计文档 v3（最终定稿）

> 状态：**可执行设计定稿**。本文档已吸收全部评审共识（critical 语义、多类别并行抽槽、防误填分层、全局 missing 重算、类别聚合与 active_category 推进）。下一步基于本文档生成执行计划。

---

## 0. 本版相对上一版的关键增量

1. **critical 语义澄清**：`critical` 管「门槛」（是否进 missing / 是否强制追问），**不管「识别」**（是否从用户自由文本中抽取）。两者解耦。
2. **抽槽契约改为多类别并行**：LLM 返回 `{categories, category_slots}`，按类别分组，不再锁死单一 `active_category`。
3. **防误填分层**：类别归属判断 → 枚举白名单 → 关键词反向分流（不丢弃）→ 先登记类别再决定是否填槽。
4. **全局 `missing` 重算**：抽槽后**重算**而非手动删除；每项带类别前缀 `"{category}_{key}"`。
5. **类别聚合**：`_merge_categories`（并集+去重+按 `CATEGORY_PRIORITY` 排序）实现「ADD」。
6. **`active_category` 推进**：存入 LangGraph checkpointer，补完一张表才推进，`route` 不得每次重置为 `categories[0]`。

---

## 1. 目标
让助手处理「一个地点/一句话里的多个安全隐患」：能识别多个类别、区分「新增(ADD)/切换(SWITCH)」、按类别并行补齐槽位、一次并行检索并合并报告，且**不串类别、不重复追问、不丢隐患**。

---

## 2. 已确认决策（全部定稿）

### 决策 A：`category` → `categories: list[str]`
有序、去重，按 `CATEGORY_PRIORITY` 排序。字段：`active_category`、`category_index`。

### 决策 B：判别「新增 vs 切换」→ 一律 agent 追问，不做启发式
- **同句多类别** → 直接 **ADD**（不追问，用户就在描述一个场景）。
- **跨轮新类别** → **meta-clarify 追问一次**「同一处还是单独反映？」据答复 ADD/SWITCH。

### 决策 C：先补齐所有槽，再一次执行检索 + 报告
澄清阶段收集**所有类别**缺失槽（并集），用户集中回答；全填齐（或到上限）后**一次并行检索 + 合并报告**。

### 决策 D：类别切换只留公共槽（复用已实现）
`active_category` 切换时：`old_keys ∩ new_keys` 保留（如 `persistence`），清旧类别专属槽。

### 决策 E：人工紧急度 `CATEGORY_PRIORITY`
```python
CATEGORY_PRIORITY = {
    "危房": 0, "消防通道": 1, "高空坠物": 2, "电气": 3,
    "施工": 4, "占道": 5, "井盖/道路": 6, "其他": 9,
}
```
用于 `categories` 排序、`missing` 排序、`clarify` 先问谁。

### 决策 F：**选槽=代码，措辞=LLM**
- 哪个槽最关键由**代码**决定：`missing` 已按 `CATEGORY_PRIORITY` + schema 顺序 + `critical` 过滤排好，`clarify` **硬取 top 1-2**，**绝不把选槽交给 LLM**。
- **LLM 只做两件事**：① 把已选好的 1-2 个槽**措辞成自然提问**；② 把用户回答**批量抽槽**（按类别分组）。

### 决策 G：`critical` 语义 = **门槛 vs 识别**（本次澄清）
- `critical=False` 的槽**不进 `missing`**（不阻塞检索、不专门追问）。
- 但 `critical=False` **不代表不识别**：抽槽输入仍是当前类别的**全部槽位**，用户顺口提到的非关键信息仍会进报告（「已确认，非必须」）。
- 一句话：**临界关门槛，不关识别。**

### 决策 H：抽槽契约 = **多类别并行**
LLM 返回：
```json
{
  "categories": ["消防通道", "占道"],
  "category_slots": {
    "消防通道": {"impact": "影响通行"},
    "占道": {"persistence": "长期", "behavior": "占道"}
  }
}
```

### 决策 I：防误填分层（见 §4.3）
类别归属 → 枚举白名单 → 关键词**分流**（不丢弃）→ 先登记类别再决定填槽。

### 决策 J：全局 `missing` **重算**，不手动删
抽槽后基于最新 `category_slots` 重新生成 `missing`（critical 且为空才进），不逐个 remove。

### 决策 K：每轮 clarify 的 LLM 次数
1 次措辞提问 + 1 次批量抽槽；澄清上限 3 轮 → 澄清阶段最多约 6 次 + 报告 1 次。

---

## 3. 槽位定义与 `critical` 真标注

`Slot` dataclass `critical: bool = True`。本次**真正区分**，可有可无槽标 `critical=False`：

```python
SLOT_SCHEMAS = {
    "占道": [
        Slot("behavior", "具体是什么占道？摆摊、还是车辆停放？", critical=True),
        Slot("persistence", "是长期占压还是临时停放？", critical=True),
        Slot("blocked", "是完全堵死还是部分占用？", critical=True),
    ],
    "危房": [
        Slot("structure", "房屋有没有裂缝、倾斜或沉降？", critical=True),
        Slot("occupancy", "现在有人在里面居住或使用吗？", critical=True),
        Slot("risk", "有没有明显的即时坍塌风险？", critical=True),
    ],
    "消防通道": [
        Slot("blocker", "被什么东西占用了？", critical=True),
        Slot("persistence", "是长期还是临时？", critical=True),
        Slot("impact", "是否影响消防车或人员通行？", critical=False),
    ],
    "高空坠物": [
        Slot("source", "是从哪掉落的（外墙/阳台/广告牌）？", critical=True),
        Slot("target", "下面是人行道还是车行道？", critical=False),
        Slot("exposure", "有没有围挡或警告标志？", critical=False),
    ],
    "井盖/道路": [
        Slot("defect", "井盖是缺失、破损还是松动？", critical=True),
        Slot("traffic", "是否影响行人或车辆通行？", critical=True),
    ],
    "电气": [
        Slot("source", "是漏电、裸露电线还是设备故障？", critical=True),
        Slot("contact", "是否可能被人或车辆接触到？", critical=True),
        Slot("risk", "有没有冒烟或火花等迹象？", critical=True),
    ],
    "施工": [
        Slot("site", "施工区域是否做了围挡？", critical=True),
        Slot("safety", "有无安全警示或防护？", critical=True),
        Slot("impact", "是否影响行人或车辆通行？", critical=False),
    ],
    "其他": [
        Slot("describe", "能再具体描述一下这个安全隐患是什么吗？", critical=True),
    ],
}
```

---

## 4. 抽槽分层与契约

### 4.1 三层 → 落地两层（向量不做）
| 层 | 作用 | 是否启用 |
|---|---|---|
| 关键词（第1层） | 仅对**第一句原始描述**暖启动，扫「长期/裂缝/摊」等，能填就填 | ✅ 暖启动，非可靠机制 |
| LLM 批量抽槽（第2层） | **每一轮**对用户消息批量抽槽，按类别分组返回 | ✅ 主机制 |
| 向量相似度 | embedding 匹配同义词 | ❌ 暂不实现 |

> 关键词表只暖启动第一句；LLM 生成的答题是自由文本，关键词靠不住，**一律走 LLM 抽槽**。

### 4.2 抽槽输入：当前类别**全部槽位**（做法 B），不是只 `missing`
即使某个槽 `critical=False`，也要喂给 LLM，让用户顺口提到的非关键信息也能被识别进报告。
抽槽 prompt（示意）：
```
用户消息："有裂缝，没人住；旁边一直在摆摊"
当前处理类别列表：["危房", "占道"]
请按类别抽取能填的槽，没提到的填 ""，只返回 JSON：
{
  "categories": ["危房", "占道"],
  "category_slots": {
    "危房": {"structure": "有裂缝", "occupancy": "无人", "risk": ""},
    "占道": {"behavior": "摆摊", "persistence": "长期", "blocked": ""}
  }
}
```

### 4.3 防误填分层（关键）
串台信息**不丢，要分流**。顺序：
1. **类别归属**：抽槽时先让 LLM 判断回答涉及哪些类别（返回 `categories` + `category_slots`），信息进它真正的类别筐，不硬塞当前 `active_category`。
2. **枚举白名单**：枚举槽（persistence/blocked/impact/occupancy…）值不在合法集合就丢弃。
3. **关键词反向分流**（第 3 关，兜 LLM 归错筐）：某类别槽值里出现**其它类别强关键词** → 不丢，转发到对的筐。
   - **跨类别槽位映射表** `CROSS_SLOT_MAP`（只放语义真正等价的对，宁缺毋滥）。
   - **命中类别是列表**（一个值可能同时命中多个类别）。
   - **先登记类别**（加入 `categories`），**映射确定才填槽**；映射不确定只登记类别，留给该类别自己的 clarify。
4. **白名单/枚举最终校验**（留在最后，见 §4.4）。

### 4.4 分流伪代码
```python
CROSS_SLOT_MAP = {
    ("占道", "blocked"): ("消防通道", "impact"),      # 堵死 → 影响通行
    ("占道", "persistence"): ("消防通道", "persistence"),  # 公共槽
    # 其它不确定的不写，不硬转
}

def _relocate(value, from_cat, key, categories, category_slots):
    hit_cats = [c for c in CATEGORIES if c != from_cat and any(k in (value or "") for k in _CATEGORY_KEYWORDS.get(c, ()))]
    if not hit_cats:
        return None
    for cat in hit_cats:
        ensure_category_registered(categories, cat)   # 先登记，保证不丢隐患
    target = CROSS_SLOT_MAP.get((from_cat, key))
    if target and target[0] in hit_cats:
        return target                                  # 有明确等价映射，才转发填槽
    return None                                        # 无映射：只登记类别，不硬填
```

---

## 5. `missing`：结构、排序、重算

### 5.1 结构
`missing` 为**全局一个列表**，每项形如 `"{category}_{key}"`，按 `CATEGORY_PRIORITY` + schema 顺序排序。
```python
missing = ["危房_structure", "危房_occupancy", "危房_risk", "占道_behavior", "占道_persistence", "占道_blocked"]
```
> 不是每个类别各一个列表；是一个列表装所有类别缺失的 `critical` 槽，靠前缀区分归属。`categories` 才是类别清单。

### 5.2 重算（不手动删）
抽槽后基于最新 `category_slots` 重算：
```python
def rebuild_missing(categories, category_slots):
    out = []
    for cat in categories:
        for s in SLOT_SCHEMAS[cat]:
            if s.critical and not (category_slots.get(cat, {}).get(s.key) or "").strip():
                out.append(f"{cat}_{s.key}")
    return sort_by_priority(out)
```

---

## 6. 类别聚合与 `active_category` 推进

### 6.1 `_infer_categories`（返回列表）
```python
def _infer_categories(text, vision_category=""):
    hits = [c for c in CATEGORIES if _score(c, text) > 0]   # 命中>0的类别都收集
    if not hits:
        return [_llm_classify(text) or "其他"]
    return sort_by_priority(dedupe(hits))
```

### 6.2 `_merge_categories`（= ADD）
```python
def _merge_categories(new_cats, old_cats):
    return sort_by_priority(dedupe(old_cats + new_cats))
```

### 6.3 `active_category` 推进
- `active_category` / `category_index` **存入 checkpointer**。
- `route` **不得**每次把它重置为 `categories[0]`，否则会跳回第一张表重复问。
- `clarify` 补满当前表后才推进到下一张；所有表满 → 进 `search`。

```python
def advance(state):
    idx = state["category_index"] + 1
    if idx < len(state["categories"]):
        return {"active_category": state["categories"][idx], "category_index": idx}
    return {}   # 全部补完
```

---

## 7. 节点流程

```
route ──> (检测新类别? ──> meta_clarify(同一处/单独) ──> 更新 categories)
   │
   ├── clarify(代码选槽 top1-2 + LLM措辞 + LLM抽槽 + 重算missing)
   │       └─> (missing空 / clarify_count>=MAX / clarify_stopped? ──> search | 否则 route)
   │
   └── search(对每个 category 检索) ──> report(合并报告) ──> END
```

- **route**：`_infer_categories` → 更新 `categories`（同句 ADD / 跨轮 meta-clarify）→ 重算 `missing` → 定 `can_search`。
- **meta_clarify**（新增节点）：跨轮新类别时问「同一处还是单独反映」，写 `relationship`，据此 ADD/SWITCH。
- **clarify**：`chosen = missing[:2]`（已排序）；`question = llm_phrase(chosen, context)`；用户答 → LLM 批量抽槽 → `add_category_slots` → `rebuild_missing` → `clarify_count += 1`。
- **search**：对每个 `category`，`keyword = _pick_keyword(category, category_slots[category])`，检索法规+案例，写 `category_results[category]`。
- **report**：合并模板（每类 `### 触犯法规 / 安全隐患 / 类似案例`），文字由模型生成（见 §9）。

`can_search`：
```python
MAX_CLARIFY = 3
can_search = (not missing) or (clarify_count >= MAX_CLARIFY) or clarify_stopped
```
到上限 / 用户说「别问了」→ 放行进检索，缺的槽在 report 写「信息不足，未确认」。

---

## 8. 状态结构（`AssistantState` 演进）

```python
class AssistantState(TypedDict, total=False):
    session_id: str
    messages: list
    categories: list[str]              # 有序、去重
    active_category: str               # 当前正在补哪张表
    category_index: int                # 指向 categories 下标（checkpointer 记住）
    category_slots: dict[str, dict]    # {类别: {slot_key: value}}
    category_results: dict[str, dict]  # {类别: {regulation, case}}
    missing: list[str]                 # 全局并集 + 排序 + critical 过滤，形如 "{cat}_{key}"
    relationship: str                  # "add"|"switch"|""
    clarify_count: int
    clarify_stopped: bool
    vision_summary: str
    draft_report: str
    grade_feedback: str
    attempts: int
    route_decision: str
```

---

## 9. 报告提示词（合并报告）

```
对每个隐患，用一节输出：### 一、触犯法规 / ### 二、安全隐患 / ### 三、类似案例。
- 法规和案例必须来自给定检索结果，库内没有就写「库内暂未检索到」，绝不允许编造。
- 法规条文要完整准确引用，不能精简/概括成一句。
- 多隐患时每个隐患精炼，突出核心结论，避免冗长；但法规引用必须完整准确。
- 若某类信息不足，如实写「信息不足，未确认」。
- 若视觉分析失败，注明「视觉分析失败，本结论仅依据文字描述」，不编造图中细节。
```

---

## 10. 走查示例：「消防被堵，长期占道」（追问轮）

前面已识别 `categories=["消防通道","占道"]`（ADD），只是槽位未填。
- 抽槽（多类别并行）：`{"categories":["消防通道","占道"], "category_slots":{"消防通道":{"impact":"影响通行"}, "占道":{"persistence":"长期","behavior":"占道"}}}`。
- `rebuild_missing` 重算：消防还缺 `blocker`（用户没说被什么堵），占道还缺 `blocked`（没提堵死没）。
- 按优先级（消防 > 占道）推进：先补消防 `blocker`，再补占道 `blocked`。
- 若用户这时说「消防被杂物堵，占道完全堵死」，则消防 `blocker=杂物`、占道 `blocked=完全堵死`，两边补齐 → `missing` 空 → 一次检索两张表 → 合并报告。

---

## 11. 涉及文件

| 文件 | 改动 |
|---|---|
| `core/langgraph_state.py` | `categories/active_category/category_index/category_slots/category_results/missing/relationship/clarify_count/clarify_stopped` |
| `core/assistant_graph.py` | `_infer_categories`、`_merge_categories`、`CATEGORY_PRIORITY`、`CROSS_SLOT_MAP`、`rebuild_missing`、`add_category_slots`、`meta_clarify`、`clarify`（代码选槽+LLM措辞+LLM抽槽）、`search`（循环）、`report`（模板合并）、`route`、`can_search` |
| `core/assistant_agent.py` | 系统提示补充多隐患 + 槽位分层 + 防串类别说明 |
| `tests/test_adaptive_slots.py` | 多隐患用例 + 选槽/抽槽/上限/防误填用例 |

---

## 12. 下一步
基于本文档生成**执行计划**（`writing-plans` 规范，逐 task + TDD + 提交），再逐 task 落地。