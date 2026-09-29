# 执行计划：规划器漏放修复 + 关键指标方差

日期：2026-09-29　　设计：`docs/superpowers/specs/2026-09-29-object-claim-grounding-design.md`

## 阶段 0：复现与定位（已完成）

- `db/_diag_planner_leak.py`（各 3 次）：两条已知漏放的来源是**规划器自己**判 hazard + 给 issues。
- `db/_diag_anchor_coverage.py`：40 条现实口吻本领域表述里 11 条不含 `DOMAIN_KEYWORDS` 词
  → 通用「必须有域锚」不可行，规则必须窄。
- 结论写进 spec §1–§3。

## 阶段 1：代码否决（TDD）

1. `tests/test_scope_policy.py` 先加失败用例：
   - 漏放输入（声称 `traffic_facility_damage`、原文无物件词无场所词）→ 必须不是 hazard；
   - 5 个物件型小类：给物件词 → hazard；给场所词 → hazard；
   - 非物件型小类（如 `fire_lane_blocked` + 「楼道里堆了很多纸箱」）→ 不受影响，仍 hazard；
   - `support_text`（视觉摘要）能作为依据。
2. `core/scope_policy.py`：`OBJECT_CLASS_EVIDENCE` + `PUBLIC_SPACE_WORDS` + `unbacked_object_claim()`，
   并在 `decide_scope` 的 `issues` 分支里否决（返回 `ambiguous`）。`decide_scope` 新增
   可选参数 `support_text`（默认空，既有调用点不受影响）。
3. `core/assistant_graph.py::scope_guard` 传 `support_text=vision_summary`。
4. `core/dialogue_understanding.py::_planner_system_prompt` 补一条判据（软的一侧，见 spec §6）。

## 阶段 2：回归

- 全量 `pytest`（基线 767 passed, 3 skipped, 5 xfailed）。
- 变异实验：否决条件改恒 False → 新用例必须复现漏放。

## 阶段 3：部署 + 线上端到端（每例 3 次 → 方差）

- 打包部署、`restart_ai_tmp.sh`、health 200。
- `db/measure_object_claim_grounding.py`：9 条越界 + 12 条本领域，每例 3 次，逐条落盘。

## 阶段 4：三个关键指标的方差（每例重复 3 次，报区间）

| 指标 | 脚本 | 口径 |
| --- | --- | --- |
| 分类准确率 | `eval_classify.py --samples 3`（已有 ±） | 64 正 + 10 负 × 3 |
| 追问命中率 | `db/measure_missing_to_planner.py` 加 3 次采样 | 每例 3 次，命中=A 类缺失 |
| 护栏拦截率 | 阶段 3 的产物（越界 9 条 × 3）+ 负样本 10 × 3 | 被拦 = 不产报告；分别报"软拦(含 ambiguous)"与"硬拦(out_of_scope)" |

## 阶段 5：文档收口

- 把实测数字写回 spec 与执行文档；登记已知残留。

## 实测结果（2026-09-29）

- 阶段 2：全量 pytest **798 passed, 3 skipped, 5 xfailed, 0 failed**（新增 26 条用例；另有 1 条
  与本次无关的、仓库里未纳入版本管理的 `test_server_upload_validation.py` 失败，改动前后都在）。
  变异实验：否决条件改恒 False → 5 条用例复现漏放（证明测试有效）。
- 阶段 3：部署 `20260929T110559`，health 200；线上 3 次采样见
  `db/eval_object_claim_grounding.txt` —— 本领域 36/36 保持，越界 27/27 不进检索。
- 阶段 4（三个关键指标的方差，每例 3 次）：
  | 指标 | 区间 | 说明 |
  | --- | --- | --- |
  | 分类准确率（小类） | 0.917 ± 0.016（同日 A/B 两臂一致） | 跨运行噪声 ≈ 0.02，见 spec §8.2 |
  | 追问命中率 | 人工复核 0.900~0.900（极差 0）；启发式 0.600~0.800（极差 0.2） | 极差主要来自量具，见 `db/eval_followup_hit_variance.txt` 人工复核段 |
  | 护栏拦截率 | 越界 27/27 不进检索；负样本 30/30 被拦（1.000 ± 0.000）；误拦真隐患 0/192 | 两个臂一致 |
- 阶段 5：数字与残留已写回本文与 spec §8。
