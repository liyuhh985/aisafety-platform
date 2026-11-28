> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/agent-orchestration.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# LangGraph 迁移与深度升级实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把安全隐患平台「新版 AI 助手」（手写 ReAct）迁移到 LangGraph，并在其上实现「反思/评审 + 可观测 Trace + Human-in-the-loop 整改闭环」三个深度点，最终形成可面试、可申述的 Agent 项目。

**Architecture:** 用 LangGraph `StateGraph` 建模为 `route → (clarify | analyze_image | search) → report → grade → (report|END)` 的多轮 agent 图；以 `checkpointer` 按 `session_id` 持久化多轮状态（替代当前手写 `WorkingMemory` 的多轮记忆）；保留当前手写 ReAct 版本到 `legacy/` 作差异化对照。

**Tech Stack:** Python 3.11、FastAPI、`langgraph`、`langchain-core`（仅用 messages/state，不引重框架）、requests、pymysql、pymilvus、SSE。

## Global Constraints

1. **SSE 事件契约不变**：`assistant_stream` 对外仍输出 `data: {"type": kind, "content": text}`，`kind ∈ {status, chunk, error, done}`。
2. **模型降级保留**：主 `mimo-v2.5-pro`（90s 超时）→ 备 `mimo-v2.5`（90s）；超时/429/500/502/503/504 触发 `[FALLBACK]`，不做破坏性中断。
3. **多轮上限保留**：最多 5 轮（含追问与检索），超限友好收尾。
4. **疑问句放行保留**：内容含 `？/?` 且尚无工具结果时直接产出追问文本，不强制 `required_tool`。
5. **检索兜底保留**：`search_regulation/search_cases` 走 `hybrid_search`，10s 超时返回 `[检索失败]`，错误文本作为工具结果且**不重试**（避免死循环）。
6. **识图唯一性保留**：`analyze_image(mimo-v2.5, 60s)` 写死先调一次；失败注入 `[视觉分析失败，请仅按用户文字描述判断]`，历史已有视觉结果则不再重复调。
7. **保留手写版到 `legacy/`**：`core/agent.py` + `core/assistant_agent.py` 复制过去，作为「为什么不用框架」的对照。
8. **依赖限定**：`langgraph>=0.2`、`langchain-core>=0.3`；不引入 langchain 全量、不引 langchain-community。
9. **Java 侧不受影响**：`AiService.assistantStream` 期待的 SSE 格式不变，后端只改 Python `server.py` 的调用内部。

---

## 迁移前基线（现状，动代码前先确认）

- `core/agent.py::Agent`：手写 ReAct 循环（`_call_llm` + `_call_llm_stream_events` + 工具执行 + 模型降级）。
- `core/assistant_agent.py::ASSISTANT_SYSTEM`：身份 + 多轮澄清规则 + 工具规则 + 三段式要求；`create_assistant_agent()` 返回 `Agent`。
- `tools/assistant_tools.py::ASSISTANT_TOOLS`：`search_cases` / `search_regulation` / `analyze_image`。
- `core/memory.py::WorkingMemory`：session 级，`max_turns=10`，`_trim()` 保留最近 `max_turns*2` 条消息；`sessions: dict[str, WorkingMemory]`。
- `server.py::assistant_stream`：接收 JSON 或 multipart（带 file），先 `analyze_image` 注入历史，再从 `get_session(sid).get_history()` 截取，`assistant.run_stream_events(...)`，`yield ("kind", text)`。

---

## 目标文件结构

| 文件 | 责任 |
|---|---|
| `core/langgraph_state.py` | 定义 `AssistantState`（TypedDict）+ 默认值 |
| `core/assistant_graph.py` | 构建 `StateGraph`：节点 + 条件边 + checkpointer |
| `core/grader_node.py` | 反思/评审节点 `grade`（Day2） |
| `core/trace.py` | 结构化 trace 工具（Day3） |
| `core/hitl_node.py` | Human-in-the-loop 整改任务节点（Day3） |
| `server.py`（改）| `assistant_stream` 改调 `assistant_graph`，保留 SSE 事件契约 |
| `requirements.txt`（改）| + `langgraph`、`langchain-core` |
| `legacy/`（新建）| 复制现有 `agent.py`、`assistant_agent.py` 留底 |
| `tests/test_assistant_graph.py` 等 | 每个深度点的测试 |

---

## Day 1：LangGraph 核心 + 迁移（产出：可运行的 LangGraph 助手，行为与现状一致）

**今天学（先讲透再动手）**：`StateGraph`、`TypedDict` 状态、`add_node`/`add_edge`/`add_conditional_edges`/`set_entry_point`、`InMemorySaver`（checkpointer）、`compile() + stream()`。

### Task 1.1 依赖与留底
- [ ] **依赖**：`requirements.txt` 增加 `langgraph>=0.2`、`langchain-core>=0.3`，`pip install` 安装。
- [ ] **留底**：`mkdir legacy`，复制 `core/agent.py`、`core/assistant_agent.py` 到 `legacy/`。

### Task 1.2 定义状态
`core/langgraph_state.py`：
```python
from typing import TypedDict, Optional
from langchain_core.messages import BaseMessage

class AssistantState(TypedDict, total=False):
    session_id: str
    messages: list[BaseMessage]          # 当前图内消息（含系统/用户/助手）
    slots: dict[str, str]                # {"behavior","persistence","blocked"} 填槽
    vision_summary: str                  # [视觉分析] 结果
    regulation_results: str              # search_regulation 输出
    case_results: str                    # search_cases 输出
    draft_report: str                    # report 节点产出（三段式）
    grade_feedback: str                  # grade 节点的评审意见
    attempts: int                        # 反思重试次数
    needs_clarify: bool                  # 是否还缺槽位（route 判定用）
```

### Task 1.3 节点路由（多轮澄清）
- **节点**：`route`（判定 needs_clarify / 是否需要看图 / 是否可出结论）、`clarify`（一次只问一个槽位）、`search`（调 regulation→case）、`report`（生成三段式）。
- **复用**：`tools/assistant_tools.py` 的 `ASSISTANT_TOOLS`、`core/agent.py` 的模型降级调用（单独抽成 `_call_llm` 复用），`ASSISTANT_SYSTEM` 放入 graph 的起始 system message。
- [ ] **Step**：实现 `route` 节点（读 `slots` + `vision_summary`，决定走哪条边）。
- [ ] **Step**：实现 `clarify` 节点（用 `_call_llm` 一次追问一个缺失槽位，更新 `slots`）。
- [ ] **Step**：实现 `search` 节点（调两个检索工具，结果写 state，非法关键词返回 `[检索失败]` 且不重试）。
- [ ] **Step**：实现 `report` 节点（`_call_llm` 生成三段式，写 `draft_report`）。

### Task 1.4 条件边 wiring
- `add_conditional_edges("route", route_decider, {"clarify","search","analyze_image","report"})`
- `add_conditional_edges("report", report_end, {"END"})`
- `set_entry_point("route")`
- [ ] **Step**：用 `InMemorySaver` 作为 checkpointer，`compile(checkpointer=saver)`；`thread_id=session_id`。

### Task 1.5 接入 SSE
- 改 `server.py::assistant_stream`：把 `assistant.run_stream_events(...)` 替换为 `for event in assistant_graph.stream(input, config={"configurable":{"thread_id": sid}, "stream_mode":"messages"})`，把 chunk 映射成 `yield ("chunk", delta)`、错误映射成 `yield ("error", msg)`、结束映射成 `yield ("done","")`。
- [ ] **Step**：SSE 契约逐事件对齐。

### Task 1.6 验证
- [ ] 运行 `python -m pytest tests/assistant -q`（现有测试）。
- [ ] 用 `test_images/day33_excavator.jpg` 走一遍：识图→多轮→检索→三段式，与手写版输出一致。
- [ ] 多轮追问：只回半句能逐步填槽。
- [ ] 疑问句放行：用户直接问句时输出追问，不强制调工具。

---

## Day 2：反思/评审（产出：`report → grade → (report|END)` 的自主反思循环）

**今天学**：`add_conditional_edges` 的回环用法、`State` 里的 `attempts` 上限、评审 prompt 构造。

### Task 2.1 评审 prompt 与节点
`core/grader_node.py`：
```python
GRADER_SYSTEM = """你是质量评审。对报告打分并给出简短意见。
判不合格的情况：
1. 没有回答用户问题（跑题）
2. 编造了工具结果里没有的内容（幻觉）
3. 关键信息缺：长期/临时、是否堵死、行为类型
4. 没有三段式（### 一/二/三）
输出 JSON: {"pass": true|false, "reason": "..."}
"""
```
- [ ] **Step**：实现 `grade` 节点：读 `draft_report` + `messages`，用 `_call_llm` 取 JSON 评审，写 `grade_feedback`、`pass`。

### Task 2.2 回环边
- `add_conditional_edges("report", grade_decider, {"grade","END"})`（report 完必进 grade）
- `add_conditional_edges("grade", grade_reroute, {"report","END"})`
  - 若 `not pass` 且 `attempts < MAX_ATTEMPTS(=2)` → `"report"`（带 `grade_feedback` 重生成）
  - 否则 → `"END"`
- [ ] **Step**：`attempts` 自增，超限放行最后版本。

### Task 2.3 验证
- [ ] `tests/test_grader.py`：构造“有幻觉/缺关键槽位/合格”三种报告，断言 pass 与是否回环。
- [ ] 跑 excavator demo，观察一次不通过时二次生成。

---

## Day 3：可观测 Trace + Human-in-the-loop 闭环（产出：每条请求一条 trace + agent 能写整改任务）

### Task 3.1 Trace
`core/trace.py`：
```python
@dataclass
class TraceEvent:
    session_id: str; t: str; millis: int; tokens: int
    model: str; kind: str; error: str = ""; note: str = ""
```
- 在 `assistant_graph` 各节点入口/出口记录：`session_id`、节点名、耗时、`token`（从 LLM 响应 usage 取）、`model`、是否 `[FALLBACK]`、是否 `[检索失败]`。
- [ ] **Step**：`trace.py` 提供 `emit(event)` 结构体；在 `server.py` 或 graph 事件流里 `yield ("trace", json.dumps(...))`（可选，不改变现有 chunk 契约）。
- [ ] **验证**：一次请求后打印/落一条完整 trace，包含“哪步慢、是否降级、token 数”。

### Task 3.2 Human-in-the-loop 整改任务
- 在 `report` 之后加 `hitl` 节点：输出草案 + “需要我帮你在库里建个整改任务吗？”
- 用户确认 → `create_rectification_task`：
  - 写库：`INSERT INTO tb_rectification_task (title, location, category, deadline, status, owner_team) VALUES (...)`。
  - 异步通知：**消息队列**（RabbitMQ/Redis Stream）发布给对应施工团队。
  - **权限**：区分 普通用户/施工团队 角色（Java 侧鉴权透传 `role`）。
- [ ] **Step**：`core/hitl_node.py` 实现 `interrupt`/确认分支；新增 `tools/rectification_task.py`（写库 + 发 MQ）。
- [ ] **验证**：`tests/test_hitl.py` 确认写库 + MQ 发布 + 非授权角色被拒。

---

## Day 4：复盘（单独文档）

- 新建 `docs/superpowers/plans/2026-08-31-langgraph-agent-review.md`：
  - 迁移前后对比（行为不变、结构变化）。
  - LangGraph 关键概念掌握：`StateGraph` / `typed state` / `conditional_edge` / `checkpointer` / `interrupt`。
  - 面试 Q&A：`为什么不用 framework？为什么又用 LangGraph？` `checkpointer 的作用` `反思怎么避免死循环` `HITL 怎么实现`。
  - 更新简历表述（不夸大）。
  - 记录本次踩坑（提问句放行/降级/检索兜底 在 langgraph 里怎么保留）。
- [ ] 完成后回到主线：**Docker（按原计划）**。

---

## 自我评审记录
- 覆盖了 spec 的“迁移 + 三深度点 + 复盘”。
- 无占位符（每个任务给了文件、接口、验证或代码骨架）。
- 关键契约（SSE/降级/5轮/疑问放行/检索兜底/识图唯一）在 Global Constraints 中显式保留。

## 执行交接
计划保存至 `docs/superpowers/plans/2026-08-31-langgraph-agent-migration.md`。
执行方式建议：**Inline（本会话逐天推进，边学边做）**——因为这是学习型迁移，需要边讲概念边动手；若你要更快，也可用 **Subagent-Driven**（每个任务派子代理）。
