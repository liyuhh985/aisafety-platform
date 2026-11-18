# 评测与压测摘要

> 最后更新：2026-11-18

仓库保留可复现的评测脚本、最终指标和结论摘要。为避免公开真实街景文字、联系方式与模型原始响应，完整候选池、标注文件、逐样本预测、协商原始结果和过程日志已移至私有存档。

## 保留内容

- [模型对比与复核结论](./2026-09-29-final-experiment-and-peer-review-report.md)
- [会话分类评测规范结果](./2026-09-29-canonical-results.md)
- [建单 MQ 压测](./2026-10-11-hazard-create-mq-load.md)
- [Redis 基准测试](./redis-benchmark.md)

视觉评估代码与最终指标位于 [ai-module/eval/vision/v2](../../ai-module/eval/vision/v2/)，其中：

- `REPORT.model_consensus.md`：最终评测结论
- `ERROR_ANALYSIS.md`：误报与错分类分析
- `metrics.*.json`：冻结指标
- `tests/`：冻结、标注、评分与报告生成测试

## 口径说明

- 视觉评测是模型共识诊断集，不是人工 gold。
- 平衡测试集上的 FPR 不能直接表述为线上误报率。
- 压测数字用于说明系统容量边界，不代表生产 SLA。
- 完整实验原始响应和样本数据不进入公开仓库。
