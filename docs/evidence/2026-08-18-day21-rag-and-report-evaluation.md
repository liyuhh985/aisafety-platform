> 状态：evidence
> 最后核对：2026-10-09

# Day 21 RAG 与报告评估实施计划

> 供执行者使用：按任务逐项完成。每一步采用先写失败测试、确认失败、最小实现、确认通过的方式。

**目标：** 为现有检索评估增加 `Recall@k`、`MRR`、负样本误召回和失败案例分析，并用固定样例检查报告的关键要点覆盖。

**架构：** `eval_rag.py` 在评估模式直接调用既有 `HybridSearcher.vector_search()` 和 `keyword_search()`，按生产 `hybrid_search()` 相同的关键词优先与 ID 去重规则构造有序结果。纯函数负责计算指标，因此单元测试不依赖 Milvus、MySQL、网络或模型凭证；脚本实跑仅负责调用真实检索和打印证据。

**技术栈：** Python 3、`unittest`、现有 `HybridSearcher`。

## 全局约束

- 只修改评估脚本、其离线测试和学习复盘；不修改生产检索、向量库结构、模型提示词或历史记忆。
- 测试必须使用固定输入，不访问网络、Milvus、MySQL 或模型服务。
- 真实脚本运行中的异常按失败案例计入分母，不能静默跳过。
- 不输出密码、Token、API Key 或真实连接字符串。

---

### 任务 1：建立可测试的排名和指标函数

**文件：**

- 修改：`ai-module/eval_rag.py`
- 新建：`ai-module/tests/test_eval_rag.py`

**接口：**

- 产出：`merge_ranked_results(keyword_results: list[dict], vector_results: list[dict]) -> list[dict]`
- 产出：`first_expected_rank(results: list[dict], expected_category: str) -> int | None`
- 产出：`recall_at_k(results: list[dict], expected_category: str, k: int) -> float`
- 产出：`reciprocal_rank(results: list[dict], expected_category: str) -> float`

- [ ] **步骤 1：写失败测试**

```python
from eval_rag import first_expected_rank, merge_ranked_results, recall_at_k, reciprocal_rank


def test_metrics_use_first_expected_category_in_deduplicated_order():
    results = merge_ranked_results(
        [{"id": 7, "category": "消防安全"}, {"id": 8, "category": "燃气安全"}],
        [{"id": 8, "category": "燃气安全"}, {"id": 9, "category": "建筑施工"}],
    )

    assert [result["id"] for result in results] == [7, 8, 9]
    assert first_expected_rank(results, "建筑施工") == 3
    assert recall_at_k(results, "建筑施工", 2) == 0.0
    assert recall_at_k(results, "建筑施工", 3) == 1.0
    assert reciprocal_rank(results, "建筑施工") == 1 / 3
```

- [ ] **步骤 2：确认测试因缺少接口失败**

运行：`Set-Location ai-module; python -m unittest tests.test_eval_rag`

预期：失败信息指出无法从 `eval_rag` 导入上述函数。

- [ ] **步骤 3：实现最小排名与指标函数**

```python
def merge_ranked_results(keyword_results: list[dict], vector_results: list[dict]) -> list[dict]:
    seen_ids: set[object] = set()
    ranked: list[dict] = []
    for result in [*keyword_results, *vector_results]:
        result_id = result.get("id")
        if result_id in seen_ids:
            continue
        seen_ids.add(result_id)
        ranked.append(dict(result))
    return ranked


def first_expected_rank(results: list[dict], expected_category: str) -> int | None:
    for rank, result in enumerate(results, start=1):
        if result.get("category") == expected_category:
            return rank
    return None


def recall_at_k(results: list[dict], expected_category: str, k: int) -> float:
    return float(first_expected_rank(results[:k], expected_category) is not None)


def reciprocal_rank(results: list[dict], expected_category: str) -> float:
    rank = first_expected_rank(results, expected_category)
    return 0.0 if rank is None else 1.0 / rank
```

- [ ] **步骤 4：确认测试通过**

运行：`Set-Location ai-module; python -m unittest tests.test_eval_rag`

预期：新增指标测试通过。

- [ ] **步骤 5：提交**

```powershell
git add ai-module/eval_rag.py ai-module/tests/test_eval_rag.py
git commit -m "feat: add deterministic RAG ranking metrics"
```

### 任务 2：加入负样本与失败分析

**文件：**

- 修改：`ai-module/eval_rag.py`
- 修改：`ai-module/tests/test_eval_rag.py`

**接口：**

- 产出：`NEGATIVE_EVAL_SET: list[dict]`，每项包含 `query` 和 `forbidden_category`。
- 产出：`evaluate_case(results: list[dict], case: dict, k: int = 3) -> dict`，正样本返回排名、`recall_at_k`、`rr` 和失败原因；负样本返回 `false_positive` 和失败原因。
- 产出：`format_failure(result: dict) -> str`，包含查询、排序类别与失败原因。

- [ ] **步骤 1：写失败测试**

```python
from eval_rag import evaluate_case


def test_negative_case_marks_forbidden_category_as_false_positive():
    evaluation = evaluate_case(
        [{"id": 1, "category": "燃气安全"}],
        {"query": "办公室照明损坏", "forbidden_category": "燃气安全"},
    )

    assert evaluation["false_positive"] is True
    assert evaluation["failure_reason"] == "负样本错误召回禁止类别"
```

- [ ] **步骤 2：确认测试因缺少负样本评估失败**

运行：`Set-Location ai-module; python -m unittest tests.test_eval_rag`

预期：失败信息指出 `evaluate_case` 不存在，或返回缺少 `false_positive`。

- [ ] **步骤 3：实现负样本集合、案例评估和失败格式化**

```python
NEGATIVE_EVAL_SET = [
    {"query": "办公室照明损坏", "forbidden_category": "燃气安全"},
    {"query": "小区绿化修剪", "forbidden_category": "建筑施工"},
]


def evaluate_case(results: list[dict], case: dict, k: int = 3) -> dict:
    categories = [result.get("category", "") for result in results]
    evaluation = {"query": case["query"], "categories": categories}
    if "forbidden_category" in case:
        forbidden = case["forbidden_category"]
        false_positive = forbidden in categories[:k]
        return evaluation | {
            "false_positive": false_positive,
            "failure_reason": "负样本错误召回禁止类别" if false_positive else "",
        }
    expected = case["expected_category"]
    rank = first_expected_rank(results, expected)
    return evaluation | {
        "rank": rank,
        "recall_at_k": recall_at_k(results, expected, k),
        "rr": reciprocal_rank(results, expected),
        "failure_reason": "前 k 条未命中期望类别" if rank is None or rank > k else "",
    }
```

- [ ] **步骤 4：让脚本用真实检索结果输出分组汇总与失败案例**

脚本调用顺序固定如下，保证评估排名与现有生产合并规则一致：

```python
vector_results = searcher.vector_search(query, "tb_hazard_case", top_k=3)
keyword_results = searcher.keyword_search(query, "tb_hazard_case", limit=3)
ranked_results = merge_ranked_results(keyword_results, vector_results)
```

按基础、困难、负样本三个集合分别打印数量、`Recall@3`、`MRR` 或负样本误召回率；每个失败案例打印 `format_failure()` 的结果。

- [ ] **步骤 5：确认离线测试通过**

运行：`Set-Location ai-module; python -m unittest tests.test_eval_rag`

预期：指标、负样本及失败分析测试全部通过。

- [ ] **步骤 6：提交**

```powershell
git add ai-module/eval_rag.py ai-module/tests/test_eval_rag.py
git commit -m "feat: analyze RAG negative retrieval failures"
```

### 任务 3：将报告检查改为固定评估样例

**文件：**

- 修改：`ai-module/eval_rag.py`
- 修改：`ai-module/tests/test_eval_rag.py`

**接口：**

- 产出：`REPORT_EVAL_SET: list[dict]`，每项包含 `name`、`report`、`required_keywords`、`forbidden_keywords`。
- 产出：`evaluate_report_case(case: dict) -> dict`，返回样例名和 `check_report()` 的检查结果。

- [ ] **步骤 1：写失败测试**

```python
from eval_rag import evaluate_report_case


def test_report_case_reports_missing_and_forbidden_points():
    result = evaluate_report_case({
        "name": "错误报告",
        "report": "发现燃气泄漏，建议立即通风。建筑施工已完成整改。",
        "required_keywords": ["燃气", "隔离"],
        "forbidden_keywords": ["建筑施工"],
    })

    assert result["name"] == "错误报告"
    assert result["missing"] == ["隔离"]
    assert result["hallucinated"] == ["建筑施工"]
    assert result["pass"] is False
```

- [ ] **步骤 2：确认测试因缺少报告案例评估失败**

运行：`Set-Location ai-module; python -m unittest tests.test_eval_rag`

预期：失败信息指出 `evaluate_report_case` 不存在。

- [ ] **步骤 3：实现固定报告样例与报告案例评估**

```python
REPORT_EVAL_SET = [
    {
        "name": "消防隐患报告",
        "report": "电动自行车入户充电存在火灾风险，属于消防安全隐患，建议清理楼道并停止充电。",
        "required_keywords": ["充电", "消防安全", "建议"],
        "forbidden_keywords": ["燃气泄漏"],
    },
]


def evaluate_report_case(case: dict) -> dict:
    return {"name": case["name"]} | check_report(
        case["report"],
        case["required_keywords"],
        case.get("forbidden_keywords", []),
    )
```

- [ ] **步骤 4：确认测试通过并运行全部离线测试**

运行：`Set-Location ai-module; python -m unittest tests.test_eval_rag tests.test_retrieval_contract`

预期：全部通过；现有检索合并契约保持不变。

- [ ] **步骤 5：实跑评估脚本并记录结果**

运行：`Set-Location ai-module; python eval_rag.py`

预期：基础和困难集合输出 `Recall@3`、`MRR`；负样本输出误召回率；报告样例输出缺失要点、错误主张和通过状态。将实际结果、失败案例和脚本运行异常记录到学习复盘，不得把异常当作成功。

- [ ] **步骤 6：追加 Day 21 复盘并提交**

追加到 `docs/superpowers/plans/2026-07-28-agent-application-learning-plan.md`：算法题、评估指标实际值、负样本和失败案例、报告检查边界、项目文件、资料来源以及下一日第一件事。

```powershell
git add ai-module/eval_rag.py ai-module/tests/test_eval_rag.py docs/superpowers/plans/2026-07-28-agent-application-learning-plan.md
git commit -m "feat: evaluate RAG retrieval and report coverage"
```
