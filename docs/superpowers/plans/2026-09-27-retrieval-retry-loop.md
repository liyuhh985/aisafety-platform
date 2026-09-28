# Plan：检索自评重试环

依据：`docs/superpowers/specs/2026-09-27-retrieval-retry-loop-design.md`

## 阶段 1：先量触发率（决定要不要真的启用）

1. 写一个只读测量脚本（不改生产代码），对 64 条查询 × 两种情形（槽位空/有值）统计：
   - T1 命中数（`ungrounded_slots` 非空 —— 需要规划器真实输出，先用现有评测的槽位 fixture 近似并标注）
   - T2 命中数（`filter_by_major` 返回 `NO_MATCH`）
   - T3 命中数（top1 分数 < 0.58）
   - 三条的并集（真实触发率）
2. 输出到 `db/eval_retry_trigger.txt`。
3. **如果并集为 0，停止，把结论写回 spec**（"测过，触发率为 0，不启用" + 数字）。

## 阶段 2：TDD 实现

4. 先写纯函数 `should_retry_retrieval(state) -> tuple[bool, str]`（返回是否重试 + 触发原因），
   配 `tests/test_retrieval_retry.py`：
   - T1/T2/T3 各自触发
   - 三者都不满足 → 不触发
   - `retrieval_attempts >= 1` → 即使 T1/T2/T3 成立也不触发
   - 返回的 reason 可读
5. 实现 `evaluate_retrieval` 节点（代码判定，无 LLM）。
6. 实现 `rewrite_query` 节点（模型产出新的检索串），提示词约束"标签 + 槽位值"形状。
7. 改图接线：`retrieve → evaluate_retrieval`；`evaluate_retrieval` 条件边 → `rewrite_query` / `report`；
   `rewrite_query → search`（回边）。
8. `begin_turn` 重置 `retrieval_attempts`（每轮独立）。
9. 确认 reducer 汇聚点：`evaluate_retrieval` 必须只跑一次（用单测锁，参考 `report` 现在的行为）。

## 阶段 3：验证与对照

10. 跑评测，报告：触发次数、T1/T2/T3 分布、触发前后 top1 分数变化。
11. 按验收标准第 2 条判定：提升为 0 就把 `RETRY_ENABLED` 默认关闭，并写明理由。
12. 全量 pytest。
13. 延迟对照：不触发路径不得变慢。

## 阶段 4：部署与线上验证

14. 打包 → 备份 → 上传 → 编译校验 → 重启 8000 → 健康检查。
15. 线上冒烟：一条会触发 T3 的输入 + 一条普通输入；确认前者日志里有重试记录、后者无额外调用。
16. 部署报告。

## 风险

- 环的接线最容易出问题（reducer 汇聚点、`Send` 扇出后节点跑几次）→ 阶段 2 第 9 条必须先用单测确认。
- 重试会改善分数也可能不改善；**不改善就默认关闭**，不留死循环。
