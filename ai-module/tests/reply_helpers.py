"""测试用：把 state 渲染成最终回复文本。

走的是与生产**同一份**分发逻辑（`assistant_graph._reply_destination`），
所以重构前后只要内容断言不变，就说明是纯重构。
"""
from langchain_core.messages import HumanMessage

from core import assistant_graph as ag

REPLY_NODES = ("boundary_reply", "smalltalk_reply", "answer_reply", "fallback_reply")


def render_update(state, config=None) -> dict:
    destination = ag._reply_destination(state)
    node = getattr(ag, destination)
    if destination == "fallback_reply":
        return node(state, config)
    return node(state)


def render_reply(state, config=None) -> str:
    return render_update(state, config)["messages"][-1].content


def collect_chunks(monkeypatch) -> list:
    """把 SSE chunk 收集器装到 get_stream_writer 上，返回那个列表。"""
    chunks = []
    monkeypatch.setattr(ag, "get_stream_writer", lambda: chunks.append)
    return chunks


def streamed_text(chunks) -> str:
    return "".join(str(c.get("chunk", "")) for c in chunks if isinstance(c, dict))


def fake_report_model(monkeypatch, reply: str) -> list:
    """把措辞模型换成固定输出（危险路径的应急指引也走它），返回调用记录。"""
    calls = []

    def fake_stream(messages, cancellation=None):
        calls.append(messages)
        yield ("chunk", reply)

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    return calls


def run_turn(app, config, text: str):
    """跑一轮真实图，返回 (节点序列, 用户可见文本, 终态)。

    刻意走图而不是直接调节点：把 emergency_guidance 从图上摘掉、或让它不输出，
    以它为前提的断言就必须变红。
    """
    nodes = []
    for mode, item in app.stream(
        {"session_id": "s", "messages": [HumanMessage(content=text)]},
        config, stream_mode=["updates", "custom"],
    ):
        if mode == "updates":
            nodes.extend(item.keys())
    values = app.get_state(config).values
    messages = values.get("messages") or []
    answer = getattr(messages[-1], "content", "") if messages else ""
    return nodes, answer, values
