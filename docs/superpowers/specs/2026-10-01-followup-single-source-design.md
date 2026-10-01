# 追问只有一个出处：把"写问句"从 understand 收进产物节点

日期：2026-10-01
状态：待评审（未动代码）
关联：`core/dialogue_understanding.py`、`core/dialogue_policy.py`、`core/assistant_graph.py`、`core/slot_schemas.py`
上游：[`2026-09-27-followup-and-emergency-product-design.md`](./2026-09-27-followup-and-emergency-product-design.md)（四条决策，已执行）

## 0. 起点：现状核实（全项目有两个地方会产出问句）

|  | 出处 ① | 出处 ② |
| --- | --- | --- |
| 哪个模型 | `understand` 的规划器（`dialogue_understanding._planner_llm`） | `report` 的报告撰写模型（`assistant_graph._report_llm`） |
| 问句长在哪 | JSON 的 `question` 字段 | **报告正文里**，与正文是同一条流式文本 |
| 经过 `ask_slot_question` 节点吗 | 会 | **不会** |
| 有"问的是哪个槽"吗 | 有（`question_target`） | **没有** |
| 谁兜底 | 节点内三级降级（`resolve_slot_question`） | `preliminary_question_tail` 贴固定串 |

证据：

- 出处 ① 的契约：`core/dialogue_understanding.py:237`（`"question":"最多一个自然问题"`）与 `:238`（`question_target`）
- 出处 ② 的提示词：`core/assistant_graph.py:1844` —— "最后用你自己的话追问其中最关键的那一个"
- 出处 ② 的核对只有"有没有问号"：`core/assistant_graph.py:1515` 的函数 docstring 自认是"弱层次"：
  "它只保证「报告里有一个问句」，不判定这个问句是否真问在缺的那个槽上"

**一处确定的浪费**：出处 ① 的问句基本用不上。`resolve_slot_question`（`core/dialogue_understanding.py:465`）
把 `understand` 自带的问句当**第二级**，只在 `ask_slot_question` 节点（`core/assistant_graph.py:797`）
自己那次小调用失败时才用。也就是规划器每轮多写一份基本会被丢弃的问句。

## 1. 目标产物形态

产物三种，其中**报告只有两种**：

| 产物 | 铺垫 | 追问 |
| --- | --- | --- |
| 完整报告 | 报告正文（三段式） | 无 |
| **初步报告 + 追问** | 初步判断（报告正文） | 一个 |
| 纯回答（对话式） | 自然回答 | 可选，一个 |

**关键定界**：初步报告**不是独立产物，它是那个追问的铺垫**。
目的：不让追问显得突兀 —— 先让用户看到上一轮的初步判断结果，再问他缺的那一项。

反过来说，意味着"报告为主体、末尾挂一个问题"这个读法要废掉；正确的是"**一个追问，前面带一段铺垫**"。

## 2. 决策

### 决策 1：`understand` 不再产出面向用户的文本（问句 + 回答）

规划器契约去掉三个字段：`question`、`question_target`（`core/dialogue_understanding.py:237-238`），
以及 **`answer`**。

- `question` / `question_target` → 交给产物节点（决策 2 / 3）
- `answer` → 同上。按 §1，`understand` 只产出**事实与判断**，不产出给用户看的话
- 收益一：`understand` 的职责收敛成"定位 + 抽槽 + 分类 + 给事实性判断（risk_level / intent / needs_search）"
- 收益二：消掉 §0 那处浪费
- 收益三：**"该不该进追问节点"这个判断不需要了** —— 现在要先判 `understand` 有没有给问句，
  再决定要不要进节点；问句只有一个来源之后，这个判断自然消失

**`answer` 挪走的连带影响（`core/dialogue_policy.py`）**：两处 `if answer:`（`:153`、`:188`）
本质是在问"模型有没有给我一个可用的回答"。产物节点接管"写铺垫"之后这个判断**恒真**，于是：

- `answer_with_optional_question` 与 `answer_now` 的区分要重新定义（大概率简化成"要不要附追问"一个维度）
- `:197` 的 reason `"planner supplied a usable answer"` 失去依据

### 决策 2：追问只有一个出处 —— 产物节点

初步报告不再自己写问句。于是全项目只有一处产出问句，那个固定串兜底
（`preliminary_question_tail`，`core/assistant_graph.py:1515`）**整块删除**，不是降级。

- 连带可删：报告路径的 `question_limiter(1)`（`core/assistant_graph.py:1887`、`:1916`）——
  初步报告不再自带问句，"一轮最多一个问句"自动成立
- 连带可删：`resolve_slot_question` 的第二级（`understand` 自带问句）
- 连带可删：`question_source` 这个 state 字段 —— 只剩两级之后它等价于 `question == fixed`，
  而代码早就改用文本比对了（理由与删除成本见下面的「state 变更清单」）

### 决策 3：铺垫与问句**同一次调用**产出（两个字段）

产物节点一次模型调用返回 `{body: 铺垫, question: 追问}`（外加 `question_target`）。

- 这样总调用次数是 **2 次**（`understand` + 产物节点），与现状持平（见 §3）
- 问句是**独立字段**而不是混在正文里 → 它是结构化的，能带 `question_target`
- 铺垫与问句出自同一个模型、同一份上下文 → **不会脱节**
  （若不这样做，追问节点看不到铺垫正文，会出现"铺垫讲消防通道、追问问得很跳"）

**这是本设计唯一需要拍死的前提。** 若改成两次调用（先写铺垫、再写问句），总调用变 3 次，
且要额外解决连续性（把铺垫喂给追问节点的提示词）。

### 决策 4：该不该问，判据从"模型有没有写问句"改成 `missing` + 风险

现在 `dialogue_policy` 用 `_question_for_missing(plan)`（`core/dialogue_policy.py:48`）——
即**读模型写的问句**——来决定要不要追问（`:180`、`:199` 两处分支）。
决策 1 之后这个字段没了，判据改成 `missing` 非空 + 风险等级。

这更符合项目既有原则：**代码管"该做什么"，模型管"怎么说"。**
现状是代码在问模型"你想不想问"，这本身就是错位的。

### 决策 5：产物节点是三个，纯回答**不追问**

| 节点 | 铺垫 | 追问 | 天花板 |
| --- | --- | --- | --- |
| 完整报告 | 三段式报告 | 无 | 可邀请建代办任务（现状已如此） |
| 初步判断 + 追问 | 初步判断 | 有（一个） | 补齐后可升级成**完整报告**（走 search） |
| **纯回答** | 初步判断 | **无** | **只到初步判断，不升级、不检索** |

- **纯回答**：用户问"这东西算不算隐患" → 不检索、不追问，直接根据这一句给判断
- **写问句的只有一个节点**（"初步判断 + 追问"）—— "追问单一出处"这条不变式是
  **结构上**满足的，不靠调用约定
- 三个节点今天都已存在（`answer_reply` / `report`）；本决策是**收窄职责**，不是新建节点

**关于"天花板"（纯回答永远不出报告）**：它**大部分是自然结果** —— 纯回答不追问，所以下一轮
不存在"用户回答了追问"这件事，`dialogue_policy:122` 那条升级分支自然不会命中。**先不加"路径锁"字段**：
只剩"用户自己继续补充、直到事实齐全且用词不带口语判断"这一条窄路径可能升级，而那种情况下用户
本来就在主动描述隐患，给报告大概率是对的。观察后再说。

### 决策 6：判否即清锁

- 纯回答节点的模型调用**多返回一个结构化字段**：`is_hazard`（是 / 不是隐患），与回答正文同一次产出
- 节点内**代码**判断：为真 → **不改 state**；为假 → **清空这一条隐患的全部事实** ——
  `locked_major`、`locked_subcategory`、`categories`、`issues`、`missing`、`category_slots`、`category_results`
- **这个字段不进 state**（节点内局部值）→ 不存在跨轮生命周期问题。留一行日志（判否 + 清了哪些），
  只为线上可查、可统计判否率
- **为什么必须清**：今天的锁是**只进不出**的 —— `locked_major` 全项目只有三处赋值
  （前端改选 `core/assistant_graph.py:521` / 用户纠正 `:523` / 沿用上一轮 `:525`），**没有任何一处清空**。
  而它被建立的原因仅仅是"规划器把东西归到了某个小类" —— 那是**分类**，不是**判定它是隐患**。
  两件事今天被绑死了，所以"不是隐患"这个结论在 state 里毫无痕迹，下一轮一切照旧。

### 决策 7：越界时**撤销本轮**的锁定，而不是清零

`scope_guard` 判 `ambiguous` / `out_of_scope` 时，把**事实整体回滚到本轮之前**。

- **不清零**：用户只是跑题（"今天天气不错"）时，正在跟的那条隐患要留着
- **要撤销的是"本轮造成的改动"**：越界那一句可能已经把锁建上、把槽位覆盖了
- 实现：`begin_turn` 存一份本轮之前的事实快照，`scope_guard` 越界时按它回滚

**顺带修掉一个既有 bug**：现在一句越界的话会**把已积累的槽位清空** —— 规划器不给 `issues` 时，
`focus` 被重建成 `slots: {}`（`core/assistant_graph.py:547`），随后 `category_slots[code] = {}`
覆盖掉之前攒的（`:560`）。回滚正好一起修了。

### 决策 8：流式节奏与材料措辞（两个细节）

- **直接流**：铺垫先流出去，问句随后单独流，不攒整篇。让用户先看到字比"没有停顿"更重要
- **`_issue_blocks` 的 `[仍缺信息]` 后半句**（`core/assistant_graph.py:1457-1458`）：
  从"（这一项由本轮末尾的那一个追问承载）"改成"（**这一项缺了，正文不要展开**）"。
  追问不再是报告的尾巴，旧措辞会让模型以为后面还会跟一个追问

### state 变更清单（决策 1–8 的下游）

`core/langgraph_state.py` 是**真的契约**，不是文档 —— `assistant_graph.py` 里 `AssistantGraphState`
的 docstring 记过这个坑："未声明的键会被 LangGraph **静默丢弃**（节点返回未声明键时值不会进 state，
已实测）"。所以下面每一项都必须先改 state 声明，不能靠节点返回时顺手带上（带了不报错，就是不生效）。

| 字段 | 变化 | 依据 |
| --- | --- | --- |
| `facts_snapshot` | **新增** | 决策 7：`begin_turn` 存下本轮之前的事实，`scope_guard` 判越界时按它回滚 |
| `question_target` | **新增** | 决策 3：唯一写问句的节点必须自报"这一问问的是哪个槽"。今天这个值算得出来但**从来没进 state** —— 只喂给 `question_target_audit` 打日志（`core/assistant_graph.py:639`、`:832`） |
| `clarification_question` | **删除**（见下） | 决策 5：问句由那个节点自己生成、自己交付，不需要 state 中转 |
| `question_source` | **删除**（见下） | 决策 2 |
| `optional_question` | **删除** | 决策 5：纯回答不追问，"可选追问"这个概念消失 |
| `draft_report` | **语义扩**：从"报告正文"变成"本轮交付正文"（对话式回答也走它） | 保持 `"".join(chunks) == draft` 只有一个源头，不新增字段 |
| `dialogue_plan` | 字段保留，**内容契约变**（去掉 `question` / `question_target` / `answer`） | 决策 1 |
| `question_dropped` | **改成纯观测**（"有没有 A 类缺口"的判据挪到了那个节点） | 决策 2 |
| `question_missing_reason` | **取值要重定义**：`planner_failed` / `planner_no_question` 这两个枚举以"规划器有没有给问句"为前提 | 决策 1 |

#### 为什么删 `clarification_question`

它今天的全部用途是"让 `understand` 把问句传给另一个节点"。决策 5 之后，写问句的那个节点
**自己生成、自己交付**，这句话再也不需要经过 state。

**删除成本（已核实）**：生产代码 5 处读写（`core/assistant_graph.py:450` 复位、`:680` 写、`:821` 读作
第二级、`:843` 写、`:885`/`:890` 读）；**测试 44 处**（10 个文件，`test_slot_question_node.py` 占 14 处）；
**db 脚本 18 处**（8 个文件）。比 `question_source` 大得多，但它在新设计下**逻辑上确实不再需要** ——
那 5 处生产读写会全部自然消失（`understand` 不再写、第二级降级被删、`answer_reply` 不再是交付者）。

#### 为什么删 `question_source`

它记的是"三级降级里哪一级给的问句"。删它的理由不是"没人用"，而是**它本来就是个会说谎的标签** ——
`core/assistant_graph.py:836-840` 那段注释自己写着：

> 因为第 2 级（understand 自带问句）有时本身就是 `dialogue_policy._question_for_missing`
> 退回的固定串 —— 端到端实测见过这种「穿着 understand 外衣的第 3 级」。
> 所以判据取「交付问句是否等于固定串」，**与 source 无关**。

也就是：判断"用户看到的是不是固定串"，代码已经**绕开这个字段、改用文本比对**了。决策 2 之后只剩
两级（模型写的 / schema 固定串），而后者完全等价于 `question == fixed` —— 于是这个字段变成
"用两种方式记同一件事，其中一种还不准"。

**删除成本（已核实）**：生产代码里它只有一个真读者（`core/assistant_graph.py:641`，只给审计日志填
`origin` 标签，不影响行为）。要一起改的是：

- **13 处测试断言**，分布在 3 个文件：`tests/test_slot_question_node.py`(7)、
  `tests/test_slot_question_observability.py`(4)、`tests/test_redundancy_observation.py`(2)。
  其中 `test_slot_question_observability.py` 整个文件就是为这个字段写的，要单独评估是改还是退役
- **2 个测量脚本、共 5 处**：`db/measure_stage5_e2e.py`(3)、`db/measure_gap1_first_turn.py`、
  `db/measure_gap1_first_turn_batch2.py`

（数字是实测的：测试是 **13 处**，不是先前引用的 9 处。）

## 3. 成本：持平，不是省钱

| 场景 | 现在 | 改后 |
| --- | --- | --- |
| 追问轮 | `understand` 规划器（1）+ 追问小调用（2）= **2** | `understand`（1）+ 产物节点（2）= **2** |
| 初步报告轮 | 规划器（1）+ 报告模型（2）= **2** | **2** |
| 完整报告轮 | **2** | **2** |

**买到的不是钱，是结构**：追问单一出处、决策与措辞分离、消掉一处浪费。

另外澄清两条容易误解的：

- **`understand` 本来就不流式输出**。全项目真正逐 token 流出的只有 `report`、`emergency_guidance`、
  `fallback_reply`；`understand` 和 `answer_reply` 都是整段一次发出。这条不用改，也没得改。
- **"understand 给决策建议、和 `decide_next_action` 联动"这件事已经存在**：
  规划器返回 `risk_level` / `intent` / `needs_search`，`dialogue_policy` 的 if-else 拿它们当输入。
  **不要再加一层"模型建议动作"** —— 决策权必须只有一处（代码），否则会退回"两个地方在决定"的形状。

## 4. 本轮明确不改的部分（已经是要的形状）

`understand` 判完之后按产物分发，各走各的节点、各自结束这一轮 —— 这块**已经实现**，
见 `build_graph()`（`core/assistant_graph.py:2036`）：

| 产物 | 节点 | 产出方式 |
| --- | --- | --- |
| 越界 / 模糊 | `boundary_reply` | **纯模板**，不调模型 |
| 寒暄 | `smalltalk_reply` | **纯模板**，不调模型 |
| 紧急应答 | `emergency_guidance` | 模型写 + 代码核对必含要点 |
| 纯回答 | `answer_reply` | 模型回答 |
| 兜底 | `fallback_reply` | 现调一次模型 |

四条要保持的性质：

1. **寒暄与越界是纯模板，是有意的**。越界拒答必须稳定安全，不能交给模型自由发挥；
   寒暄不值得花一次调用。它们看着像"死板"，但这里没有"措辞更人性化"的收益，只有"说错话"的风险。
2. **危险的优先级最高，压过寒暄与越界**。`understand` 判出 `danger_veto` 后，寒暄那条路也会被改成
   走应急指引；`scope_guard` 一进来先看 `danger_veto`，是危险就直接返回，不给越界护栏任何降级机会。
3. **`END` 结束的是"这一轮"，不是"这次会话"**。会话状态按 `session_id` 跨轮持久化，
   下一轮仍从 `begin_turn` 进来，`locked_major` / `category_slots` 都还在。
4. **越界路径本轮要改一处**（决策 7：撤销本轮锁定）。模板本身、以及"越界只回答不检索"这两条不动。

## 5. 待定项

（已全部关闭，2026-10-01）

| 原待定项 | 结论 |
| --- | --- |
| 纯回答路径的落点 | **独立节点**，且**不追问**（决策 5） |
| 流式节奏 | **直接流**（决策 8） |
| `[仍缺信息]` 措辞 | 改成"这一项缺了，正文不要展开"（决策 8） |
| 判否时清哪些 | `locked_*` + `categories` + `issues` + `missing` + `category_slots` + `category_results` 全清（决策 6） |
| 越界路径要不要一起管 | **要**，做法是"**撤销本轮**锁定"而不是清零（决策 7） |

## 6. 验收标准（草案）

1. 全项目 grep：只有一处产出问句（"初步判断 + 追问"节点）；`preliminary_question_tail` 不再存在
2. 规划器契约里没有 `question` / `question_target` / `answer`；提示词里也没有
3. 初步报告的回复里，问句来自模型产出的 `question` 字段，且带 `question_target`
4. `dialogue_policy` 里没有 `_question_for_missing` 的调用；判据是 `missing` + 风险
5. **纯回答节点不产生任何问句**（有测试锁），且不触发检索（不进 `search`）
6. **判否即清锁**：模型给"不是隐患"时，七个事实字段全清；给"是"时 state 逐字未变（有测试锁两个方向）
7. **越界回滚**：一句越界的话之后，`locked_*` / `categories` / `issues` / `category_slots` 与本轮之前**逐字相同**；
   并且不再出现"越界一句话把已积累槽位清空"（决策 7 顺带修的既有 bug，要有回归测试）
8. `"".join(chunks) == draft_report` 这条一致性不变式仍然成立（既有测试）
9. 危险场景回复不含问号、不进报告（既有测试保持绿）
10. 全量 pytest 通过（既有失败 `tests/test_server_upload_validation.py` 除外）

## 7. 明确不做的事

- 不改紧急应答、寒暄两条路径（越界路径按决策 7 改一处：撤销本轮锁定）
- 不上 `interrupt`、不把追问做成暂停点（见 §8）
- 不引入"一轮问多个槽位"
- 不改前端
- 不修 `tests/test_server_upload_validation.py`

## 8. 被考虑并搁置的方案（记下来，别重复讨论）

**方案 B：把追问做成 `interrupt` 暂停点（像 `task_gate`）**

- 想要的效果：追问轮不再从 `begin_turn → understand` 重走一遍；恢复路径不经过 `scope_guard`，
  顺带绕掉"补答助手自己的追问被判成越界"那个问题
- **搁置原因**：`interrupt` 恢复时**节点从头重跑**，`interrupt()` 之前算出的东西都会重做一遍
  （`task_gate` 的 docstring 明写"恢复时整体重跑，所以 `interrupt()` 之前不能有副作用"）。
  所以"在追问节点里组问句 + 停住"这个画法不成立 —— 组问句必须挪到前一个节点。
  再叠加上 `run_stream_events` 要从"特判 task_gate"变成"按暂停节点分发"、以及逃逸路径
  （用户说"别问了直接出报告"）仍要回到全量 `understand`，收益不抵复杂度。
- **触发条件**：如果将来前端需要把追问渲染成结构化控件（像建任务那张卡），再重新评估。

**方案 A：只在 `understand` 里做窄提示词分流（不动图、不拆 report）**

- 做法：state 里多存一个"上一轮问的是哪个槽"，下一轮 `understand` 据此改用只带锁定小类 schema 的窄提示词
- 能拿到：省提示词、绕开 `scope_guard`
- **被决策 1/2 覆盖**：决策 1/2 已经把"写问句"收到一处，A 的那点收益在里面了。
  若决策 1/2 最终不做，A 可以作为最小替代方案。
