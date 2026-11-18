# Agent 编排（当前真相）

> 状态：current
> 最后核对：2026-10-09
> 事实来源：`ai-module/core/assistant_graph.py::build_graph()` 及 `core/*` 模块。节点以代码为准（**19 个**，不是旧文档写的 11 个或 4 个）。
> 旧 Orchestrator / clarify / meta_clarify / multi-hazard / 早期 LangGraph 迁移文档已降级为历史，见 `私有历史归档/`。

## 一、图结构（19 节点）

```
begin_turn
  -> understand              # 唯一的事实与决策写入者
  -> scope_guard             # 范围护栏（越界回滚事实）
  -> route                   # 纯映射，不决策
       ├─ 报告档:  search  ──Send 并行扇出──> retrieve
       │             ^                            │
       │             └── rewrite_query <── evaluate_retrieval（不达标，上界 1 次）
       │                                          │（达标）
       │                                       report -> after_report
       │                                                        │
       │                                       offer_task? -> task_gate
       │                                                        ├─confirm─> submit_task -> END
       │                                                        ├─decline─> close_task -> END
       │                                                        └─address─> task_gate(address) -> submit_task
       ├─ 追问档:  ask_slot_question -> END
       └─ 回答/旁路: boundary_reply | smalltalk_reply | answer_reply | fallback_reply -> END
         危险:      emergency_guidance -> END
```

### 节点清单与职责

| 节点 | 职责 |
|------|------|
| `begin_turn` | 组装本轮输入、写事实快照 |
| `understand` | **唯一**写入事实与决策：issues / 槽位 / intent / next_action / missing |
| `scope_guard` | 判定 hazard / emergency / smalltalk / ambiguous / out_of_scope；越界按快照整体回滚 |
| `route` | 把 `next_action` 映射成 `Command(goto=...)`，不做判断 |
| `search` | 组织检索计划，`Send` 按类别并行扇出 |
| `retrieve` | 并行执行法规 + 案例检索（`_run_tool`） |
| `evaluate_retrieval` | 检索自评：top1 分数 / 覆盖度判定是否达标 |
| `rewrite_query` | 不达标时改写检索词，回到 `search`（最多 1 次） |
| `report` | 生成报告（初步 / 完整），逐句流式 + 约束执行器 |
| `after_report` | 报告后预抽地址，供确认卡片显示（只跑一次） |
| `task_gate` | 建单确认闸门（LangGraph `interrupt`，人机回环） |
| `submit_task` | 写 outbox 并推 `task_accepted`（MQ 唯一路径） |
| `close_task` | 用户拒绝建单时的收尾语 |
| `boundary_reply` | 越界/边界模板回复 |
| `smalltalk_reply` | 寒暄 |
| `answer_reply` | 基于 plan 的直接回答 |
| `fallback_reply` | 无有效 plan 的兜底 |
| `emergency_guidance` | 正在发生的危险：安全处置指引（压过一切） |
| `ask_slot_question` | A 类关键槽缺失时的唯一问句来源；多条隐患时由代码拼成并列追问（每条一个问点，见 `_parallel_slot_question`），不调模型 |

## 二、状态通道

基类 `core/langgraph_state.py::AssistantState`，图内扩展 `AssistantGraphState`（新增检索重试通道）。

要点：
- **未声明的键会被 LangGraph 静默丢弃**；节点参数注解必须用子类 `AssistantGraphState`，否则新增通道读不到值（会导致重试环不收敛）。
- `messages` reducer：按 id 追加/覆盖 + 截断到 `MAX_THREAD_MESSAGES=20`（重放幂等）。
- `category_results` reducer：按类别浅合并；`None` 表示清空该类别。
- `dialogue_mode` 跨轮继承：`plain | preliminary | report`。

关键字段：`locked_major`、`locked_subcategory`、`categories`、`category_slots`、`missing`、`issues`、`next_action`、`dialogue_mode`、`premises_scope`、`immediate_danger`、`danger_veto`、`uncertainty_level`、`ungrounded_slots`、`task_phase`、`address_text`、`picked_longitude/latitude`。

## 三、两级隐患分类（canonical）

`core/hazard_taxonomy.py`：8 大类 × 32 小类。

| 大类 code | 标签 | 小类数 |
|-----------|------|--------|
| `traffic` | 交通与通行 | 4 |
| `municipal` | 市政设施 | 4 |
| `fire` | 消防安全 | 3 |
| `building` | 建筑安全 | 5 |
| `utility` | 电气与燃气 | 5 |
| `construction` | 施工安全 | 5 |
| `elevator_special` | 电梯与特种设备 | 3 |
| `environment_other` | 环境与其他 | 3 |

- `normalize_taxonomy()` 兼容旧标签（`LEGACY_CATEGORY_MAP`，如「占道」→ `traffic/road_occupancy`）。
- 会话内**最多 3 条活跃隐患**（`MAX_ACTIVE_HAZARDS`），且都落在锁定的大类集合
  `locked_majors` 里：集合由前端多选（`selected_major_code` 里用逗号拼多个 code）或
  自动判断模式下首轮由模型判定 —— **一句话涉及几个大类就锁几个**。
  **集合一旦锁定就硬锁**：模型改不了，前端中途改选也被忽略（只留一条日志）；要换大类
  只能**新开一个对话**。小类只在同集合内由用户明确纠正换。
  集合之外的条目只发一句通知、不记录（一张工单只有一个 `category`）。

## 四、槽位三分类（A/B/C）

`core/slot_schemas.py`：

| 类 | 判据 | 处理 |
|----|------|------|
| A 决策级 | 缺了会判错风险等级或该采取的动作 | 追问（进 `missing`） |
| B 报告级 | 结论/动作不变，但法规适用/责任/处罚档次不同 | 不追问，写进报告「仍需确认」条件分支 |
| C 装饰级 | 结论、动作、法规都不变 | 不问、不提 |

## 五、范围护栏 `scope_policy.py`

- `VALID_SCOPES = {hazard, emergency, smalltalk, ambiguous, out_of_scope}`。
- 危险词表与 `uncertainty.DANGER_TERMS` 共用一份定义（同一含义只允许一处定义）。
- 除「语义判断」外，还有**确定性关键词层**用于兜底（避免规划器抖动把本领域表述误判成越界）。
- 越界时：`understand` 写的事实按 `facts_snapshot` 整体回滚（不污染会话）。
- 历史误拦与逐词依据写在模块注释里（占道 / 交通设施 / 外立面 / 配电设施 / 交通标线等）。

## 六、不确定性 `uncertainty.py`

| 级别 | 含义 |
|------|------|
| `ok` | 正常 |
| `cautious` | 槽位值对不上原文（grounding 不足），降级表述 |
| `fallback` | 严重不足，走兜底 |

- `GROUNDED_COVERAGE=0.6` / `WEAK_COVERAGE=0.34`（刻意偏松，避免把好值误判成编造）。
- `danger_veto`：正在发生的危险（火灾/燃气泄漏/被困/坍塌/地震等）→ 禁止追问，直接走 `emergency_guidance`。
- `major_mismatch`：规划器与前端大类提示矛盾。

## 七、检索自评重试环（evaluator-optimizer）

- `WEAK_SCORE=0.58`（实测 p10：法规 0.5426 / 案例 0.5726；向量置信门槛 0.48）。
- `RETRY_MAX_ATTEMPTS=1`，`RETRY_ENABLED=True`，`PROBE_TOP1_SCORE=True`。
- 触发原因 T1/T2/T3；改写串长度上限 `MAX_RETRIEVAL_KEYWORD=24`。
- `GRAPH_RECURSION_LIMIT=60`（合法路径约 16 步；显式设限防回边失控烧模型调用）。
- 检索结果按大类过滤：`core/case_relevance.py` 剔除跨大类「语义邻近」条目，无同类则明确回「库内暂未检索到」。

## 八、建单闸门（human-in-the-loop）

- `after_report` 预抽地址 → `route_after_report`：`offer_task && !task_offered` 才进 `task_gate`。
- `task_gate` 用 LangGraph `interrupt()` 持久化挂起；恢复时**整段重跑**，所以 `interrupt()` 前不得有副作用（地址抽取因此放在 `after_report`）。
- `task_phase`：`confirm` → `address`。
- 恢复值可以是结构化 dict（前端卡片）或纯文本（老路径），见 `docs/current/ai-assistant-sse-contract.md` 第三节。

## 九、状态文案契约

- `STATUS_TEXT` 每节点一条；`STATUS_MAX_LENGTH=24`；带上下文模板如 `retrieve` 注入小类标签。
- 禁营销词（解构/深度研判/智能研判/赋能/洞察/强大/领先）。
- 后端自律有测试锁：每节点必须有文案、长度/非空/禁词校验。

## 十、设计原则（改代码前必读）

1. **决策权只有一处**：`understand` 写事实与决策，`route` 只映射。
2. **同一约束只有一套判定**：约束走统一的逐句执行器，不留第二套。
3. **模型负责语义，代码负责可判定的判据**：产物模式由代码判据 + 跨轮继承决定，不由单轮 intent 决定。
4. **不静默**：缺问句、被丢弃、冗余、落兜底都要留日志/字段。

### 相关模块

```
core/assistant_graph.py      图与节点
core/langgraph_state.py      状态定义与 reducer
core/dialogue_understanding.py  语义计划
core/dialogue_policy.py      确定性 next-action 策略
core/scope_policy.py         范围护栏
core/uncertainty.py          不确定性与危险否决
core/hazard_taxonomy.py      两级分类
core/slot_schemas.py         槽位 A/B/C
core/stream_guard.py         流式约束执行器
core/case_relevance.py       类别相关性过滤
core/cancellation.py         取消令牌
tools/                       检索/向量/地理/建单
```

## 十一、LLM 调用链与可靠性

`core/agent.py` 的调用链（2026-10-10 起）：

```
主端点（重试 LLM_RETRY_PER_ENDPOINT 次）
  -> 同供应商备用模型（仅当 MIMO_MODEL_BACKUP 与主模型不同）
    -> 跨供应商降级（FALLBACK_LLM_*，当前为 DeepSeek deepseek-flash）
```

- 只对**瞬时**错误重试（超时 / 429 / 5xx / 连接被切）；400/401/403 直接跳过本端点。
- **流式只在未吐出任何 token 时降级** —— 已吐正文再重试会重复内容。
- 只读 `delta["content"]`，推理模型的 `reasoning_content` 不会混进报告正文。

> 改这条链路前先读 `docs/current/ai-hazard-create-mq.md` §8（含"原降级是死代码"的原因与实测）。
