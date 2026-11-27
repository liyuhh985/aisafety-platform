# Rerank 生产口径验收报告

> 状态：FAILED
> 日期：2026-11-27
> 基座：origin/main@7d98f67
> 集成代码：dd8736d

## 结论

**未通过，不合并、不开启。**

本次使用最新主线的真实 Skill Router + Planner 预测大类/子类，没有使用 gold oracle major；gold 仅用于检索后的评分。

## 数据与调用

- 案例：231
- 正样本：64
- 负样本：10
- 模型：BAAI/bge-reranker-v2-m3
- reranker mode：http / fallback
- 生产预测：74/74 成功
- 大类错配：0
- 子类错配：1

## 指标

| 模式 | Hit@5 | MRR | Top-1 | EmptyRate | rerank P95 | 增量 P95 | 成功/尝试 | fallback |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0.9688 | 0.8763 | 52 | 1.0000 | 0.00ms | — | 0/0 | 0 |
| candidates | 0.9844 | 0.9250 | 56 | 1.0000 | 0.00ms | 51.46ms | 0/0 | 0 |
| rerank | 0.9844 | 0.9146 | 56 | 1.0000 | 567.65ms | 570.43ms | 63/64 | 1 |

## Gate 失败项

- Hit@5 fell below 1.000
- Top-1 hits below baseline + 5
- Top-1 regression detected
- reranker successful responses below attempts
- reranker fallback count must be 0
- rerank P95 exceeds 350ms
- end-to-end added P95 exceeds 500ms

## 生产预测诊断

生产大类错配为 0；生产子类错配为 1。

| 查询 | gold major/sub | predicted major/sub |
|---|---|---|
| 那栋老楼早就不行了，墙都是歪的，里头还住着人 | building/dangerous_building | building/wall_crack_lean |

## 延迟与 fallback

- rerank P95：567.65ms，门槛 <=350ms
- 端到端增量 P95：570.43ms，门槛 <=500ms
- rerank fallback：1，原因：{'exception:ReadTimeout': 1}

## 产物

- docs/evidence/2026-11-27-rerank-production-gate.raw.json
- docs/evidence/2026-11-27-rerank-production-gate.run.log
- ai-module/db/eval_rerank_output.json 是生成物，已加入 .gitignore

## 决策

- 不合并主项目
- 不修改 RERANK_ENABLED 默认值
- 保持 RERANK_ENABLED=false
- 保留本分支与 evidence 作为 Rag Lab 材料
- 不调整门槛、不改 query/gold 后重复跑
