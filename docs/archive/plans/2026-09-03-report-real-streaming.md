> 状态：superseded
> 最后核对：2026-10-09
> 替代文档：docs/current/ai-assistant-sse-contract.md
> 历史文档：当前版本请以 docs/current/ 和代码为准。

# 新版助手 report 真流式（custom stream mode）实施计划

> 日期：2026-09-03
> 背景：当前 `report` 等跑完一次性发整份 `draft_report`（非流式）。目标是改成**逐 token 真流式**，用 LangGraph 的 `get_stream_writer()` + `stream_mode=["updates","custom"]`。
> 前置验证：`get_stream_writer` 在本环境（Python 3.13, langgraph 1.2.11）可用，`stream_mode=["updates","custom"]` 同时产出 updates（节点级）和 custom（writer 写的内容）。

---

## 方案

用 `stream_mode=["updates","custom"]`：
- **updates**：照旧拿节点级更新（status、clarify 追问、route 进度）——**不动**。
- **custom**：新增，拿 `report` 里 `get_stream_writer()` 逐 token 写的 `{"chunk": token}`。

**关键**：`report` 若同时走 updates（整份）+ custom（逐 token）会重复。所以 **bridge 里忽略 `updates` 模式的 `report`**，只认 `custom` 的 chunk。

---

## 文件结构

| 文件 | 改动 |
|---|---|
| `core/assistant_graph.py` | `report` 加 `get_stream_writer`；`produce()` 改 `stream_mode=["updates","custom"]`；bridge 处理 custom chunk、跳过 updates 的 report |
| `tests/test_multi_hazard.py` | 新增 report 用 writer 流式输出的测试 |

---

### Task 1: `report` 节点用 `get_stream_writer` 逐 token 写

**Files:**
- Modify: `core/assistant_graph.py`（`report`）
- Test: `tests/test_multi_hazard.py`

**Interfaces:**
- Consumes: `_report_llm._call_llm_stream_events`（返回 `(kind, text)`）。
- Produces: `report` 用 writer 逐 token 发 `{"chunk": text}`；仍返回 `draft_report`。

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_multi_hazard.py 追加
def test_report_writes_custom_chunks(monkeypatch):
    # monkeypatch _report_llm 流式返回多个 chunk；模拟 get_stream_writer
    import core.assistant_graph as ag
    from langchain_core.messages import HumanMessage

    class FakeStream:
        def _call_llm_stream_events(self, msgs, cancellation=None):
            for t in ["## ", "占道", "被堵"]:
                yield ("chunk", t)

    sent = []
    # monkeypatch get_stream_writer 让 writer 记录
    monkeypatch.setattr("core.assistant_graph.get_stream_writer", lambda: (lambda d: sent.append(d)))
    ag._report_llm = FakeStream()

    st = {"messages": [HumanMessage(content="占道被堵")],
          "categories": ["占道"],
          "category_results": {"占道": {"regulation": "法", "case": "案例"}},
          "vision_summary": "", "category": "", "category_index": 0, "active_category": "占道"}
    up = ag.report(st)
    assert up["draft_report"] == "## 占道被堵"      # 仍返回整份 draft_report
    assert sent == [{"chunk": "## "}, {"chunk": "占道"}, {"chunk": "被堵"}]  # 且逐 token 写进 writer
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py::test_report_writes_custom_chunks -v`
Expected: FAIL（`get_stream_writer` 未导入/未调用，sent 为空）

- [ ] **Step 3: 实现 report**

```python
# core/assistant_graph.py —— 头部加
from langgraph.config import get_stream_writer

def report(state: AssistantState) -> dict:
    messages = list(state.get("messages", []))
    cats = state.get("categories") or []
    results = state.get("category_results") or {}
    vision = state.get("vision_summary") or ""
    lines = []
    for cat in cats:
        r = results.get(cat, {})
        reg = r.get("regulation") or "库内暂未检索到"
        case = r.get("case") or "库内暂未检索到"
        lines.append("[隐患类别] " + cat + "\n[视觉分析] " + vision + "\n[检索法规] " + reg + "\n[检索案例] " + case)
    ctx = (
        "\n\n".join(lines) +
        "\n请对每个隐患用一节输出：### 一、触犯法规 / ### 二、安全隐患 / ### 三、类似案例。" +
        "法规和案例必须来自上面检索结果，没有就写「库内暂未检索到」，不编造。" +
        "多隐患时每个隐患精炼、突出结论；法规引用完整准确。信息不足写「信息不足，未确认」。" +
        "最后加一句「需要我按这个情况生成一个整改建议吗？」"
    )
    dict_msgs = []
    _ROLE_MAP = {"system": "system", "human": "user", "ai": "assistant", "tool": "tool"}
    for m in messages:
        dict_msgs.append({"role": _ROLE_MAP.get(getattr(m, "type", "user"), "user"), "content": getattr(m, "content", "")})
    dict_msgs.append({"role": "user", "content": ctx})

    writer = get_stream_writer()          # 拿到 writer（contextvar，跨线程可靠）
    buf = []
    for kind, text in _report_llm._call_llm_stream_events(dict_msgs, cancellation=None):
        if kind == "chunk":
            buf.append(text)
            try:
                writer({"chunk": text})   # 逐 token 写进 custom 流
            except Exception:
                pass                       # 非 custom 模式下 writer 可能不可用，忽略
    return {"draft_report": "".join(buf)}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py::test_report_writes_custom_chunks -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/assistant_graph.py ai-module/tests/test_multi_hazard.py
git commit -m "feat(report): stream tokens via get_stream_writer (custom mode)"
```

---

### Task 2: `produce()` 用 `stream_mode=["updates","custom"]`，bridge 处理 custom chunk、跳过 updates 的 report

**Files:**
- Modify: `core/assistant_graph.py`（`run_stream_events` 里 `produce()` + bridge）
- Test: `tests/test_multi_hazard.py`（图级冒烟：custom chunk 能出来）

**Interfaces:**
- Consumes: `app.stream(initial, config, stream_mode=["updates","custom"])`。
- Produces: bridge 把 custom `{"chunk": text}` emit 成 SSE `chunk`；updates 里**跳过 report**（避免整份重复）。

- [ ] **Step 1: 写失败的测试（图级冒烟，custom chunk 能被 emit）**

```python
# tests/test_multi_hazard.py 追加
def test_bridge_custom_chunk_from_report(monkeypatch):
    import asyncio
    import core.assistant_graph as ag
    from langchain_core.messages import HumanMessage

    # monkeypatch _report_llm 流式返回 token
    class FakeStream:
        def _call_llm_stream_events(self, msgs, cancellation=None):
            for t in ["#", "报告"]:
                yield ("chunk", t)
    class FakeLLM:
        def _call_llm(self, m, cancellation=None): return {"content": "占道"}
        def _call_llm_stream_events(self, m, cancellation=None): yield ("chunk", "x")
        def _call_llm_stream(self, m, cancellation=None): yield "x"
    ag._report_llm = FakeStream()
    # 让 _infer_categories 直接返回占道（不走 LLM 分类）
    monkeypatch.setattr(ag, "_infer_categories", lambda t, v="": ["占道"])
    monkeypatch.setattr(ag, "_llm_extract_slots", lambda msg, cats, keys: {"占道": {"behavior":"占道"}})
    monkeypatch.setattr(ag, "_llm_phrase", lambda slots, ctx: "占道是完全堵死吗？")

    async def run():
        out = []
        async for kind, text in ag.run_stream_events(
            message="占道被堵死", history=[], slots={}, vision_summary="", session_id="t", max_rounds=3):
            out.append((kind, text))
        return out

    out = asyncio.run(run())
    # 应该收到来自 report 的 custom chunk
    assert any(k == "chunk" and "报告" in t for k, t in out)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py::test_bridge_custom_chunk_from_report -v`
Expected: FAIL（当前 bridge 只认 updates，收不到 custom chunk）

- [ ] **Step 3: 实现 produce() + bridge**

```python
# core/assistant_graph.py —— produce() 内部
def produce():
    _stream_local.emit = emit
    try:
        seen = set()
        for mode, item in app.stream(initial, config, stream_mode=["updates", "custom"]):
            if mode == "custom":
                # report 逐 token 写的 {"chunk": text}
                if isinstance(item, dict) and "chunk" in item:
                    emit("chunk", item["chunk"])
                continue
            # mode == "updates"（节点级更新）
            for node, update in item.items():
                if node not in seen:
                    seen.add(node)
                    emit("status", STATUS_TEXT.get(node, "处理中..."))
                if node in ("clarify", "meta_clarify"):
                    msgs = (update or {}).get("messages") or []
                    if msgs:
                        last = msgs[-1]
                        content = getattr(last, "content", None) or ""
                        if content:
                            emit("chunk", content)
                # 注意：不再从 updates 取 report 的 draft_report（避免和 custom 重复）
                # report 正文现在走 custom 流
            if cancellation:
                cancellation.throw_if_cancelled()
        emit("done", "")
    except Exception as e:
        emit("error", str(e))
    finally:
        try:
            del _stream_local.emit
        except Exception:
            pass
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd E:\java\newProject\ai-module; python -m pytest tests/test_multi_hazard.py::test_bridge_custom_chunk_from_report -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd E:\java\newProject
git add ai-module/core/assistant_graph.py ai-module/tests/test_multi_hazard.py
git commit -m "feat(bridge): consume custom stream for report real streaming"
```

---

## 自检清单

- [ ] report 逐 token 走 `stream_mode="custom"`，不再整份发（与 updates 的 draft_report 不重复）。
- [ ] updates 仍提供 status / clarify 追问。
- [ ] Java 端 SSE 依然收到 `data: {"type":"chunk","content":"..."}`（逐 token）。
- [ ] 断连取消（cancellation）仍有效。
- [ ] 全量测试通过（test_multi_hazard + test_adaptive_slots + 旧图冒烟）。

## 注意
- `stream_mode=["updates","custom"]` 的 `item` 迭代出的不是 `{node: update}`，而是 `(mode, item)` 元组。updates 时 `item={node: update}`；custom 时 `item=writer 写的东西`。
- `report` 不再从 `updates` 拿，避免重复；`_report_llm._call_llm_stream_events` 逐 token 由 writer 发出。