"""
视觉模型客户端 — 自封装，无 LangChain 依赖。
OpenAI-compatible API 格式，支持多供应商切换。

供应商优先级（由 VISION_PROVIDER 指定）：
  opendesign  OpenDesign Go  DeepSeek V4.1 Flash（默认）
  mimo        MiMo           mimo-v2.6-flash

结果缓存（VISION_CACHE=1，默认开启）：
  同一张图 + 同一提示词 + 同一模型 → 只请求一次，之后读磁盘缓存。
  OpenDesign 按请求次数计费，缓存能让重跑成本归零，且不影响结果正确性。
  需要强制重算时设 VISION_CACHE=0 或删掉 .cache 目录。
"""
import base64
import hashlib
import json
import os
from io import BytesIO
from typing import Optional

import requests
from PIL import Image

from config import (
    MAX_IMAGE_SIZE,
    VISION_PROVIDER,
    VISION_CACHE, VISION_CACHE_DIR,
    VISION_MODEL,
    OPENDESIGN_BASE_URL, OPENDESIGN_API_KEY, OPENDESIGN_VISION_MODEL,
    MIMO_BASE_URL, MIMO_API_KEY, MIMO_VISION_MODEL,
)

# 供应商注册表
_PROVIDERS = {
    "opendesign": {
        "base_url": OPENDESIGN_BASE_URL,
        "api_key": OPENDESIGN_API_KEY,
        "model": OPENDESIGN_VISION_MODEL,
    },
    "mimo": {
        "base_url": MIMO_BASE_URL,
        "api_key": MIMO_API_KEY,
        "model": MIMO_VISION_MODEL,
    },
    # 统一槽位：视觉配置来自 LLM_VISION_*（默认 DeepSeek）
    "deepseek": {
        "base_url": VISION_MODEL.base_url,
        "api_key": VISION_MODEL.api_key,
        "model": VISION_MODEL.model,
        "max_tokens": VISION_MODEL.max_tokens,
    },
}


# ---------------------------------------------------------------- 缓存
def _file_sha1(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _cache_file(img_sha: str, prompt: str, model: str) -> str:
    pk = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:16]
    mk = hashlib.sha1(model.encode("utf-8")).hexdigest()[:8]
    d = os.path.join(VISION_CACHE_DIR, mk)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{img_sha}_{pk}.json")


def cache_stats() -> tuple:
    n = size = 0
    if os.path.isdir(VISION_CACHE_DIR):
        for root, _, files in os.walk(VISION_CACHE_DIR):
            for f in files:
                if f.endswith(".json"):
                    n += 1
                    size += os.path.getsize(os.path.join(root, f))
    return n, size


class VisionClient:
    """视觉模型客户端，支持图片识别 + 结构化 JSON 输出。"""

    def __init__(self, provider: str = None):
        name = (provider or VISION_PROVIDER or "deepseek").strip().lower()
        if name not in _PROVIDERS:
            raise ValueError(f"未知的视觉供应商: {name}；可选 {list(_PROVIDERS)}")
        conf = _PROVIDERS[name]
        self.provider = name
        self.base_url = (conf["base_url"] or "").rstrip("/")
        self.api_key = conf["api_key"]
        self.model = conf["model"]
        self.max_tokens = conf.get("max_tokens")
        if not self.api_key:
            raise ValueError(f"供应商 {name} 缺少 API Key，请检查 .env")
        if not self.base_url:
            raise ValueError(f"供应商 {name} 缺少 base_url，请检查 .env")

    def analyze(self, image_path: str, prompt: str, temperature: float = 0.3) -> Optional[str]:
        """发送图片 + 提示词，返回模型回复文本。失败返回 None。

        开启缓存时，同一 (图片内容, 提示词, 模型) 只真正请求一次。
        """
        # ---- 查缓存 ----
        img_sha = None
        cf = None
        if VISION_CACHE:
            try:
                img_sha = _file_sha1(image_path)
                cf = _cache_file(img_sha, prompt, self.model)
                if os.path.isfile(cf):
                    try:
                        cached = json.load(open(cf, encoding="utf-8"))
                        return cached.get("content")
                    except Exception:
                        pass
            except Exception:
                cf = None

        image_b64 = self._encode_image(image_path)
        if image_b64 is None:
            return None

        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            }],
            "temperature": temperature,
        }
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # ---- 写缓存 ----
            if cf:
                try:
                    json.dump({"content": content, "model": self.model,
                               "usage": data.get("usage")},
                              open(cf, "w", encoding="utf-8"),
                              ensure_ascii=False)
                except Exception:
                    pass
            return content
        except requests.HTTPError as e:
            body = e.response.text[:500] if e.response is not None else ""
            print(f"[ERROR] API 请求失败: {e}")
            print(f"[ERROR] 响应体: {body}")
            # 余额/鉴权错误向上抛，调用方需中止而非吞掉
            if e.response is not None and e.response.status_code in (401, 402, 403):
                raise
            return None
        except requests.RequestException as e:
            print(f"[ERROR] API 请求失败: {e}")
            return None

    def analyze_json(self, image_path: str, prompt: str,
                     temperature: float = 0.3) -> Optional[dict]:
        """识图并以 JSON 格式返回。自动清理 markdown 代码块包裹。"""
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
        """从模型回复中提取 JSON，兼容 markdown 代码块包裹与含未转义引号的情况。"""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3].strip()

        # 优先剥掉 markdown 后再整体解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            print(f"[WARN] JSON 解析失败，原始回复:\n{text[:500]}")
            return None

        block = text[start:end + 1]
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            pass

        # 修复字符串值内的裸双引号
        try:
            from json_repair import repair_json
            fixed = repair_json(block)
            if fixed is not None:
                return fixed
        except Exception:
            pass

        print(f"[WARN] JSON 解析失败，原始回复:\n{text[:500]}")
        return None


# 兼容旧名字（项目内多处 import 的是 MiMoVisionClient）
MiMoVisionClient = VisionClient

# 单例（延迟创建，避免导入时因缺 key 直接崩）
_client = None


def get_client(provider: str = None) -> VisionClient:
    global _client
    if _client is None or provider:
        _client = VisionClient(provider)
    return _client


class _LazyClient:
    """模块级 client，首次使用时才真正初始化"""

    def __getattr__(self, name):
        return getattr(get_client(), name)


client = _LazyClient()
