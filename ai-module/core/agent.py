"""Base Agent — 工具调用循环 + SSE 流式输出。"""
import json
import time
from typing import Generator, Optional

import requests

from config import (
    MIMO_MODEL_BACKUP,
    FALLBACK_LLM_BASE_URL,
    FALLBACK_LLM_API_KEY,
    FALLBACK_LLM_MODEL,
    FALLBACK_LLM_EFFORT,
    TEXT_MODEL,
    SMALL_MODEL,
    LLM_RETRY_PER_ENDPOINT,
    LLM_RETRY_BACKOFF_SECONDS,
)
from .cancellation import CancellationToken, StreamCancelled


_SMALL_AGENT_NAMES = {
    "hazard_extract",
    "hazard_address_extract",
    "dialogue_planner",
    "rewrite_query",
}


def _is_transient(exc) -> bool:
    """只有瞬时错误才值得重试：400/401/403 这类重试多少次结果都一样。"""
    if isinstance(exc, requests.Timeout):
        return True
    if isinstance(exc, requests.HTTPError):
        code = exc.response.status_code if exc.response is not None else 0
        return code in (408, 409, 425, 429, 500, 502, 503, 504)
    return isinstance(exc, requests.RequestException)   # 连接被切 / ChunkedEncodingError


class Agent:
    """通用 Agent，拥有 system prompt + 工具集，自动处理 LLM ↔ Tool 循环。"""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        tools: list,
        base_url: str,
        api_key: str,
        model: str = "mimo-v2.5",
        tool_choice: str = "auto",
        slot: str = "",
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.tool_choice = tool_choice
        self.slot = slot or ("small" if name in _SMALL_AGENT_NAMES else "text")
        self._tool_map = {t.name: t for t in tools}

    # ====== 非流式执行 ======

    def run(self, user_message: str, max_rounds: int = 5,
            history: list[dict] = None,
            cancellation: CancellationToken = None) -> str:
        """执行 Agent，返回最终文本结果。可传入历史消息。"""
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        for _ in range(max_rounds):
            if cancellation:
                cancellation.throw_if_cancelled()
            yield ("status", "正在分析您的咨询...")
            response = self._call_llm(messages, cancellation=cancellation)

            if response.get("content"):
                return response["content"].strip()

            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                return "Agent 未返回有效结果"

            messages.append({
                "role": "assistant", "content": None, "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                if cancellation:
                    cancellation.throw_if_cancelled()
                tool_name = tc["function"]["name"]
                tool_args = json.loads(tc["function"]["arguments"])
                tool = self._tool_map.get(tool_name)
                result = tool.execute(**tool_args) if tool else f"未知工具: {tool_name}"
                messages.append({
                    "role": "tool", "tool_call_id": tc["id"], "content": result,
                })

        return "Agent 超出最大轮次"

    # ====== 流式执行 ======

    def run_stream(self, user_message: str, max_rounds: int = 5,
                   history: list[dict] = None,
                   cancellation: CancellationToken = None) -> Generator[str, None, None]:
        """兼容入口：只产出文本 token（丢弃 status）。"""
        for kind, text in self.run_stream_events(user_message, max_rounds=max_rounds,
                                                 history=history, cancellation=cancellation):
            if kind == "chunk":
                yield text

    def run_stream_events(self, user_message: str, max_rounds: int = 5,
                          history: list[dict] = None,
                          cancellation: CancellationToken = None) -> Generator[tuple, None, None]:
        """
        SSE 流式执行 Agent，产出 (kind, text) 事件。
        kind ∈ {status, chunk, done, error}
        - status: 工具执行的进度提示（供前端展示）
        - chunk:  最终文本逐 token
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        for _ in range(max_rounds):
            if cancellation:
                cancellation.throw_if_cancelled()
            yield ("status", "正在分析您的咨询...")
            response = self._call_llm(messages, cancellation=cancellation)

            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                # 澄清追问放行：含问号且还没检索过，直接回追问，不强制调工具
                _content = response.get("content") or ""
                if (("？" in _content or "?" in _content) and not any(m.get("role") == "tool" for m in messages)):
                    # 追问直接流式返回，不逼调工具
                    emitted_q = False
                    for k, txt in self._call_llm_stream_events(messages, cancellation=cancellation):
                        yield (k, txt); emitted_q = True
                    if not emitted_q:
                        yield ("chunk", _content)
                    return
                # 还没检索过就直接给文本（例如"我来帮你检索"的空话）→ 强制模型选工具再试一次
                if not any(m.get("role") == "tool" for m in messages):
                    yield ("status", "正在调用检索工具...")
                    response = self._call_llm(messages, cancellation=cancellation,
                                              required_tool=True)
                    tool_calls = response.get("tool_calls", [])
                if not tool_calls:
                    if response.get("content"):
                        content = response["content"]
                        # 若仍是"我来帮你检索"这类空话，说明模型一直不调工具，给个降级提示
                        emitted = False
                        for k, txt in self._call_llm_stream_events(messages, cancellation=cancellation):
                            yield (k, txt); emitted = True
                        if not emitted:
                            yield ("chunk", content)
                        return
                    yield ("error", "未能生成有效结论，请补充更多信息后重试")
                    return

            messages.append({
                "role": "assistant", "content": None, "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                if cancellation:
                    cancellation.throw_if_cancelled()
                tool_name = tc["function"]["name"]
                tool_args = json.loads(tc["function"]["arguments"])
                tool = self._tool_map.get(tool_name)
                if tool_name == "search_regulation":
                    yield ("status", "正在检索相关法规...")
                elif tool_name == "search_cases":
                    yield ("status", "正在检索相似案例...")
                elif tool_name:
                    yield ("status", f"正在调用 {tool_name}...")
                result = tool.execute(**tool_args) if tool else f"未知工具: {tool_name}"
                messages.append({
                    "role": "tool", "tool_call_id": tc["id"], "content": result,
                })

        yield ("error", "分析步骤较多，未能生成结论，请重试或换一种问法")

    def _call_llm_stream_events(self, messages: list,
                                cancellation: CancellationToken = None) -> Generator[tuple, None, None]:
        """流式调用 LLM，逐 token yield ('chunk', text)。

        降级取舍：只在「一个 token 都还没吐出去」时才重试/换端点 —— 已经吐出正文后
        重试会重复内容，宁可中断报错。只读 delta["content"]，所以推理模型的
        reasoning_content 不会被当成正文写进报告。
        """
        plan = self._attempt_plan()
        i = 0
        while i < len(plan):
            base, key, model, effort, attempt = plan[i]
            if attempt:
                time.sleep(LLM_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
            if cancellation:
                cancellation.throw_if_cancelled()
            payload = self._build_payload(messages, stream=True)
            payload["model"] = model
            if effort:
                payload["effort"] = effort
            emitted = False
            resp = None
            close = None
            try:
                resp = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload, timeout=120, stream=True,
                )
                close = resp.close
                if cancellation:
                    cancellation.register(close)
                    cancellation.throw_if_cancelled()
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if cancellation:
                        cancellation.throw_if_cancelled()
                    if line and line.startswith(b"data: "):
                        data = line[6:]
                        if data == b"[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                emitted = True
                                yield ("chunk", delta["content"])
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                return
            except StreamCancelled:
                raise
            except requests.RequestException as e:
                if cancellation and cancellation.is_cancelled():
                    raise StreamCancelled() from e
                j = i + 1
                if not _is_transient(e):
                    while j < len(plan) and (plan[j][0], plan[j][2]) == (base, model):
                        j += 1
                if emitted or j >= len(plan):
                    print(f"[ERROR] {self.name} 流式调用失败: {e}")
                    yield ("error", f"[流式中断: {e}]")
                    return
                nxt = plan[j]
                if (nxt[0], nxt[2]) != (base, model):
                    print(f"[FALLBACK] {model} -> {nxt[2]} err={e}")
                else:
                    print(f"[RETRY] {model} 第 {nxt[4] + 1}/{LLM_RETRY_PER_ENDPOINT} 次 err={e}")
                i = j
                continue
            finally:
                if cancellation and close:
                    cancellation.unregister(close)
                if resp is not None:
                    resp.close()

    def _llm_endpoints(self) -> list:
        """调用链：槽位主端点 -> 跨供应商降级（若已配置且不是同一端点）。"""
        conf = SMALL_MODEL if self.slot == "small" else TEXT_MODEL
        if conf.base_url and conf.api_key and conf.model:
            chain = [(conf.base_url.rstrip("/"), conf.api_key,
                      conf.model, conf.effort or None)]
        else:
            chain = [(self.base_url, self.api_key, self.model, None)]
            if MIMO_MODEL_BACKUP and MIMO_MODEL_BACKUP != self.model:
                chain.append((self.base_url, self.api_key, MIMO_MODEL_BACKUP, None))
        if FALLBACK_LLM_BASE_URL and FALLBACK_LLM_API_KEY and FALLBACK_LLM_MODEL:
            fallback = (FALLBACK_LLM_BASE_URL.rstrip("/"), FALLBACK_LLM_API_KEY,
                        FALLBACK_LLM_MODEL, FALLBACK_LLM_EFFORT or None)
            if (fallback[0], fallback[2]) != (chain[0][0], chain[0][2]):
                chain.append(fallback)
        return chain

    def _attempt_plan(self) -> list:
        """把「端点 x 每端点重试次数」摊平成一张顺序清单，便于单层循环控制。"""
        attempts = max(1, int(LLM_RETRY_PER_ENDPOINT))
        plan = []
        for base, key, model, effort in self._llm_endpoints():
            for attempt in range(attempts):
                plan.append((base, key, model, effort, attempt))
        return plan

    def _call_llm(self, messages: list,
                  cancellation: CancellationToken = None,
                  required_tool: bool = False) -> dict:
        """非流式调用 LLM：主端点重试 -> 备用模型 -> 跨供应商降级。"""
        plan = self._attempt_plan()
        last_err = None
        i = 0
        while i < len(plan):
            base, key, model, effort, attempt = plan[i]
            if attempt:
                time.sleep(LLM_RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
            if cancellation:
                cancellation.throw_if_cancelled()
            payload = self._build_payload(messages, stream=False, required_tool=required_tool)
            payload["model"] = model
            if effort:
                payload["effort"] = effort
            resp = None
            close = None
            try:
                resp = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload, timeout=90,
                )
                close = resp.close
                if cancellation:
                    cancellation.register(close)
                    cancellation.throw_if_cancelled()
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]
            except StreamCancelled:
                raise
            except requests.RequestException as e:
                last_err = e
                if cancellation and cancellation.is_cancelled():
                    raise StreamCancelled() from e
                j = i + 1
                if not _is_transient(e):
                    # 非瞬时：跳过本端点剩下的重试，直接看下一个端点
                    while j < len(plan) and (plan[j][0], plan[j][2]) == (base, model):
                        j += 1
                if j >= len(plan):
                    print(f"[ERROR] {self.name} LLM 调用失败（已穷尽 {len(plan)} 次尝试）: {e}")
                    return {"content": f"调用失败: {e}"}
                nxt = plan[j]
                if (nxt[0], nxt[2]) != (base, model):
                    print(f"[FALLBACK] {model} -> {nxt[2]} err={e}")
                else:
                    print(f"[RETRY] {model} 第 {nxt[4] + 1}/{LLM_RETRY_PER_ENDPOINT} 次 err={e}")
                i = j
                continue
            finally:
                if cancellation and close:
                    cancellation.unregister(close)
                if resp is not None:
                    resp.close()
        return {"content": f"调用失败: {last_err}"}

    def _call_llm_stream(self, messages: list,
                         cancellation: CancellationToken = None) -> Generator[str, None, None]:
        """流式调用 LLM，逐 token yield。"""
        payload = self._build_payload(messages, stream=True)
        if cancellation:
            cancellation.throw_if_cancelled()
        resp = None
        close = None
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload, timeout=120, stream=True,
            )
            close = resp.close
            if cancellation:
                cancellation.register(close)
                cancellation.throw_if_cancelled()
            resp.raise_for_status()
            for line in resp.iter_lines():
                if cancellation:
                    cancellation.throw_if_cancelled()
                if line and line.startswith(b"data: "):
                    data = line[6:]
                    if data == b"[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except StreamCancelled:
            raise
        except requests.RequestException as e:
            if cancellation and cancellation.is_cancelled():
                raise StreamCancelled() from e
            print(f"[ERROR] {self.name} 流式调用失败: {e}")
            yield f"\n[流式中断: {e}]"

        finally:
            if cancellation and close:
                cancellation.unregister(close)
            if resp is not None:
                resp.close()

    def _build_payload(self, messages: list, stream: bool,
                        required_tool: bool = False) -> dict:
        payload_messages = list(messages or [])
        has_same_system = any(
            isinstance(message, dict)
            and message.get("role") == "system"
            and message.get("content") == self.system_prompt
            for message in payload_messages
        )
        if self.system_prompt and not has_same_system:
            payload_messages = (
                [{"role": "system", "content": self.system_prompt}]
                + payload_messages
            )
        payload = {"model": self.model, "messages": payload_messages, "temperature": 0.3}
        if stream:
            payload["stream"] = True
        if self.tools:
            payload["tools"] = [t.to_openai_spec() for t in self.tools]
            payload["tool_choice"] = "required" if required_tool else self.tool_choice
        return payload




