# Single-Session Handoff: Agent Grounding Harness V2

> 状态：current
> 日期：2026-11-24
> 用途：交给同一个执行会话，按顺序完成“追问/报告门禁修正 + 双模型语义复核”
> 禁止：把本任务拆给多个会话并行修改 `assistant_graph.py` / `uncertainty.py`

## 1. 任务目标

在一个会话内完成两条前后依赖的工作：

```text
Phase A：追问选择、焦点语义、严格 A 类报告门禁
Phase B：双模型伪标签、阈值校准、运行时语义复核
```

Phase B 的运行时部分依赖 Phase A 完成后的 `missing` 重算和全 issue 追问逻辑，因此必须顺序执行，不能并行改同一批核心文件。

---

## 2. 必读文档

按以下顺序阅读：

1. `docs/superpowers/plans/2026-11-24-single-session-agent-grounding-handoff.md`
2. `docs/superpowers/plans/2026-11-24-dual-model-semantic-verifier.md`
3. `docs/superpowers/specs/2026-11-22-evidence-grounded-slot-verification-design.md`
4. `docs/superpowers/specs/2026-11-22-agent-skill-harness-design.md`

已实现的内容不要重做：

```text
- evidence quote / source_ref / SSE 脱敏
- 8 个 canonical SKILL.md
- skill_route -> understand
- active_skills 与 locked_majors 对齐
- interrupt 证据脱敏
```

已废弃的文档不要执行：

```text
docs/superpowers/plans/2026-11-24-semantic-grounding-verifier.md
```

该单模型计划已被双模型计划替代。

---

## 3. 工作区规则

当前仓库存在与本任务无关的视觉评估脏文件。执行会话必须：

- 不清理、不提交、不格式化无关文件；
- 只暂存本任务实际修改的文件；
- 每个小任务独立提交；
- 不推送 GitHub，除非用户明确要求；
- 不修改 Java、MySQL、SSE 契约；
- 不把证据写入 taxonomy、interrupt、报告 Prompt、报告正文或 Java DTO。

建议从当前 HEAD 创建分支：

```bash
git switch -c codex/agent-grounding-v2
```

---

## 4. Phase A：先修追问与报告门禁

### A1. 焦点语义收口

目标：

```text
焦点只影响排序、展示和报告先写哪条。
焦点不影响：
- 追问目标
- A 类完整性
- 报告覆盖范围
- 建单门禁
- 工具白名单
```

为兼容旧 checkpoint，可以暂时保留 `locked_subcategory` 字段，但不得继续作为“只问焦点”的唯一目标来源。

### A2. 追问目标扫描全部 active issues

实现规则：

```text
扫描全部 issues
  -> 找所有 missing A 槽位
  -> 只有一条缺失：单条追问，目标就是这条 issue
  -> 两条及以上缺失：并列追问，每条一个 A 类槽位
  -> 非焦点 issue 缺 A 类：必须能被选中追问
```

最小改造点：

- `_decision_slot_keys()` 不能再只读 `locked_subcategory`；
- `ask_slot_question()` 的单条路径必须能选择任意未完整 issue；
- `_parallel_slot_question()` 继续保留“每条一个问点”；
- 去掉“只有焦点缺失才可单条追问”的隐含限制。

验收：

```text
- 焦点完整、非焦点缺 A 类 -> 追问非焦点
- 两条 issue 各缺 A 类 -> 一条并列追问
- 单 issue 缺 A 类 -> 只问一个问题
- 问句不得出现“请确认我理解得对不对”之类的事实确认轮次
```

### A3. 缺 A 类时禁止检索和正式报告

正常对话策略：

```text
任意 active issue 有 missing A
    -> ask_critical_question
    -> 不进入 search
    -> 不生成正式报告
```

只有：

```text
全部 active issues 的 missing 为空
并且没有任何 unverified/unavailable 影响事实完整性
    -> search
    -> full report
```

保留特殊分支：

```text
即时危险 -> emergency_guidance
用户明确拒绝追问 -> 初步判断，但不做正式报告
```

删除或绕过当前旧策略：

```text
complete and incomplete -> report_preliminary
explicit report + incomplete -> report_preliminary
```

### A4. 报告覆盖全部 active issues

报告 Prompt 必须：

```text
- 删除“本次对话只跟踪这一个隐患”
- 明确列出 issues 数量
- 要求逐条写所有 issues
- 焦点 issue 只决定顺序，不裁掉其他 issue
```

验收：

```text
- 两条完整 issue -> 报告 Prompt 包含两个 issue block
- 一条完整、一条不完整 -> 不进入完整报告
- 不再出现“只针对一个隐患输出”
```

### A5. Phase A 测试与提交

新增或修改：

```text
tests/test_multi_hazard_question_policy.py
tests/test_dialogue_policy.py
tests/test_report_sections.py
tests/test_task_gate_interrupt.py
```

必须通过的定向测试：

```bash
python -m pytest tests/test_multi_hazard_question_policy.py tests/test_dialogue_policy.py tests/test_report_sections.py tests/test_task_gate_interrupt.py -q
```

Phase A 完成后单独提交：

```bash
git add <Phase A files>
git commit -m "fix(ai): question all incomplete hazards before reporting"
```

---

## 5. Phase B：执行双模型语义复核

完成 Phase A 后，严格按以下文档的 Task 1～Task 11 顺序执行：

```text
docs/superpowers/plans/2026-11-24-dual-model-semantic-verifier.md
```

### B1. 执行顺序

```text
Task 1  Agent dedicated zero-temperature mode
Task 2  数据集协议与校验
Task 3  确定性预过滤
Task 4  双模型配置与 JSONL 标注
Task 5  consensus + agreement + kappa
Task 6  dev 阈值校准
Task 7  test 冻结与一次性评估
Task 8  runtime dual-model semantic verifier
Task 9  四个 business_status
Task 10 understand 集成与 missing 重算
Task 11 off/shadow、SSE 边界、完整回归
```

### B2. 运行时固定策略

```text
A 类：
    MiniMax 与 GLM 都 entailed 且 min_confidence >= T_A
        -> grounded_by_model
    两模型都 contradicted 且 min_confidence >= T_C
        -> rejected
    其他
        -> unavailable

B 类：
    Model A entailed 且 confidence >= T_B
        -> grounded_by_model
    Model A contradicted，再调用 Model B 确认
        两模型都 contradicted 且 min >= T_C
            -> rejected
        否则
            -> unavailable
```

调用上限：

```text
每轮 Model A 最多 1 次
每轮 Model B 最多 1 次
总候选最多 5 个
A 类候选优先
```

### B3. 业务状态

```text
grounded            direct quote support
grounded_by_model   dual/single model consensus accepted
rejected            invalid evidence or contradiction confirmed
unavailable         weak/neutral/model failure/echo/missing
```

### B4. 槽位处理

```text
rejected / unavailable
    -> 从 issue slots 和 category_slots 删除
    -> 重算 missing / report_missing

A 类 unavailable
    -> 回到 missing
    -> 下一轮重新问原槽位

B 类 unavailable
    -> 进入 report_missing
    -> 报告中只能写条件分支，不得当确定事实
```

禁止：

```text
- 新增人工确认节点
- 新增“请确认我理解是否正确”轮次
- verifier 失败时自动接受
- 双模型分歧时自动选择其中一边
```

### B5. 数据集和评估边界

```text
- 150 条基础样本：entailed/neutral/contradicted 各 50
- dev 90 / test 60，按 source_group_id 隔离
- 20～30 条 boundary 样本单独保存，不参与阈值选择
- agreement >= 0.75
- Cohen's kappa >= 0.60
- threshold scan: 0.70, 0.75, 0.80, 0.85, 0.90, 0.95
- A precision target >= 0.98
- B precision target >= 0.95
- test 冻结后只跑一次
```

报告必须写：

```text
Thresholds are calibrated against dual-model consensus pseudo-labels.
No human review was performed.
Test metrics are pseudo-label agreement metrics, not production accuracy.
```

### B6. Phase B 测试与提交

按双模型文档中的 Task 提交粒度执行。最后运行：

```bash
python -m pytest tests -q --ignore=tests/test_memory_store.py
python -m compileall core eval tests -q
```

预期：

```text
全部测试通过；外部 MySQL 不可用时只排除 test_memory_store.py
```

---

## 6. 完成定义

一个会话只有在以下条件全部满足时才算完成：

```text
1. Phase A 全部测试通过并提交
2. 双模型离线数据集与协议可校验
3. agreement/kappa 质量门禁可运行
4. dev 阈值校准完成
5. test 冻结产物存在
6. runtime semantic verifier 接入 understand
7. A 类 unavailable 回到 missing
8. B 类 unavailable 进入 report_missing
9. 报告覆盖全部 active issues
10. 无人工确认轮次
11. 证据不出 SSE/interrupt/report
12. off/shadow 行为保持不变
13. 完整 AI 回归通过
14. 不触碰无关脏文件
15. 不自动推送 GitHub
```

---

## 7. 可直接粘贴给执行会话的指令

```text
你在一个会话内执行 Agent Grounding Harness V2。

先读取：
1. docs/superpowers/plans/2026-11-24-single-session-agent-grounding-handoff.md
2. docs/superpowers/plans/2026-11-24-dual-model-semantic-verifier.md
3. docs/superpowers/specs/2026-11-22-evidence-grounded-slot-verification-design.md
4. docs/superpowers/specs/2026-11-22-agent-skill-harness-design.md

不要执行 docs/superpowers/plans/2026-11-24-semantic-grounding-verifier.md，它已被替代。

按顺序执行：
Phase A：先修正焦点语义、全部 active issue 的 A 类追问、严格 A 类报告门禁、报告覆盖全部 issues。
Phase B：再按 dual-model-semantic-verifier.md 的 Task 1～Task 11 完成双模型伪标签、阈值校准和 runtime semantic verifier。

要求：
- 测试先行，每个任务独立提交。
- 不新增人工确认节点。
- A 类双模型一致，B 类单模型高阈值 + 双模型矛盾确认。
- unavailable/rejected 槽位必须从可用 slots 删除并重算 missing/report_missing。
- 证据不得进入 SSE、interrupt、报告、Java/MySQL。
- 不修改无关脏文件，不推送 GitHub。
- 完成后报告提交列表、测试结果、未解决风险和未执行事项。
```