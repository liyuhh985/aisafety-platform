"""Base Agent — 工具调用循环 + SSE 流式输出。"""
import json
from typing import Generator, Optional

import requests


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
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._tool_map = {t.name: t for t in tools}

    # ====== 非流式执行 ======

    def run(self, user_message: str, max_rounds: int = 5,
            history: list[dict] = None) -> str:
        """执行 Agent，返回最终文本结果。可传入历史消息。"""
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        for _ in range(max_rounds):
            response = self._call_llm(messages)

            if response.get("content"):
                return response["content"].strip()

            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                return "Agent 未返回有效结果"

            messages.append({
                "role": "assistant", "content": None, "tool_calls": tool_calls,
            })
            for tc in tool_calls:
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
                   history: list[dict] = None) -> Generator[str, None, None]:
        """
        SSE 流式执行 Agent。
        先非流式处理 tool_calls，最后一段文本以流式输出。
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # 非流式处理 tool_calls
        for _ in range(max_rounds):
            response = self._call_llm(messages)

            # LLM 决定返回文本 → 用 stream 重跑最后一步
            if response.get("content"):
                # 去掉最后一条 user 消息（timeout 后不用重发），用流式重试
                last_user = messages.pop()  # 弹出 user message
                # 先用非流式结果返回（tool_calls 已经处理完了，直接流式最后一轮）
                yield from self._call_llm_stream(messages)
                return

            tool_calls = response.get("tool_calls", [])
            if not tool_calls:
                yield "Agent 未返回有效结果"
                return

            messages.append({
                "role": "assistant", "content": None, "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_args = json.loads(tc["function"]["arguments"])
                tool = self._tool_map.get(tool_name)
                result = tool.execute(**tool_args) if tool else f"未知工具: {tool_name}"
                messages.append({
                    "role": "tool", "tool_call_id": tc["id"], "content": result,
                })

        yield "Agent 超出最大轮次"

    def _call_llm(self, messages: list) -> dict:
        """非流式调用 LLM。"""
        payload = self._build_payload(messages, stream=False)
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload, timeout=90,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]
        except requests.RequestException as e:
            print(f"[ERROR] {self.name} LLM 调用失败: {e}")
            return {"content": f"调用失败: {e}"}

    def _call_llm_stream(self, messages: list) -> Generator[str, None, None]:
        """流式调用 LLM，逐 token yield。"""
        payload = self._build_payload(messages, stream=True)
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload, timeout=120, stream=True,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
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
        except requests.RequestException as e:
            print(f"[ERROR] {self.name} 流式调用失败: {e}")
            yield f"\n[流式中断: {e}]"

    def _build_payload(self, messages: list, stream: bool) -> dict:
        payload = {"model": self.model, "messages": messages, "temperature": 0.3}
        if stream:
            payload["stream"] = True
        if self.tools:
            payload["tools"] = [t.to_openai_spec() for t in self.tools]
            if not stream:
                payload["tool_choice"] = "auto"
        return payload
