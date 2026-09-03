# 新版 AI 助手 —— B 篇：SSE bridge（run_stream_events）

> 日期：2026-09-03
> 本文档配合「新版链路引导」B 篇，讲清楚图跑出的 `status/chunk/done` 怎么逐条吐给前端（SSE），含 `get_stream_writer` 真流式、断连取消。
> 代码取自 `ai-module/core/assistant_graph.py`（**当前最新版本**）。

---

## 0. 一句话

`run_stream_events` 是一个 **async generator**：它把「图（LangGraph）跑出的每一步」用 **asyncio.Queue** 当中转，一帧一帧 `yield` 给 server，server 再转成 SSE 发给前端。

```
produce 线程（跑图）     asyncio.Queue        main 协程（生成器）        SSE → Java
    emit(...)  ──►  塞进队列  ──►   await q.get()  ──►  yield  ～～～  data: {...}
```

---

## 1. 整体结构

```python
async def run_stream_events(message, history, slots, vision_summary, session_id,
                            max_rounds=5, cancellation=None) -> Generator[tuple, None, None]:
    app = get_app()                            # 编译好的图
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()         # 传送带

    def emit(kind, text):
        loop.call_soon_threadsafe(q.put_nowait, (kind, text))   # 线程安全塞队列

    # ... 构造 messages + initial + config ...

    def produce():                             # 后台线程：跑图
        ...
    worker = asyncio.create_task(asyncio.to_thread(produce))   # 线程跑图
    try:
        while True:
            try:
                kind, text = await asyncio.wait_for(q.get(), timeout=0.1)
            except asyncio.TimeoutError:
                if cancellation and cancellation.is_cancelled():
                    break
                continue
            yield (kind, text)                 # 吐给 SSE
            if kind in ("error", "done"):
                break
    finally:
        if not worker.done():
            worker.cancel()
```

---

## 2. 为什么需要一个「队列」中转？

**核心原因：`produce`（跑图）在后台线程，而 `yield` 只能在主协程。**

- `app.stream(...)` 是**同步**的（会阻塞）→ 放**线程**里跑（`asyncio.to_thread`），不阻塞主循环。
- SSE 的 `yield` 是 **async** 的 → 必须在**主协程**。
- 线程不能直接 `yield`，所以它把事件**塞进 `q`**（`emit`→`q.put_nowait`），主协程从 `q` 取出来再 `yield`。

**`emit` 只负责塞队列，不直接返回前端；`main` 协程负责从队列拿再 yield。**

---

## 3. `emit` + `q`（传送带）

```python
def emit(kind, text):
    loop.call_soon_threadsafe(q.put_nowait, (kind, text))
```

- `q.put_nowait((kind, text))`：把 `(kind, text)` 塞进队列。
- `loop.call_soon_threadsafe`：让**主事件循环**执行这个塞队列操作（因为 `produce` 在线程里，不能直接操作 asyncio 队列，要线程安全）。

---

## 4. 构造 `messages` + `initial` + `config`

```python
hc_msgs = [SystemMessage(content=ASSISTANT_SYSTEM)]
for h in (history or [])[-max_rounds * 2:]:     # 最近 N 轮（每轮 user+assistant 两条）
    role = h.get("role")
    if role == "system":   hc_msgs.append(SystemMessage(content=h.get("content","")))
    elif role == "user":   hc_msgs.append(HumanMessage(content=h.get("content","")))
    elif role == "assistant": hc_msgs.append(AIMessage(content=h.get("content","")))
hc_msgs.append(HumanMessage(content=message))   # 当前消息

initial = {
    "session_id": session_id, "messages": hc_msgs,
    "categories": [], "active_category": "", "category_index": 0,
    "category_slots": {}, "category_results": {}, "missing": [],
    "relationship": "", "pending_categories": [],
    "clarify_count": 0, "clarify_stopped": False,
    "vision_summary": vision_summary, "attempts": 0,
}
config = {"configurable": {"thread_id": session_id}}
```

- **`initial`**：这一轮的起点 state（多字段会被 checkpointer 覆盖）。
- **`config`**：`thread_id = session_id` → 告诉 checkpointer 用哪个"抽屉"，实现跨轮状态延续。

---

## 5. `produce()` —— 跑图的线程（重点：stream_mode）

```python
def produce():
    _stream_local.emit = emit
    try:
        seen = set()
        for mode, item in app.stream(initial, config, stream_mode=["updates", "custom"]):
            if mode == "custom":
                # report 逐 token 写的 {"chunk": text} -> 作为 chunk 流出
                if isinstance(item, dict) and "chunk" in item:
                    emit("chunk", item["chunk"])
                continue
            # mode == "updates"：节点级更新
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
                # 注意：report 正文现在走 custom 流，这里不再从 updates 取（避免重复）
            if cancellation:
                cancellation.throw_if_cancelled()
        emit("done", "")
    except Exception as e:
        emit("error", str(e))
    finally:
        try: del _stream_local.emit
        except Exception: pass
```

### 关键：`stream_mode=["updates","custom"]`

- **`updates`**：**节点级更新** (sync)。每个节点跑完，给 `{node: update}`。用来看 status、clarify 追问。
- **`custom`**：**writer 写的内容**。节点里 `get_stream_writer()` 写的 `{"chunk": text}` 会作为一个单独 item 冒出来。用来看 report 逐 token。

**遍历结构**：`for mode, item in app.stream(...)` 迭代出 `(mode, item)` 元组。
- `mode == "updates"` 时，`item = {node: update}`。
- `mode == "custom"` 时，`item = writer 写的东西`（比如 `{"chunk": "token"}`）。

### 为什么这样能"真流式"？
- 以前 `stream_mode="updates"`：图跑完一个节点，才给那个节点的完整 update。所以 report 是"跑完才给整份"。
- 现在 `custom`：节点每 `writer(...)` 一下，就立刻给一个。所以 report 逐 token，**token 一产生就偷过来**。

---

## 6. `get_stream_writer`（为什么它解决跨线程问题）

`report` 节点想逐 token 发，得用一个「跨线程可靠」的通道。两个选择：

| 方式 | 特点 |
|---|---|
| `threading.local()`（旧 `_stream_local.emit`） | **只在同一条线程有效** → 节点换线程就空，不可靠 |
| `get_stream_writer()`（新） | **`contextvar` 传播**，`copy_context()` 复制上下文，**跨线程也能带**，可靠 |

LangGraph 用 `get_stream_writer()` 拿到的 writer 是**跟当前执行上下文绑定的**，节点即使换到线程池跑，`get_stream_writer()` 也能拿到那个 writer，把 token 写出去。

**注意**：`get_stream_writer` 需要 Python >= 3.11（咱们是 3.13，可用）。

---

## 7. main 生成器（取队列 → yield → SSE）

```python
worker = asyncio.create_task(asyncio.to_thread(produce))
try:
    while True:
        try:
            kind, text = await asyncio.wait_for(q.get(), timeout=0.1)
        except asyncio.TimeoutError:
            if cancellation and cancellation.is_cancelled():
                break
            continue
        yield (kind, text)          # 吐给 SSE
        if kind in ("error", "done"):
            break
finally:
    if not worker.done():
        worker.cancel()
```

- `wait_for(q.get(), timeout=0.1)`：最多等 0.1 秒取队列。超时检查用户是否断连（`cancellation.is_cancelled()`），断了 break；否则继续等。
- `yield (kind, text)`：吐给 SSE。
- 遇到 `error`/`done` 结束；`finally` 取消后台线程，避免泄漏。

---

## 8. 断连取消（CancellationToken）

`cancellation` 是 `CancellationToken`，用来感知「用户是否关页/断连」。

- **`produce` 里**：每轮 `cancellation.throw_if_cancelled()` → 若断了，抛异常中止跑图。
- **`main` 里**：`wait_for` 超时时检查 `cancellation.is_cancelled()` → 断了 break。

`server.py` 的 `assistant_stream` 里，用户断连时调 `cancel_token.cancel()`，于是 `run_stream_events` 就会通过 `cancellation` 停止。

> 这跟之前学的「超时/取消链路」「谁先报异常、幂等」呼应。

---

## 9. 完整事件流（以「追问」和「报告」为例）

### 追问（clarify）
```
produce 线程:                main 协程:
  app.stream -> {"route":..}  → emit("status","正在分析...") → yield("status",...) → SSE
      -> {"clarify":..}       → emit("status","正在补充信息...")→ yield("status",...) → SSE
                              → emit("chunk","消防通道被什么堵住？")→ yield("chunk",...) → SSE
      -> emit("done","")      → yield("done","") → SSE
```

### 报告（report，真流式）
```
produce 线程:                main 协程:
  custom: {"chunk":"##"}     → emit("chunk","##")  → yield("chunk","##") → SSE
  custom: {"chunk":"占道"}    → emit("chunk","占道") → yield("chunk","占道") → SSE
  custom: {"chunk":"被堵"}    → emit("chunk","被堵") → yield("chunk","被堵") → SSE
  ...
  emit("done","")             → yield("done","") → SSE
```

---

## 10. 小结（B 篇要点）

1. **队列中转**：`produce`(线程) ——`emit`──> `q` ——`yield`──> SSE。
2. **为什么**：`app.stream` 同步放线程，`yield` 异步放主协程，`q` 是桥梁。
3. **`stream_mode=["updates","custom"]`**：updates 拿节点级(status/追问)，custom 拿 writer 逐 token(report)。
4. **`get_stream_writer`**：contextvar，跨线程可靠，解决 `threading.local()` 的坑。
5. **断连取消**：`cancellation.throw_if_cancelled()`（produce） + `is_cancelled()`（main）。

---

## 11. 下一步（C 篇预告）
- B 篇讲的是「图→SSE」这一层。C 篇可以讲 **Java 端**怎么接 SSE（鉴权、工作线程、HTTP 调 Python），以及 **超时/降级**（pro 90s 切 2.5、视觉 60s、检索 10s、报告 120s 那套）。