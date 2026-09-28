# 对话编排层简化：危险信号归一、回复节点拆分、状态文案带上下文

日期：2026-09-27
状态：待执行
关联：`core/assistant_graph.py`、`core/dialogue_policy.py`、`core/scope_policy.py`、`tools/hybrid_search.py`

## 1. 要解决的三个问题（都有实测依据）

### 1.1 危险信号有两套口径，且其中一套会丢上下文

- `core/scope_policy.py:80` / `:101` 由危险词表或规划器 `scope` 得出 `scope="emergency"`，
  响应体是固定的 `EMERGENCY_RESPONSE`。
- `core/assistant_graph.py:208-214` 的 `prepend_guidance` 由 `danger_veto` 决定是否**前置**指引。

两个信号来源不同、触发条件不同，但管的是同一件事。而 `scope=emergency` 走
`direct_reply` 的 `emergency_reply` 分支（`core/assistant_graph.py:524-529`）时：

**用一句通用模板把模型已经生成的对症回答整个替换掉。**

实测过：用户说「楼道里全是浓烟」，模型本可以走 `plan.ok` 给出撤离 + 火警 119 的对症回答；
走 `emergency_reply` 则只剩模板，且模板末尾还让用户"安全后，再描述具体位置"——让已经说清楚的人重说一遍。

**关键事实：这条分支没有承担任何不变式。**

| 不变式 | 真正的保证位置 |
| --- | --- |
| 危险时不许追问填表问题 | `core/dialogue_policy.py:226-241`：`no_questions` 为真时把 `ask_critical_question` 降级为 `report_preliminary` / `answer_now` |
| 指引必须排在最前 | `core/assistant_graph.py:208-214` `prepend_guidance`（代码保证，不依赖模型） |

所以删掉 `emergency_reply` 分支**不会放宽任何一条**。

### 1.2 `route` 只有 2 个目的地，决策堆在函数里

`core/assistant_graph.py:514-518` 的 `route` 是二值映射；模型细腻的决策实际由
`direct_reply`（`:521-613`）的 6 段分支消化：

| 分支 | 性质 |
| --- | --- |
| `emergency_reply` | 模板（本 spec 要删） |
| `anchor_domain` | 模板 |
| `out_of_scope` | 模板 |
| `plan.ok` | 模型回答 |
| `smalltalk` | 模板 |
| `else` | 兜底 LLM 调用 |

图很薄、函数很厚 —— 这是「LangGraph 用得很浅」这句话最准确的位置。

### 1.3 状态文案是孤儿

后端 `STATUS_TEXT`（`core/assistant_graph.py:54-67`）按节点推 12 条朴素文案；
**线上前端另有一套自己写死的**（实测线上产物）：

```
正在检索国家安全标准规范...
正在深度研判...
正在解构现场特征并检索标准库..
```

两套并存，前端那套不跟随真实流程，还带营销腔、标点不统一（`..` 与 `.` 混用）。

## 2. 方案

### 2.1 危险信号归一到 `danger_veto`（一步动作，非重构）

```
danger_veto = 危险词表 OR planner.immediate_danger OR planner.scope == "emergency"
```

**为什么必须并这一下**：`scope=emergency` 与 `danger_veto` 不是同一个信号。若规划器只报
`scope=emergency`、`immediate_danger=False`，则 `danger_veto` 为 False。此时若已删掉
`emergency_reply`，**这条危险输入会一句指引都没有**。所以顺序不能颠倒：先并口径，再删分支。

### 2.2 删 `emergency_reply` 分支，回复节点拆成 5 个

| 新节点 | 原分支 | 性质 |
| --- | --- | --- |
| `boundary_reply` | `anchor_domain` + `out_of_scope` | 纯模板 |
| `smalltalk_reply` | `smalltalk` | 纯模板 |
| `answer_reply` | `plan.ok` | 模型回答 + `prepend_guidance` / `prepend_interpretation` |
| `fallback_reply` | `else` | 兜底流式 |
| （删） | `emergency_reply` | — |

`route` 从二值映射变成真正的多出口 router：按 `next_action` + `direct_mode` 分发到 6 个目的地
（上述 4 个 + `search` + `boundary_reply`）。

**副作用必须一起处理**：`STATUS_TEXT` 是按键名查的，拆完要补新键，否则前端拿到空状态。

### 2.3 状态文案带上下文

- `STATUS_TEXT` 从固定串改为**可参数化**：`"正在检索「{category}」的相关法规…"`。
  只在**节点切换时**发，保持低频（状态不是正文，改太频繁会闪烁）。
- 文案约束写进契约：6~10 字、禁止营销腔（"解构现场特征"这种是自夸不是状态）、
  必须描述**系统正在做什么**而不是**系统多强**。
- 前端改为只渲染 SSE 的 `status.content`，删掉自己那套写死文案 → 单一事实来源。

### 2.4 关键词分支修复（同一批，独立文件）

`keyword_search` 现在用 `LIKE '%整串%'`（`tools/hybrid_search.py:432`），无分词。实测：

| `_pick_keyword` 产出 | 命中 |
| --- | --- |
| `消防通道占用`（槽位空） | 3 条 —— 因为 `category` 字段正好等于该串，**按 id 排序** |
| `消防通道占用 私家车 通道`（槽位有值） | **0 条** |

且 `hybrid_search` 把关键词结果放在合并结果**最前面**，所以槽位空时那 3 条按 id 排序的案例
**占住 top-1~3**，把语义最相关的挤到第 4、5 位。

修法（**只有一层，全在关键词分支内部**）：

| 层 | 改什么 |
| --- | --- |
| `keyword_search` | 按空白切 token（长度 ≥ 2）；**丢弃属于类别标签的 token**（命中 `SUBCATEGORY_LABELS` / `MAJOR_LABELS` 的值，含被 `[:24]` 截断的前缀情况）；剩下的 token 做 **OR 匹配**，取回宽候选（≤ 24 条）后在 Python 里**按命中 token 数 + 字段权重打分排序**，再截断到 limit。丢弃后无 token，或关键词为空 → 返回 `[]`（绝不能用 `LIKE '%%'`） |
| `_pick_keyword` | **保持原样，标签保留** —— 见下面的更正记录 |

#### 更正记录：`_pick_keyword` 不能去掉标签（原方案在此处是错的）

第一版方案写的是"`_pick_keyword` 不再拼小类标签，只返回槽位值"。**实测后被两个既有测试拦下来，方案已推翻**：

- `tests/test_indoor_wording.py::test_indoor_keyword_still_names_the_hazard`
- `tests/test_semantic_dialogue.py::test_pick_keyword_uses_chinese_subcategory_label`

原因：`_pick_keyword` 返回的串**同时是两样东西**：

1. `hybrid_search` 里 `vector_search(query)` 的 **embedding 查询**（`tools/assistant_tools.py:16` 把它作为
   `hybrid_search` 的第一个参数传入，`hybrid_search` 再用同一个串调 `vector_search`）
2. `keyword_search` 的 LIKE 输入

去掉标签会让**向量查询丢掉隐患语义**；槽位为空时更糟 —— 会 embed 一个**空串**。
所以标签必须留在串里，问题只能在关键词分支内部解决：**由 `keyword_search` 自己把"看起来就是
类别标签"的 token 丢掉。** 这样向量查询不受影响，而关键词分支不再退化成"按 id 取前 3 条"。

这条更正的代价是方案改了一层，收益是没有把向量检索一起弄坏 —— 记在这里，避免以后再犯。

预期：槽位空时关键词分支返回空 → top-3 交还向量；有词汇命中时窗口恢复。

**注意**：这条改动会改变检索结果，**必须先修正评测口径**（见 2.5），否则量不出效果。

### 2.5 评测口径修正（第 4 次，方向仍是"更贴近生产"）

现 `eval_retrieval.py` 传的是**用户原句**给 `keyword_search`，而生产传的是 `_pick_keyword` 产出。
所以现在量到的是**纯向量路径**。修正为：

- 查询 → `_pick_keyword(小类, 槽位)` → `hybrid_search`，与生产完全一致
- 分两种情形各跑一遍：**槽位空**（首轮真实情形）/ **槽位有值**
- 两情形分别报 Hit@5 / MRR / P@ret

## 3. 验收标准

1. `danger_veto` 单测：`scope=emergency + immediate_danger=False` 必须得出 `danger_veto=True`。
2. 删 `emergency_reply` 后，危险用例仍然：有指引且在回复最前、不含问号式追问。
   参考已有不变式测试 `immediate_danger=True → next_action != ask_critical_question`。
3. `route` 单测覆盖 6 个目的地，**优先级与重构前一致**（这是纯重构，行为必须逐位不变）。
4. 拆节点前后，端到端同一输入的最终回复文本**完全一致**（用一组固定输入做对照）。
5. 状态文案：每个节点切换都推到一条非空、≤ 20 字、不含固定孤儿的 status。
6. `keyword_search`：空关键词返回 `[]`；`"井盖"` 命中；`"井盖缺失/破损 雨水 移位"` 命中 ≥1；
   排序按"命中 token 数"降序而非 id。
7. 评测脚本两种情形都能跑通并出数字；改造前后对比写入 spec。
8. 全量 pytest 通过（既有失败 `tests/test_vector_delete_api.py` 除外，不在本 spec 范围）。

## 4. 明确不做的事

- 不改前端代码，只交付契约与大纲（前端由另一个模型负责）。
- 不修 `tests/test_vector_delete_api.py`（向量删除端点缺失是另一条线）。
- 不动 `tests/test_hazard_flow.py` 等既有测试的语义。
- 不引入新的 LLM 调用（本次全是结构与口径改动，延迟不应上升）。
