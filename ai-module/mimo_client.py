"""
MiMo 视觉客户端 — 自封装，无 LangChain 依赖。
OpenAI-compatible API 格式。
"""
import base64
import json
from io import BytesIO
from typing import Optional

import requests
from PIL import Image

from config import MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL, MAX_IMAGE_SIZE


class MiMoVisionClient:
    """MiMo 视觉模型客户端，支持图片识别 + 结构化 JSON 输出。"""

    def __init__(self):
        self.base_url = MIMO_BASE_URL.rstrip("/")
        self.api_key = MIMO_API_KEY
        self.model = MIMO_MODEL

    def analyze(self, image_path: str, prompt: str, temperature: float = 0.3) -> Optional[str]:
        """
        发送图片 + 文本提示词给 MiMo，返回模型回复文本。
        失败返回 None。
        """
        image_b64 = self._encode_image(image_path)
        if image_b64 is None:
            return None

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "temperature": temperature,
        }

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            print(f"[ERROR] API 请求失败: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"[ERROR] 响应体: {e.response.text[:500]}")
            return None

    def analyze_json(
        self, image_path: str, prompt: str, temperature: float = 0.3
    ) -> Optional[dict]:
        """
        识图并以 JSON 格式返回。自动清理 markdown 代码块包裹。
        """
        text = self.analyze(image_path, prompt, temperature)
        if text is None:
            return None
        return self._extract_json(text)

    def _encode_image(self, image_path: str) -> Optional[str]:
        """加载图片、缩放后转 base64。"""
        try:
            img = Image.open(image_path)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            # 缩放大图
            if img.width > MAX_IMAGE_SIZE[0] or img.height > MAX_IMAGE_SIZE[1]:
                img.thumbnail(MAX_IMAGE_SIZE, Image.LANCZOS)

            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception as e:
            print(f"[ERROR] 图片编码失败: {e}")
            return None

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """从模型回复中提取 JSON，兼容 markdown 代码块包裹。"""
        text = text.strip()
        # 处理 ```json ... ``` 包裹
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取第一个 { } 块
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
            print(f"[WARN] JSON 解析失败，原始回复:\n{text[:500]}")
            return None


# 单例
client = MiMoVisionClient()
