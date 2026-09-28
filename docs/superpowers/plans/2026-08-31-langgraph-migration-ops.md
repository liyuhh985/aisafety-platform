# Day1 迁移操作手册：手写 ReAct → LangGraph

> 配套计划：`2026-08-31-langgraph-agent-migration.md`。本手册是 Day1 的**逐步执行脚本**，做完后新版助手行为必须与旧版一致（SSE 契约、多轮澄清、降级、检索兜底、识图唯一、疑问句放行）。

**前提确认**：`core/agent.py` 的 `Agent._call_llm`（带降级）、`Agent._build_payload`、`tools/assistant_tools.py` 的 `ASSISTANT_TOOLS`、`core/assistant_agent.py` 的 `ASSISTANT_SYSTEM`、`server.py::assistant_stream` 均保持可复用。

---

## 0. 依赖 + 留底 + 环境

```bash
# 安装
cd E:\java\newProject\ai-module
pip install "langgraph>=0.2" "langchain-core>=0.3"

# 留底（保留手写版做差异化对照）
mkdir legacy
copy core\agent.py legacy\agent.py
copy core\assistant_agent.py legacy\assistant_agent.py
```

`requirements.txt` 追加：
```
langgraph>=0.2
langchain-core>=0.3
```

---

## 1. 状态定义（新建 `core/langgraph_state.py`）

```python
from typing import TypedDict, Optional

class AssistantState(TypedDict, total=False):
    session_id: str                     # checkpointer 的 thread_id
    messages: list                      # langchain_core 消息列表（system/human/ai/tool）
    slots: dict[str, str]               # {"behavior","persistence","blocked"} 填槽
    vision_summary: str                 # [视觉分析] 注入的识图结果
    regulation_results: str             # search_regulation 结果
    case_results: str                   # search_cases 结果
    draft_report: str                   # report 产出（三段式）
    grade_feedback: str                 # Day2 评审意见（占位）
    attempts: int                       # 反思重试计数（Day2 用）
```

---

## 2. 构建图（新建 `core/assistant_graph.py`）

复用 `Agent` 的 LLM 调用能力；`route` 用**确定性填槽判断**（不额外调 LLM），`clarify`/`report` 调 LLM。

```python
import json
from typing import Generator
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from core.assistant_agent import ASSISTANT_SYSTEM
from core.agent import Agent
from core.langgraph_state import AssistantState
from tools.assistant_tools import ASSISTANT_TOOLS
from config import MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL

_llm = Agent(
    name="assistant",
    system_prompt="",               # system 由 graph 起始消息注入
    tools=ASSISTANT_TOOLS,
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
)

TOOL_MAP = {t.name: t for t in ASSISTANT_TOOLS}

# key slots
SLOT_KEYS = ("behavior", "persistence", "blocked")

def _missing_slots(slots: dict) -> list:
    return [k for k in SLOT_KEYS if not (slots.get(k) or "").strip()]


# ---------- 节点：route（确定性）----------
def route(state: AssistantState) -> dict:
    slots = state.get("slots", {})
    vision = state.get("vision_summary", "")
    # 有图且还没注入视觉结果 → 先看图（图片链路已在 server 注入，这里兜底）
    # 关键槽位缺失 → 去 clarify；齐全 → search
    if _missing_slots(slots):
        return {"route_decision": "clarify"}
    return {"route_decision": "search"}


def route_decider(state: AssistantState) -> str:
    return state.get("route_decision", "clarify")


# ---------- 节点：clarify（一次只问一个缺失槽位）----------
def clarify(state: AssistantState) -> dict:
    messages = state.get("messages", [])
    resp = _llm._call_llm(messages, cancellation=None)   # 复用 Agent LLM（含降级）
    text = (resp.get("content") or "").strip()
    updated = {"messages": messages + [AIMessage(content=text)]}
    return updated


# ---------- 节点：search（调法规+案例，各一次，超时/失败不重试）----------
def search(state: AssistantState) -> dict:
    messages = state.get("messages", [])
    slots = state.get("slots", {})
    keyword = _pick_keyword(slots)           # 从 slots/描述里取 2-8 字关键词
    reg = _run_tool("search_regulation", keyword)
    case = _run_tool("search_cases", keyword)
    return {
        "regulation_results": reg,
        "case_results": case,
        "messages": messages,   # 工具结果由 report 组装，不塞回 messages（避免长上下文）
    }


def _pick_keyword(slots: dict) -> str:
    # 简化：用行为槽位或整句；真实现按旧逻辑取 2-8 字
    return (slots.get("behavior") or "占道")[:8]


def _run_tool(name: str, keyword: str) -> str:
    tool = TOOL_MAP.get(name)
    if not tool:
        return "[检索失败] 未知工具"
    try:
        return str(tool.execute(keyword=keyword))
    except Exception as e:
        return f"[检索失败] {e}"


# ---------- 节点：report（生成三段式，流式在 bridge 里取 token）----------
def report(state: AssistantState) -> dict:
    messages = state.get("messages", [])
    reg = state.get("regulation_results", "[库内暂未检索到]")
    case = state.get("case_results", "[库内暂未检索到]")
    vision = state.get("vision_summary", "")
    # 把检索结果作为 system/上下文注入，生成三段式
    ctx = build_report_context(vision, reg, case)
    final_messages = _llm._build_payload(
        messages + [SystemMessage(content=ctx)], stream=False
    )["messages"]   # 复用 payload 构造，实际由 _call_llm 处理
    resp = _llm._call_llm(final_messages, cancellation=None)
    draft = (resp.get("content") or "").strip()
    return {"draft_report": draft, "messages": messages}


def build_report_context(vision: str, reg: str, case: str) -> str:
    parts = [f"[视觉分析] {vision or '无'}"]
    parts.append(f"[检索法规] {reg}")
    parts.append(f"[检索案例] {case}")
    return "\n".join(parts)


# ---------- 图构建 ----------
def build_graph():
    g = StateGraph(AssistantState)
    g.add_node("route", route)
    g.add_node("clarify", clarify)
    g.add_node("search", search)
    g.add_node("report", report)
    g.set_entry_point("route")
    g.add_conditional_edges("route", route_decider, {"clarify": "clarify", "search": "search"})
    g.add_conditional_edges("clarify", lambda s: "report" if not _missing_slots(s.get("slots", {})) else "route" if _rounds_ok(s) else "report", {"report": "report", "route": "route"})
    g.add_conditional_edges("search", lambda s: "report", {"report": "report"})
    g.add_edge("report", END)
    return g.compile(checkpointer=InMemorySaver())


def _rounds_ok(state) -> bool:
    return True   # Day2 引入 attempts 计数；先放开
```

> 说明：`clarify` 后的条件边是“填完槽→report；没填完且还有轮次→route 再问；轮次耗尽→report”。Day2 再精化。

---

## 3. SSE bridge（给 `server.py` 用）

在 `core/assistant_graph.py` 加一个产出 `(kind, text)` 的生成器：

```python
def run_stream_events(message: str, history: list[dict], slots: dict,
                      vision_summary: str, session_id: str,
                      max_rounds: int = 5) -> Generator[tuple, None, None]:
    app = build_graph()
    hc_msgs = [SystemMessage(content=ASSISTANT_SYSTEM)]
    for h in history[-max_rounds * 2:]:
        role = h.get("role")
        if role == "user":
            hc_msgs.append(HumanMessage(content=h.get("content", "")))
        elif role == "assistant":
            hc_msgs.append(AIMessage(content=h.get("content", "")))
    hc_msgs.append(HumanMessage(content=message))

    initial = {
        "session_id": session_id,
        "messages": hc_msgs,
        "slots": slots,
        "vision_summary": vision_summary,
        "attempts": 0,
    }
    config = {"configurable": {"thread_id": session_id}}

    seen_nodes = set()
    try:
        for node, update in app.stream(initial, config, stream_mode="updates"):
            if node not in seen_nodes:
                seen_nodes.add(node)
                yield ("status", STATUS_TEXT.get(node, "处理中..."))
            # 若 report 产出 draft_report，流式回传已由 messages 模式处理；此处不再重复
    except Exception as e:
        yield ("error", str(e))
        return
    # 取最终 draft_report 做流式：改用 stream_mode="messages" 逐 token
    text = ""
    for chunk, meta in app.stream(initial, config, stream_mode="messages"):
        if meta.get("langgraph_node") == "report" and getattr(chunk, "content", ""):
            text += chunk.content
            yield ("chunk", chunk.content)
    yield ("done", "")


STATUS_TEXT = {
    "route": "正在分析您的咨询...",
    "clarify": "正在补充信息...",
    "search": "正在检索法规与案例...",
    "report": "正在生成结论...",
}
```

> 说明：`stream_mode="updates"` 拿节点状态/进度，`stream_mode="messages"` 拿 report 的逐 token。实际执行时若版本不支持双 mode，退化为 `updates` + 用 `report` 节点内部 `_call_llm_stream_events` 返回文字。

---

## 4. 改 `server.py::assistant_stream`

把两处 `for kind, text in assistant.run_stream_events(...)`（99、237 行左右）替换为：

```python
from core.assistant_graph import run_stream_events as assistant_graph_stream

for kind, text in assistant_graph_stream(
    message=message,
    history=history,
    slots={},                      # 旧版从多轮里手工提取；Day1 先给空，后续从 state 回填
    vision_summary=vision_summary, # server 里先识图得到的结果
    session_id=sid,
    max_rounds=5,
):
    if await request.is_disconnected():
        print("[Assistant] 客户端断开，停止")
        break
    yield f"data: {json.dumps({'type': kind, 'content': text}, ensure_ascii=False)}\n\n"
    sent_any = True
    if kind in ("chunk", "error"):
        reply_parts.append(text)
```

---

## 5. 验证

```bash
cd E:\java\newProject\ai-module
python -m pytest tests/test_assistant_tools.py -q
python -m pytest tests/test_orchestrator_stream.py -q
python -c "from core.assistant_graph import build_graph; g=build_graph(); print('graph ok')"
```

手动 demo（图片链路）：
```bash
# 启动
python server.py
# 用挖机图 POST /api/ai/assistant/stream (multipart: message+file+session_id)
# 预期：识图→(追问 长期/堵死)→检索法规案例→三段式，与旧版一致
```

---

## 6. 本手册落地检查表
- [ ] `requirements.txt` 加了 langgraph/langchain-core，`pip install` 成功
- [ ] `legacy/` 存了 `agent.py`、`assistant_agent.py`
- [ ] `core/langgraph_state.py` 建好
- [ ] `core/assistant_graph.py` build_graph 可运行
- [ ] `server.py` 两处改为调用 graph
- [ ] 多轮追问 / 疑问句放行 / 检索兜底 / 识图唯一都能跑通
- [ ] SSE 前端看到 status/chunk/done，无 error
