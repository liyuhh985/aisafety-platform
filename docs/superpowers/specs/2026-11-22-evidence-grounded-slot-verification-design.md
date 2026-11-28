# 证据引用式槽位校验（Evidence-First Slot Grounding）设计

> 状态：proposed
> 日期：2026-11-22
> 范围：Python 编排层，非侵入式改造
> 依赖：现有 `dialogue_understanding.py`、`uncertainty.py`、`assistant_graph.py`、`langgraph_state.py`

## 1. 目标

把当前“槽位值 + 字符覆盖率判断”升级为：

```text
模型抽取槽位值
+ 模型引用原文证据片段
+ 确定性代码验证证据是否真实存在
+ 输出可审计的槽位状态
```

本阶段要解决的问题：

1. `unverified` 判断从“只看字符重合”升级为“有明确证据来源”。
2. 可追踪某个槽位值来自第几条用户消息或视觉摘要。
3. 降低跨轮、跨隐患把无关词语误当成证据的概率。
4. 为后续事实确认、报告门禁、Skill 注入提供统一的事实状态。
5. 所有校验过程可测试、可观测、可降级。

## 2. 非目标

本阶段明确不做以下事项：

1. 不修改 Java 接口、MySQL 表结构、前端 SSE 契约。
2. 不向用户展示证据编号、原文引用或内部审计信息。证据只用于日志、调试和内部状态。
3. 不引入 Skill、`SKILL.md`、工具白名单或焦点机制。
4. 不改变多隐患报告策略。
5. 不直接修复非焦点追问、初步报告重复生成等逻辑缺陷。这些问题放在第二阶段处理。
6. 不依赖模型自报的 `verified`、`confidence` 或“我认为有依据”。

## 3. 当前实现与问题

### 3.1 当前流程

`dialogue_understanding.parse_plan()` 从规划器结果中取：

```json
{
  "issues": [
    {
      "major_code": "building",
      "subcategory_code": "dangerous_building",
      "slots": {
        "structure": "墙体倾斜"
      }
    }
  ]
}
```

`assistant_graph.understand()` 随后调用：

```python
verdict = assess(plan, source_messages, vision_summary)
```

`uncertainty.assess()` 把历史中的所有用户消息和视觉摘要拼成一个字符串：

```python
source = " ".join(all_user_messages)
```

然后对每个槽位执行：

```python
slot_status(value, source)
```

当前状态分为：

| 状态 | 当前判定 |
|---|---|
| `grounded` | 有 bigram 重合，或字符覆盖率 >= 0.6 |
| `weak` | 字符覆盖率在 0.34 ~ 0.6 |
| `strong` | 字符覆盖率 < 0.34，或数字不一致 |
| `unverified` | `strong` 槽位进入 `ungrounded_slots` |

### 3.2 当前问题

1. **同义表达误判**：原文“房子往一边斜”，模型值“墙体倾斜”，字符重合可能不足。
2. **否定关系误判**：原文“没有冒烟”，槽位“冒烟”可能因为字面重合被判成有依据。
3. **跨轮串位**：所有历史被拼接成一个来源，旧对话里的词可能错误支撑新隐患。
4. **跨隐患串位**：A 隐患的原文可能被拿去验证 B 隐患的槽位。
5. **无来源追踪**：无法知道槽位来自哪条用户消息。
6. **阈值脆弱**：`0.6 / 0.34` 是经验阈值，缺少语义层。

### 3.3 已有 `echo` 机制

当前 `echo_slots()` 会把“只是复述隐患名称”的值视为无效回答并删除，使槽位回到 `missing`。

本设计保留这个行为，并把 `echo` 和 `unverified` 明确区分：

```text
echo       -> 说了，但等于没回答
unverified -> 说了，但找不到可验证的原文依据
```

## 4. 核心设计

### 4.1 数据契约

规划器每个非空槽位都可以提供一条证据：

```json
{
  "issues": [
    {
      "major_code": "building",
      "subcategory_code": "dangerous_building",
      "slots": {
        "structure": "墙体倾斜"
      },
      "evidence": [
        {
          "slot": "structure",
          "quote": "房子明显往一边斜",
          "source_ref": "u2"
        }
      ]
    }
  ]
}
```

约束：

1. `slot` 必须是该小类允许的槽位 key。
2. `quote` 必须是用户原话或视觉摘要中的可定位片段。
3. `source_ref` 由后端分配，不允许模型自造。
4. 只接受 `user` 和 `vision` 来源，不接受 `assistant` 来源作为事实依据。
5. 一个槽位最多一条主证据；多条证据取第一条有效证据，其余进入审计日志。

### 4.2 来源编号

后端在构造规划器请求时，为可引用来源分配稳定编号：

```text
u1, u2, u3 ...     用户消息
v1, v2, v3 ...     视觉摘要或系统注入的视觉结果
a1, a2, a3 ...     助手历史消息，不可作为证据
```

实现建议：在 `build_planner_messages()` 中给消息内容加内部前缀，例如：

```text
[u2] 旁边还有一栋危房。
```

前缀只用于模型理解和证据引用，不进入用户可见文本。

模型必须在 prompt 中被明确要求：

```text
source_ref 只能填写输入中实际存在的编号；
quote 必须从对应来源中原样复制；
找不到证据时不要填 evidence，不要编造 quote。
```

### 4.3 槽位状态

新增内部状态，不改变现有 `missing` 字段语义：

| 状态 | 含义 | 后续动作建议 |
|---|---|---|
| `missing` | 没有值 | 追问槽位 |
| `echo` | 只是复述隐患名称 | 视为没回答，重新追问 |
| `grounded` | 有有效原文证据，语义支持 | 可进入完整报告 |
| `weak` | 有证据，但语义支持不确定 | 高风险场景优先确认 |
| `unverified` | 无证据、证据不存在或来源非法 | 事实确认节点处理，不直接完整报告 |
| `contradicted` | 原文与槽位值存在否定/冲突 | 作废该值，重新追问或确认 |

本阶段先实现 `grounded / weak / unverified / echo / missing`，`contradicted` 作为最小规则预留。

### 4.4 内部数据结构

建议存放在 `issue["slot_evidence"]`，保持可 JSON 序列化：

```json
{
  "structure": {
    "value": "墙体倾斜",
    "quote": "房子明显往一边斜",
    "source_ref": "u2",
    "status": "grounded",
    "reason": ""
  }
}
```

字段说明：

- `value`：模型抽取的槽位值。
- `quote`：模型引用的证据片段。
- `source_ref`：后端分配的来源编号。
- `status`：`grounded / weak / unverified / echo / missing`。
- `reason`：内部原因码，例如 `quote_not_found`、`invalid_source_ref`、`assistant_source`、`no_evidence`、`numeric_mismatch`、`negation_conflict`。

该字段只用于内部审计，不进入 SSE `taxonomy` 事件，不由前端渲染。

## 5. 确定性校验算法

新增接口建议：

```python
def verify_slot_evidence(
    *,
    slot_key: str,
    value: str,
    evidence: dict | None,
    source_map: dict[str, str],
    category: str,
) -> dict:
    ...
```

校验顺序：

1. **空值检查**
   - 值为空 -> `missing`。

2. **槽位合法性检查**
   - `slot_key` 不属于该小类 schema -> 丢弃该槽位并记录 `slot_not_allowed`。

3. **echo 检查**
   - 值只是复述隐患名称 -> `echo`，不进入 `unverified`。

4. **证据存在性检查**
   - 没有 evidence -> `unverified`，原因 `no_evidence`。
   - `source_ref` 不存在 -> `unverified`，原因 `invalid_source_ref`。
   - 来源是 assistant -> `unverified`，原因 `assistant_source`。

5. **quote 真实存在检查**
   - 规范化后，`quote` 必须是对应来源的子串。
   - 规范化规则：去空白、去常见标点、全角数字转半角、大小写归一。
   - `quote` 长度限制：建议 2～80 个中文字符，超过上限直接拒绝。
   - 不存在 -> `unverified`，原因 `quote_not_found`。

6. **数字一致性检查**
   - 提取 value 和 quote 中的数字。
   - value 中的数字必须能在 quote 或同来源文本中找到。
   - 数字单位需做最小归一化，例如“两米”与“2 米”。

7. **否定/冲突检查**
   - 在 quote 的匹配位置附近检查否定词窗口。
   - 否定词包括：不、没、没有、未、无、并非、不是、已清理、已恢复等。
   - 如果 value 表示存在某现象，而 quote 明确否定该现象 -> `contradicted`。

8. **语义支持检查**
   - 先做低成本字面/别名检查：value 是 quote 的子串，或命中别名表 -> `grounded`。
   - quote 有效但 value 不是字面片段 -> `weak`。
   - `weak` 不直接判定为编造，后续可接 NLI 或事实确认节点。

9. **生成内部状态**
   - 输出 `status`、`reason`、`quote`、`source_ref`。
   - `unverified` 继续汇总进 `ungrounded_slots`，供既有报告降级逻辑消费。

### 5.1 兼容旧状态

旧 Redis checkpoint 中没有 `slot_evidence`。兼容规则：

1. 如果 `slot_evidence` 不存在，继续使用现有 `slot_status()` 词面判断。
2. 如果 `slot_evidence` 存在，新逻辑优先。
3. 不对旧 checkpoint 做一次性重写，避免历史会话被突然判成大量 `unverified`。
4. 证据校验结果只在下一轮 `understand` 时写入。

## 6. 代码改动范围

### 6.1 `core/dialogue_understanding.py`

- 扩展规划器 JSON 契约，增加 `evidence` 字段。
- `_issue_from_values()` 保留 evidence，并清理非法 slot key。
- `_issues_from_plan_items()` 解析 evidence 列表。
- `parse_plan()` 输出 issue 级 evidence；保留旧 `categories` / `category_slots` 兼容。
- `build_planner_messages()` 为 user / vision / assistant 来源分配 `uN / vN / aN` 编号。
- prompt 增加：
  - evidence 的 JSON 形状；
  - quote 必须原样复制；
  - 不允许引用 assistant 消息；
  - 找不到证据时留空。

### 6.2 `core/uncertainty.py`

- 新增 `build_source_map(messages, vision_summary)`。
- 新增 `verify_slot_evidence()`。
- `assess()` 优先使用证据校验结果；无 evidence 时回退旧 `slot_status()`。
- 返回结构保持兼容：
  - `uncertainty_level`
  - `danger_veto`
  - `grounding_ratio`
  - `ungrounded_slots`
  - `uncertainty_signals`
- 新增内部字段 `slot_evidence_audit`，不进入用户可见响应。

### 6.3 `core/assistant_graph.py`

- `understand()` 将 `slot_evidence` 写入 issue，并确保 `_merge_persisted_slots()` 不丢失已有证据。
- 新槽位值覆盖旧值时，同时覆盖对应证据。
- `echo_slots()` 清空槽位时，同时清空对应证据。
- `unverified` 的汇总继续复用 `_unverified_by_issue()`。
- 不修改 `taxonomy` SSE payload 字段，证据不下发前端。

### 6.4 `core/langgraph_state.py`

- 不新增顶层通道，证据挂在 `issues` 中即可跨 checkpoint 持久化。
- 若后续需要独立审计通道，再新增 `slot_verification`，本阶段不做。

### 6.5 `config.py`

新增可选开关，便于影子运行和回滚：

```text
SLOT_EVIDENCE_MODE=off | shadow | enforce
```

建议默认：

```text
shadow
```

- `off`：完全走旧逻辑；
- `shadow`：计算新证据状态并记录日志，但实际报告仍按旧逻辑；
- `enforce`：新证据状态参与 `unverified` 和报告判断。

生产切换前先看影子日志的误判率。

## 7. 可观测性

### 7.1 日志字段

建议每个有槽位的 issue 记录：

```text
slot_evidence category=<code> slot=<key> status=<status> reason=<reason> source_ref=<ref>
```

不记录完整用户原文，避免日志泄漏敏感信息；如需调试，可记录 quote 的哈希或截断后的安全片段。

### 7.2 不展示给用户

- 不新增 SSE 事件。
- 不把 evidence 写入 `taxonomy`。
- 不写入报告 prompt。
- 不写入最终报告正文。
- 不通过 Java DTO 传递。

证据只用于：

1. 内部状态；
2. 调试日志；
3. 测试断言；
4. 后续事实确认节点的输入。

## 8. 测试设计

新增 `tests/test_slot_evidence.py`，至少覆盖：

1. `quote` 精确存在 -> `grounded`。
2. `quote` 不存在 -> `unverified`，原因 `quote_not_found`。
3. `source_ref` 不存在 -> `unverified`。
4. `source_ref` 指向 assistant -> `unverified`。
5. 槽位值只是隐患名称复述 -> `echo`。
6. 原文“没有冒烟”，槽位“冒烟” -> `contradicted` 或 `unverified`。
7. value 中数字能/不能在 quote 中找到。
8. 同义表达：原文“往一边斜”，value“墙体倾斜” -> `weak`，不能直接判为编造。
9. 多轮历史中 A 隐患的词不能支撑 B 隐患槽位。
10. 旧 checkpoint 无 evidence -> 回退旧 `slot_status()`。
11. `SLOT_EVIDENCE_MODE=shadow` 时不改变报告行为。
12. `SLOT_EVIDENCE_MODE=enforce` 时 `unverified` 正确汇总到 `ungrounded_slots`。
13. SSE `taxonomy` 中不出现 evidence 字段。

现有回归测试必须保持通过：

```text
tests/test_uncertainty.py
tests/test_uncertainty_gating.py
tests/test_echo_slots.py
tests/test_report_sections.py
tests/test_graph_state_persistence.py
tests/test_task_gate_interrupt.py
```

## 9. 验收标准

1. 新增证据字段能被解析、持久化、恢复。
2. 无证据的非法值不会静默进入完整报告。
3. 证据校验结果可追踪到来源编号和 reason。
4. 不改变 Java、MySQL、SSE 和前端契约。
5. 不改变 Skill 相关代码。
6. 影子模式下行为与当前版本一致。
7. 强制模式下既有测试通过，并新增证据测试全部通过。
8. 所有证据信息只在内部可见。

## 10. 实施顺序

1. 添加来源编号与证据 JSON 契约。
2. 扩展 `parse_plan()` 和 issue 结构。
3. 实现 `verify_slot_evidence()`。
4. 接入 `assess()`，保留旧逻辑回退。
5. 在 `understand()` 中持久化证据。
6. 增加 shadow 模式和日志。
7. 补齐单元测试与回归测试。
8. 做一轮真实对话影子对比，再决定是否开启 enforce。

## 11. 第二阶段 backlog（本文件不实施）

在证据链路稳定后，再处理以下逻辑缺陷：

1. 单条非焦点隐患缺失时，追问目标不能只看 `locked_subcategory`。
2. 多隐患时每轮允许并列追问，单隐患仍只问一个。
3. `unverified` 不直接进入初步报告，先进入事实确认节点。
4. 所有活跃隐患 A 类完整后才允许检索和完整报告。
5. 报告必须覆盖全部 issues，删除“只跟踪一个隐患”的旧提示词。
6. 任务建单闸门要求全部活跃隐患 A 类完整且已核实。

## 12. 风险与取舍

| 风险 | 处理 |
|---|---|
| 模型伪造 quote | 代码校验 quote 必须存在于指定来源 |
| quote 有效但语义不支持 | 先标 `weak`，后续接 NLI/确认节点 |
| 证据字段增加输出 token | 只对非空槽位要求 evidence |
| 旧 checkpoint 无 evidence | 保留旧词面校验回退 |
| 多轮/同轮跨隐患串位 | 使用 source_ref、quote 和轮次作用域降低串位；同轮多隐患的语义归属仍需后续 NLI/确认节点复核 |
| 误伤同义表达 | 先别名/字面支持，灰区保留 `weak`，不直接判编造 |
| 前端契约变化 | 本阶段完全不修改 SSE / DTO |

## 13. 面试表达

可以把这次改造表述为：

> 我们不直接相信模型抽取的槽位，而是要求模型提供原文证据，再由确定性代码验证证据是否存在、来源是否合法、数字是否一致，并把槽位状态分成 grounded / weak / unverified / echo。证据链只用于内部审计，不向用户展示。这样把“模型自述事实”变成了“可验证的事实引用”，同时保留了旧 checkpoint 和现有接口的兼容性。