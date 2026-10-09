"""AI 上报闭环：从对话抽取隐患信息 -> 高德地理编码 -> 调 Java 建库。

- _extract：用 LLM 从（历史 + 最新消息）抽 category/address/district/description/severity。
- submit_from_history：geocode 补坐标（失败降级），再调 java_client.create_hazard。
"""
import json
import logging
import re

from core.agent import Agent
from core.hazard_categories import SUBMIT_CATEGORIES
from core.hazard_taxonomy import (
    HAZARD_TAXONOMY,
    SUBCATEGORY_LABELS,
    format_hazard_type,
    normalize_taxonomy,
)
from config import MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL
from tools.amap_geo import geocode
from tools.java_client import create_hazard

LOGGER = logging.getLogger(__name__)

CATEGORIES = SUBMIT_CATEGORIES

# 轻量抽取器（不带工具）
_extractor = Agent(
    name="hazard_extract",
    system_prompt="你是隐患上报信息抽取器，只按用户对话提取结构化字段，不编造。",
    tools=[],
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
)




_ADDR_RE = re.compile(
    r"[一-龥]{2,}(?:省|市|自治区)[一-龥]{0,18}?"
    r"(?:区|县|市|路|街|大道|镇|乡|社区|小区|村|号|栋|门|广场)"
    r"[一-龥0-9]{0,18}"
)


def _regex_address(text: str) -> str:
    """从文本里粗提取最像地址的片段（省/市...区/路/小区...）。"""
    if not text:
        return ""
    m = _ADDR_RE.search(text)
    if m:
        return m.group(0).strip()
    return ""


def _as_text(value) -> str:
    """把抽取模型/地理编码返回的字段收敛成 Java 契约要求的 str。

    动机：上游字段类型不稳定（实测 district 返回空数组 []），而 Java 侧
    category/address/district/description/report/imageUrl 都是 String；
    类型必须在契约边界收口，不能靠上游自觉。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [_as_text(item) for item in value]
        return "、".join(part for part in parts if part)
    return str(value)


def _as_severity(value) -> int:
    """severity 安全解析：取文本里的第一个数字，缺省 1，夹到 0..2。

    抽取模型可能给出 "严重"/["2"] 等非数字，直接 int() 会抛异常并被外层
    except 吞掉，退化成空 payload -> 用户看到"未能识别隐患类别"。
    """
    match = re.search(r"\d+", _as_text(value))
    if not match:
        return 1
    return max(0, min(2, int(match.group(0))))


def _render(history, latest) -> str:
    parts = []
    for h in (history or [])[-10:]:
        parts.append(f"[{h.get('role', 'user')}] {h.get('content', '')}")
    parts.append(f"[user] {latest}")
    return "\n".join(parts)


def _extract(history, latest) -> dict:
    prompt = (
        "请从下面对话中抽取隐患上报信息，只返回 JSON，字段："
        "category(必须使用 major_code/subcategory_code 格式)，"
        "address(最具体的地点文本，如'XX市XX区XX路XX小区门口'，没有为空)，"
        "district(省/市/区，没有为空)，description(隐患描述，简短)，severity(0一般/1较重/2严重，默认1)。\n"
        "允许的类别：\n"
        + "\n".join(
            f"- {item['label']}({item['code']}): "
            + "、".join(f"{label}({code})" for code, label in item["subcategories"])
            for item in HAZARD_TAXONOMY
        )
        + "\n"
        f"对话：\n{_render(history, latest)}"
    )
    try:
        resp = _extractor._call_llm([{"role": "user", "content": prompt}], cancellation=None)
        content = (resp.get("content") or "").strip()
        if "```" in content:
            content = content.split("```")[1] if content.find("```") < content.rfind("```") else content
            if content.startswith("json"):
                content = content[4:]
        s, e = content.find("{"), content.rfind("}")
        if s != -1 and e != -1:
            data = json.loads(content[s:e + 1])
        else:
            data = json.loads(content)
        # category 归一化到 canonical major/subcategory 编码
        cat = (data.get("category") or "").strip()
        pair = normalize_taxonomy(cat)
        if pair:
            data["category"] = format_hazard_type(pair[0], pair[1])
        else:
            data["category"] = ""
        data["severity"] = _as_severity(data.get("severity"))
        if not data.get("address"):
            data["address"] = _regex_address(_render(history, latest))
        return data
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("hazard extract failed: %s", e)
        return {"category": "", "address": "", "district": "",
                "description": "", "severity": 1}


def submit_from_history(user_id, history, latest) -> dict:
    """返回 {action, hazardId?, message?}。

    action:
      created      -> 已建任务
      ask_address  -> 缺地址，需要追问用户具体地址
      no_category  -> 无法识别类别
      fail         -> 建库失败
    """
    info = _extract(history, latest)
    category = _as_text(info.get("category"))
    if not category:
        return {"action": "no_category", "message": "未能识别隐患类别，暂不建任务"}
    address = _as_text(info.get("address"))
    if not address:
        return {"action": "ask_address",
                "message": "请提供具体地址（如 XX 市 XX 区 XX 路 XX 小区 / XX 地标），我好帮您定位并创建隐患任务。"}
    geo = geocode(address) if address else {}
    payload = {
        "userId": user_id,
        "category": category,
        "address": address,
        "district": _as_text(info.get("district")) or _as_text(geo.get("district")),
        "longitude": geo.get("longitude"),
        "latitude": geo.get("latitude"),
        "description": _as_text(info.get("description")),
        "severity": _as_severity(info.get("severity")),
        "imageUrl": _as_text(info.get("imageUrl")),
        "report": _as_text(info.get("report")),
    }
    LOGGER.info("AI hazard submit payload=%s", payload)
    result = create_hazard(payload)
    if result.get("ok"):
        return {"action": "created", "hazardId": result.get("hazardId"),
                "message": result.get("message")}
    return {"action": "fail", "message": result.get("message", "建库失败")}
