# Day24 下午 - 最小 Agent 循环 demo (15行核心，对照 core/agent.py)
from core.cancellation import CancellationToken, StreamCancelled
import time, sys
sys.stdout.reconfigure(encoding="utf-8")

def search_tool(keyword: str) -> str:
    return f"[搜到案例: {keyword} 关联事故 3起]"

TOOL_MAP = {"search": search_tool}

def mock_llm(messages):
    has_tool_result = any(m.get("role") == "tool" for m in messages)
    if has_tool_result:
        return {"content": "根据检索，存在高空作业未系安全带隐患，建议立即整改。"}
    return {"tool_calls": [{"id": "1", "function": {"name": "search", "arguments": "{\"keyword\": \"高空作业\"}"}}]}

def minimal_agent_run_stream(user_msg: str, cancellation: CancellationToken = None):
    messages = [{"role": "user", "content": user_msg}]
    for _ in range(3):
        if cancellation:
            cancellation.throw_if_cancelled()
        resp = mock_llm(messages)
        if resp.get("content"):
            for token in resp["content"].split():
                if cancellation:
                    cancellation.throw_if_cancelled()
                yield token + " "
                time.sleep(0.15)
            return
        for tc in resp.get("tool_calls", []):
            if cancellation:
                cancellation.throw_if_cancelled()
            name = tc["function"]["name"]
            result = TOOL_MAP[name](keyword="高空作业")
            messages.append({"role": "assistant", "tool_calls": [tc]})
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

print("=== 正常流式 ===")
tok = CancellationToken()
for chunk in minimal_agent_run_stream("分析高空作业隐患", cancellation=tok):
    print(chunk, end="", flush=True)
print("\n")

print("=== 中途取消演示 ===")
tok2 = CancellationToken()
gen = minimal_agent_run_stream("分析高空作业隐患", cancellation=tok2)
try:
    for i, chunk in enumerate(gen):
        print(chunk, end="", flush=True)
        if i == 2:
            print("\n[用户取消！调用 token.cancel()]")
            tok2.cancel()
    print("\nDone")
except StreamCancelled:
    print("\n[捕获 StreamCancelled，流式中断] Done")
