# Plan：评测体系重建（检索 + 分类）

依据：`docs/superpowers/specs/2026-09-27-eval-recalibration-design.md`

## 阶段 0：确认前提（已完成）

- [x] MySQL 分布核对：231 案例 / 129 法规，8 大类 32 小类，0 孤儿分类、0 空小类
- [x] Milvus 同步核对：`hazard_cases=231`、`hazard_regulations=129`、`hazard_policies=30`
- [x] 确认 `mysql_vector_search` 有 0.3 下限、Milvus 路径没有

## 阶段 1：检索评测脚本（`ai-module/eval_retrieval.py`，新建）

TDD，先写测试后写实现。

1. 写 `tests/test_eval_retrieval_metrics.py`（纯函数、不联网）：
   - `hit_at_k(ranked_ids, gold_ids, k)` → top-k 是否有交集
   - `mrr(ranked_ids, gold_ids)` → 第一条命中的 `1/rank`，无命中 0.0
   - `precision_at_k(ranked_ids, gold_ids, k)` → 分子是交集大小，分母固定 k
   - `recall_at_k(ranked_ids, gold_ids, k)` → 分母是金标准大小，且返回 `(值, 上限)`
   - `major_hit_at_k(...)`
   - 边界：空金标准、空结果、k 大于结果长度
2. 实现 `eval_retrieval.py`：
   - `load_gold_ids()`：按 category 从 MySQL 取 id 集合，启动时缓存一次
   - `QUERY_SET`：64 条（32 小类 × A 直白 / B 口语）
   - `NEGATIVE_SET`：10 条
   - `ranked_ids(query)`：复用 `searcher.keyword_search` + `searcher.vector_search`，
     按**生产合并顺序**重建排名（这点必须和生产一致，否则指标是自欺）
   - 自查：32 小类全覆盖，缺一即 `sys.exit(1)`
   - 输出：每条明细（金标准 id / 命中排名 / P@5）+ 汇总（Hit@5 / MRR / P@5 / Recall@k 带上限 / MajorHit@5）
   - 统计 embedding / Milvus 超时次数，单独打印，不计入失败
3. 跑一次真实评测，记录数字。

## 阶段 2：负样本阈值

1. 量分布：正样本 top1 分数 vs 负样本 top1 分数（打印两簇的分位）
2. 若可分 → 在 `core/case_relevance.py` 加 `min_score` 门槛（纯函数，配单测）并接进 `_issue_blocks`
3. 若不可分 → 不改，在 spec 里写明“测过，不可分，理由如下”
4. 重跑负样本集，报 `EmptyRate` 前后对比

## 阶段 3：分类评测（并行，独立文件）

产物：`ai-module/eval_classify.py` + 单测。
- 复用 `QUERY_SET`（从 `eval_retrieval.py` 导入，避免两套查询漂移）
- 走真实的 `understand` 节点，不另写一份提示词
- 每例 3 次采样，输出：小类准确率 / 大类准确率 / 混淆对 Top-10 / 采样极差

## 阶段 4：回归与文档

1. 跑全量 pytest，确认没碰坏别的东西
2. `eval_rag.py` 里过期的检索集加废弃注释并指向新脚本（报告评估部分不动）
3. spec 里回填实测数字

## 风险与边界

- Milvus / embedding 是远程依赖，会偶发超时 → 超时不算失败，但要计数
- 不改前端；不改生产对话流程（阶段 2 若引入阈值属于生产改动，必须先测分布）
- 不修既有的两个失败用例（`test_hazard_flow.py::test_report_writes_custom_chunks`、`test_vector_delete_api.py`）
