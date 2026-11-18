"""Python -> Java 内部查询：AI 建单对账使用。

- 带 X-Internal-Token（与 Java 端 ai.internal-token 一致）。
- 异常/超时 -> 返回 {found: False, error}，不抛到对账层。
"""
import logging
import requests
from config import JAVA_BASE_URL, AI_INTERNAL_TOKEN

LOGGER = logging.getLogger(__name__)


def hazard_create_result(request_id: str) -> dict:
    """GET /api/hazard/ai/requests/{requestId}：供 Python 超时对账使用。

    返回 {"found": bool, "hazardId": ...}；网络/服务异常返回 {"found": False, "error": ...}，
    调用方必须把 error 当成“暂时查不到”而不是“确认没建单”。
    """
    url = f"{JAVA_BASE_URL.rstrip('/')}/api/hazard/ai/requests/{request_id}"
    headers = {"X-Internal-Token": AI_INTERNAL_TOKEN or ""}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 404:
            return {"found": False}
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") or {}
        return {
            "found": bool(data.get("found")),
            "hazardId": data.get("hazardId"),
        }
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("java hazard_create_result 查询失败 request_id=%s: %s", request_id, e)
        return {"found": False, "error": str(e)}
