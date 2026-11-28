# Rerank 隔离实验设计

> 状态：approved-for-spec-review
> 日期：2026-11-27
> 范围：主项目检索链路的可开关 rerank 实验
> 事实基线：`docs/evidence/2026-11-26-retrieval-baseline-refresh.md`

## 1. 背景

2026-11-26 在云主机本机使用真实 MySQL、Milvus 和 231 条案例完成检索复测：

- 64 条正样本、10 条负样本；
- 三种场景 Hit@5 = 1.000、大类Hit@5 = 1.000；
- MRR = 0.875～0.878；
- EmptyRate = 1.00；
- 每种场景有 14/64 条查询的首个正确结果在第 2～4 位。

当前案例以短文本为主，不做 chunking。可测优化点是候选集排序，因此设计可开关、可回退的 rerank 实验。

## 2. 目标

1. 扩大候选池，为 rerank 提供足够输入。
2. 增加统一 reranker 接口，默认关闭，不改变现有生产输出。
3. 支持 NoopReranker 作为基线，StubReranker 仅用于离线测试。
4. 提供独立评估脚本，比较原排序、扩大候选后的排序和 rerank 后的排序。
5. reranker 异常、超时、非法结果时回退原排序。
6. 实验结果通过门槛后，才讨论合并主项目或把实验转化为 Rag Lab。

## 3. 非目标

- 不修改当前默认 `hybrid_search` 行为。
- 不修改 chunking、Embedding、Milvus schema 或数据库表。
- 不把假 reranker 分数当真实模型效果。
- 不写入、更新或删除业务数据。
- 不在本阶段增加法规检索评估；法规查询集作为后续独立增量。
- 不在实验阶段直接开放数据库公网访问。

## 4. 方案选择

采用“可插拔接口优先”的方案：

- 第一版只实现接口、NoopReranker、StubReranker 和评估入口；
- 真实 reranker 通过依赖注入接入；
- 模型来源、计费方式和部署位置在评估前由单独配置确定；
- 未接入真实模型的 Stub 结果只能做行为测试，不能作为效果证据。

不采用直接绑定某个本地 cross-encoder 的方案，因为会增加模型下载、显存、启动时间和部署复杂度，无法先验证实验边界。
不采用直接让主项目 LLM 批量打分的方案，因为成本、延迟和输出稳定性尚未评估。

## 5. 架构

```text
HybridSearcher.retrieve_candidates()
  ├─ vector_search(top_k=10)
  └─ keyword_search(limit=10)
       ↓
  _merge_results(..., 10, 10)，保留现有去重和顺序规则
       ↓
  candidate list（最多 12 条）
       ↓
  Reranker.rerank(query, candidates, final_k=5)
       ↓
  final ranking（格式与现有输出兼容）
```

新增模块：

```text
core/reranker.py
eval/eval_rerank.py
tests/test_reranker.py
tests/test_rerank_evaluation.py
```

接口：

```python
class Reranker:
    def rerank(self, query: str, candidates: list[dict], final_k: int,
               cancellation=None) -> list[dict]:
        ...
```

实现：

- `NoopReranker`：原顺序返回前 `final_k` 条。
- `StubReranker`：只存在于测试，按测试指定规则重排。
- 真实 reranker：后续通过构造函数或工厂注入，不在本规格中写死模型。

## 6. 配置与回退

新增实验配置：

```text
RERANK_ENABLED=false
RERANK_CANDIDATE_K=10
RERANK_FINAL_K=5
RERANK_TIMEOUT_SECONDS=1.0
```

行为：

- `RERANK_ENABLED=false`：完全走原来的 3+3 检索路径。
- `RERANK_ENABLED=true`：只走实验入口，候选 k=10，最终 k=5。
- reranker 抛出异常、超时、返回非法结构、返回空结果：记录日志并回退原候选前 5 条。
- 不向浏览器暴露 reranker 分数、原始候选或内部错误。

## 7. 评估设计

### 对比组

1. `baseline`：现有 3+3，无 rerank。
2. `expanded`：10+10 候选，无 rerank。
3. `rerank`：10+10 候选 + 真实 reranker。

### 固定数据

- 64 条正样本查询；
- 10 条负样本；
- 231 条当前案例；
- 同一 query、同一 gold、同一排序合并规则；
- 同一云主机本机环境。

### 指标

- Hit@5；
- MRR；
- Top-1 命中数；
- P@5；
- P@ret；
- Recall@5 和设计上限；
- EmptyRate；
- 每次检索和 rerank 的 P50/P95 延迟；
- 失败案例。

### 预注册门槛

只有同时满足以下条件才通过：

1. Hit@5 不低于 baseline 的 1.000；
2. MRR 相比 baseline 至少提高 0.025 绝对值；
3. 14 条非 Top-1 查询中至少 5 条移动到第 1 位；
4. rerank 附加延迟 P95 不超过 300ms；
5. 10 条负样本 EmptyRate 仍为 1.00；
6. 真实模型调用有明确成本和超时记录。

不满足任一条：不合并主项目，实验代码归档到 Rag Lab。

## 8. 错误与安全

- rerank 输入只包含当前查询和候选文本，不包含用户隐私字段。
- reranker 不接收数据库连接，不执行写操作。
- 模型输出只接受候选 id 和分数；未知 id、重复 id、非数值分数都视为非法。
- 超时或异常不能阻断原检索结果。
- 评估脚本只读 MySQL/Milvus，不写业务数据。
- 外部模型凭据只从部署环境变量读取，不写入源码或日志。

## 9. 测试

离线测试：

- NoopReranker 保持顺序并截断到 final_k；
- StubReranker 能改变顺序，测试可断言；
- 候选合并复用现有 `_merge_results`；
- rerank 返回未知 id、空列表、重复 id 时回退；
- 超时和异常回退原结果；
- feature flag 关闭时输出与旧路径一致。

集成评估：

- 使用真实 64 条查询和 10 条负样本；
- 三组结果分别落盘；
- 记录代码 SHA256、数据量、模型版本、耗时和失败样本。

## 10. 变更文件

```text
ai-module/core/reranker.py
ai-module/eval/eval_rerank.py
ai-module/tests/test_reranker.py
ai-module/tests/test_rerank_evaluation.py
ai-module/config.py（仅实验配置）
ai-module/.env.example（仅占位符）
```

不修改：

```text
ai-module/tools/hybrid_search.py 的默认返回值
ai-module/core/assistant_graph.py
Milvus schema
MySQL schema
前端
```

## 11. 分支与回退

- 使用独立 worktree：`E:\java\newProject-rag-rerank`
- 分支：`codex/rag-rerank-experiment`
- 不基于当前未提交工作区修改
- 实验未通过时，删除 worktree 和分支；保留设计、评估脚本和实验报告到 Rag Lab
- 实验通过后，另行创建主项目集成计划，不直接合并未评审实验分支

## 12. 成功产物

- 可运行 reranker 接口与 Noop/Stub 测试；
- 独立 rerank 评估脚本；
- 三组对比结果；
- 一份 evidence 报告；
- 一个明确的合并/不合并结论。
