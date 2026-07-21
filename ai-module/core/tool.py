"""Tool 定义 — Agent 可调用的工具。"""
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Tool:
    """一个工具 = 名称 + 描述 + JSON Schema 入参 + 执行函数"""
    name: str
    description: str
    parameters: dict  # JSON Schema properties
    func: Callable[..., Any]
    required: list = field(default_factory=list)

    def to_openai_spec(self) -> dict:
        """转为 OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required,
                },
            },
        }

    def execute(self, **kwargs) -> str:
        """执行工具，返回文本结果。"""
        try:
            result = self.func(**kwargs)
            return str(result) if not isinstance(result, str) else result
        except Exception as e:
            return f"[工具执行失败] {self.name}: {e}"
