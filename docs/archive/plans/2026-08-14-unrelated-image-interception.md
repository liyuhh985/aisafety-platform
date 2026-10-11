> 状态：implemented
> 最后核对：2026-10-09
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 无关图片拦截 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在视觉判断明确为无安全隐患时终止编排流程，同时对缺失判断字段保持 fail-safe 继续分析。

**Architecture:** 将视觉提示词收敛到 `prompts.py`，视觉 Agent 复用该常量。两个编排入口在视觉 JSON 已解析后使用严格的 `is False` 判断提前返回；测试在 Agent 和检索器边界使用 mock 验证外部调用未发生。

**Tech Stack:** Python 3, unittest, unittest.mock, FastAPI SSE payload format.

## Global Constraints

- 只有 `vision_result.get("has_hazard") is False` 才可中止流程。
- 字段缺失、`None` 或解析失败都必须继续既有流程。
- 不实现前端展示、`force_continue` 或评估集。
- 仅运行新增和受影响的编排器测试。

---

### Task 1: 统一视觉提示词

**Files:**
- Modify: `ai-module/prompts.py`
- Modify: `ai-module/agents/vision_agent.py`

**Interfaces:**
- Produces: `prompts.VISION_PROMPT`，供 `create_vision_agent` 传给 `MiMoVisionClient.analyze_json`。

- [x] **Step 1: 替换标准提示词**

在 `prompts.py` 定义 `VISION_PROMPT`，JSON 字段包含 `has_hazard`、`confidence`、`hazard_category`、`severity`、`description`、`reason_if_no_hazard`、`location_hint`、`rectification`，并写明明确无关才可返回 false、false 需理由、模糊图必须返回其他/低置信度。

- [x] **Step 2: 删除重复定义并导入常量**

在 `vision_agent.py` 添加：

```python
from prompts import VISION_PROMPT
```

删除文件尾部的本地 `VISION_PROMPT`，保留工具调用中的 `VISION_PROMPT` 参数。

### Task 2: 测试提前结束和 fail-safe

**Files:**
- Create: `ai-module/test_orchestrator_no_hazard.py`

**Interfaces:**
- Consumes: `Orchestrator.analyze_stream`、`Orchestrator.analyze`。
- Produces: 对 `no_hazard` SSE、非流式 `early_exit` 与缺字段继续处理的回归保护。

- [x] **Step 1: 写出失败的流式提前结束测试**

创建返回 `{"has_hazard": false, "reason_if_no_hazard": "人物肖像"}` 的 Vision stub，patch `searcher.hybrid_search` 和 Report stub。断言事件类型为：

```python
["status", "vision", "no_hazard", "done"]
```

并断言检索器和 Report 未调用。

- [x] **Step 2: 验证测试失败**

运行：

```powershell
python -m unittest test_orchestrator_no_hazard.OrchestratorNoHazardTest.test_stream_stops_before_retrieval_for_explicit_no_hazard -v
```

预期：由于尚未发出 `no_hazard` 或流程仍检索而失败。

- [x] **Step 3: 写出失败的非流式和缺字段测试**

非流式用例断言返回 `early_exit == "no_hazard"` 且无检索、无报告。缺字段用例令 Vision 返回不含 `has_hazard` 的有效 JSON，断言存在 retrieval、report 和最终 `done`。

- [x] **Step 4: 验证测试失败**

运行：

```powershell
python -m unittest test_orchestrator_no_hazard -v
```

预期：提前结束断言失败，缺字段用例保持通过或在测试 stub 配置完成后通过。

### Task 3: 实现编排器拦截

**Files:**
- Modify: `ai-module/core/orchestrator.py`
- Test: `ai-module/test_orchestrator_no_hazard.py`

**Interfaces:**
- Consumes: 成功解析的 `dict` 型视觉结果。
- Produces: 流式 `no_hazard` / `done` 事件与非流式 `results["early_exit"]`。

- [x] **Step 1: 实现流式分支**

在 `analyze_stream` 中，视觉事件和内存写入后、router 之前添加：

```python
if vision_result and vision_result.get("has_hazard") is False:
    yield self._sse("no_hazard", vision_result.get("reason_if_no_hazard", ""))
    yield self._sse("done", "")
    return
```

- [x] **Step 2: 实现非流式分支**

在 `_run_pipeline` 中视觉结果保存到 `results["vision"]` 后、router 之前添加：

```python
if vision_result and vision_result.get("has_hazard") is False:
    results["early_exit"] = "no_hazard"
    return results
```

- [x] **Step 3: 运行聚焦测试**

运行：

```powershell
python -m unittest test_orchestrator_no_hazard test_orchestrator_stream -v
```

预期：全部通过。

### Task 4: 复核变更

**Files:**
- Modify: `ai-module/prompts.py`
- Modify: `ai-module/agents/vision_agent.py`
- Modify: `ai-module/core/orchestrator.py`
- Create: `ai-module/test_orchestrator_no_hazard.py`

- [x] **Step 1: 检查唯一提示词来源**

运行：

```powershell
Select-String -Path ai-module\prompts.py,ai-module\agents\vision_agent.py -Pattern '^VISION_PROMPT\s*='
```

预期：仅 `ai-module/prompts.py` 定义该常量。

- [x] **Step 2: 检查计划覆盖与无占位内容**

确认每一项全局约束都有对应实现或测试步骤，且文档不含未完成占位标记。
