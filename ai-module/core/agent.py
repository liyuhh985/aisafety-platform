"""Base Agent — 工具调用循环 + SSE 流式输出。"""
import json
from typing import Generator, Optional

import requests

from config import MIMO_MODEL_BACKUP
from .cancellation import CancellationToken, StreamCancelled


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
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.tool_choice = tool_choice
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
        """流式调用 LLM，逐 token yield ('chunk', text)。"""
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
                            yield ("chunk", delta["content"])
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except StreamCancelled:
            raise
        except requests.RequestException as e:
            if cancellation and cancellation.is_cancelled():
                raise StreamCancelled() from e
            print(f"[ERROR] {self.name} 流式调用失败: {e}")
            yield ("error", f"[流式中断: {e}]")
        finally:
            if cancellation and close:
                cancellation.unregister(close)
            if resp is not None:
                resp.close()

    def _call_llm(self, messages: list,
                  cancellation: CancellationToken = None,
                  required_tool: bool = False) -> dict:
        """非流式调用 LLM，带主备降级（主 mimo-v2.5-pro -> 备 mimo-v2.5）。"""
        models = [self.model]
        try:
            from config import MIMO_MODEL_BACKUP
            if MIMO_MODEL_BACKUP and MIMO_MODEL_BACKUP != self.model:
                models.append(MIMO_MODEL_BACKUP)
        except Exception:
            pass
        last_exc = None
        for idx, model in enumerate(models):
            payload = self._build_payload(messages, stream=False, required_tool=required_tool)
            payload["model"] = model
            if cancellation:
                cancellation.throw_if_cancelled()
            resp = None
            close = None
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload, timeout=90,
                )
                close = resp.close
                if cancellation:
                    cancellation.register(close)
                    cancellation.throw_if_cancelled()
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]
            except requests.Timeout as e:
                last_exc = e
                if idx == 0 and len(models) > 1:
                    print(f"[FALLBACK] {model} 超时 -> {models[1]}")
                    continue
                if cancellation and cancellation.is_cancelled():
                    raise StreamCancelled() from e
                print(f"[ERROR] {self.name} LLM 调用失败: {e}")
                return {"content": f"调用失败: {e}"}
            except requests.HTTPError as e:
                last_exc = e
                code = e.response.status_code if e.response is not None else 0
                if code in (429, 500, 502, 503, 504) and idx == 0 and len(models) > 1:
                    print(f"[FALLBACK] {model} -> {models[1]} code={code}")
                    continue
                if cancellation and cancellation.is_cancelled():
                    raise StreamCancelled() from e
                print(f"[ERROR] {self.name} LLM 调用失败: {e}")
                return {"content": f"调用失败: {e}"}
            except requests.RequestException as e:
                last_exc = e
                if idx == 0 and len(models) > 1:
                    print(f"[FALLBACK] {model} -> {models[1]} err={e}")
                    continue
                if cancellation and cancellation.is_cancelled():
                    raise StreamCancelled() from e
                print(f"[ERROR] {self.name} LLM 调用失败: {e}")
                return {"content": f"调用失败: {e}"}
            except StreamCancelled:
                raise
            finally:
                if cancellation and close:
                    cancellation.unregister(close)
                if resp is not None:
                    resp.close()
        return {"content": f"调用失败: {last_exc}"}


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




