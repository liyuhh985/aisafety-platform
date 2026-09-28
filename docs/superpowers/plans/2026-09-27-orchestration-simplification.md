# Plan：对话编排层简化

依据：`docs/superpowers/specs/2026-09-27-orchestration-simplification-design.md`

执行顺序不能颠倒：**先并危险信号，再删分支**（否则 `scope=emergency + immediate_danger=False`
这条输入会丢掉指引）。关键词那条线与图重构**改的文件不重叠**，可并行。

## 阶段 1：危险信号归一（前置，必须最先）

1. 先写测试 `tests/test_danger_signal_unification.py`：
   - `scope=emergency + immediate_danger=False` → `danger_veto=True`
   - `scope=hazard + immediate_danger=True` → `danger_veto=True`
   - 危险词表命中 → `danger_veto=True`
   - 三者都不满足 → `danger_veto=False`
2. 改 `danger_veto` 计算处，把 `planner.scope == "emergency"` 并入。
3. 跑测试，并确认既有危险用例不回归（`tests/test_uncertainty*.py`、`tests/test_agent_hardening.py`）。

## 阶段 2：删 `emergency_reply` 分支

4. `direct_reply` 去掉 `emergency_reply` 分支（`scope_response` 的 emergency 模板不再使用）。
5. 补测试：危险输入走 `plan.ok` 时，回复**包含指引且在最后一段之前**，且**不含追问**。
6. 确认 `EMERGENCY_RESPONSE` 与 `scope_response` 的关系：若 `scope_response` 仍被
   `boundary_reply` 使用则保留常量，仅删除 emergency 目标；无用则一并清理。

## 阶段 3：拆回复节点 + `route` 多出口（纯重构）

7. 先写"行为不变"对照测试：同一组固定 state 输入，记录重构前 `direct_reply` 的输出文本，作为基线。
8. 拆出 4 个节点：`boundary_reply` / `smalltalk_reply` / `answer_reply` / `fallback_reply`。
9. `route` 改多出口（返回 `Command(goto=...)`），**分发优先级与重构前逐条对齐**。
10. `STATUS_TEXT` 补 4 个新键；删掉已不存在的节点键。
11. 跑对照测试，确认输出文本逐字一致；再跑全量 pytest。

## 阶段 4：状态文案带上下文

12. `STATUS_TEXT` 支持参数化：`"正在检索「{category}」的相关法规…"`。
13. 新增约束单测：所有 status 文本 ≤ 20 字、非空、不含营销词（解构/深度研判/智能研判…）。
14. 写前端大纲 `docs/superpowers/specs/2026-09-27-assistant-status-text-contract.md`（给前端模型）。

## 阶段 5：关键词分支 + 评测口径（并行线，独立文件）

15. 先改评测口径：`eval_retrieval.py` 走 `_pick_keyword` + `hybrid_search`，分"槽位空/有值"跑基线。
16. `keyword_search` 引入分词 OR 匹配 + 命中打分排序；空关键词返回 `[]`，配单测。
17. `_pick_keyword` 去掉小类标签，只留槽位值。
18. 重跑评测，把前后数字写回 spec。

## 阶段 6：部署与线上验证

19. 全量 pytest → 打包 → 备份 → 上传 → 编译导入校验 → 重启 8000 → 健康检查。
20. 线上冒烟：
    - 危险输入（"楼道里全是浓烟，人都出不来"）：有指引、无追问
    - 普通输入（"消防设施老旧"）：能出答
    - 越界输入（"红烧肉怎么做好吃"）：被拒
    - 线上直接调 `_pick_keyword` + `keyword_search` 验证关键词分支
21. 记录部署报告（备份路径 / pid / 健康检查 / 冒烟结果）。

## 风险与约定

- 阶段 3 是纯重构：**任何输出文本变化都算失败**，不是"可以接受"。
- 只改 `ai-module`，不碰前端与 Java。
- 不修 `tests/test_vector_delete_api.py`（既有失败，另一条线）。
- 改动不提交（用户未要求）。
