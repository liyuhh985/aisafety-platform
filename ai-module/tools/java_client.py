"""Python -> Java：调用 POST /api/hazard/ai 建隐患（AI 上报闭环的写库入口）。

- 带 X-Internal-Token（与 Java 端 ai.internal-token 一致）。
- 异常/超时 -> 返回 {ok: False, message}，不抛到对话层。
"""
import logging
import requests
from config import JAVA_BASE_URL, AI_INTERNAL_TOKEN

LOGGER = logging.getLogger(__name__)


def create_hazard(payload: dict) -> dict:
    """POST /api/hazard/ai。返回 {ok, hazardId?, message?}。"""
    url = f"{JAVA_BASE_URL.rstrip('/')}/api/hazard/ai"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Token": AI_INTERNAL_TOKEN or "",
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("java create_hazard 请求失败: %s", e)
        return {"ok": False, "message": f"上报服务暂时不可用：{e}"}

    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "message": f"上报服务返回异常（HTTP {resp.status_code}）"}

    code = body.get("code")
    if resp.status_code == 200 and code == 200:
        data = body.get("data") or {}
        return {"ok": True, "hazardId": data.get("id"), "message": "已创建"}
    return {"ok": False,
            "message": body.get("message") or body.get("msg") or f"HTTP {resp.status_code}"}
