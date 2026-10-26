"""AI 上报闭环：从对话抽取隐患信息 -> 高德地理编码 -> 调 Java 建库。

- _extract：用 LLM 从（历史 + 最新消息）抽 categoryList(最多3条)/address/district/description/severity。
- submit_from_history：geocode 补坐标（失败降级），再写 request+outbox 交给 MQ。
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
from tools.hazard_create_queue import enqueue_hazard_create
from tools.amap_geo import geocode

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




# 轻量地址抽取器（不带工具、不加载 32 小类清单）：
# 确认卡片要在「出报告之后、点确认之前」就显示地址；重抽取器 _extract
# 带全套 32 小类清单还要归一化类别，太慢，所以单独做一个只问地点的。
_location_extractor = Agent(
    name="hazard_address_extract",
    system_prompt="你是地址抽取器，只从对话中提取用户描述的地点，不编造。",
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


# 一次上报最多允许的隐患类别数（第一条为主类别）。
MAX_CATEGORY_LIST = 3


def _normalize_category_list(value) -> list:
    """把抽取模型给的类别（列表或单值）归一化成 canonical major/subcategory 列表。

    契约：最多 MAX_CATEGORY_LIST 条、按原顺序去重、第一条为主类别；
    解析不出的条目直接丢弃。模型给单值（非列表）时按一条处理，坏格式退化成空列表。
    """
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = []
    result = []
    for item in items:
        pair = normalize_taxonomy(_as_text(item))
        if not pair:
            continue
        code = format_hazard_type(pair[0], pair[1])
        if not code or code in result:
            continue
        result.append(code)
        if len(result) >= MAX_CATEGORY_LIST:
            break
    return result


def _render(history, latest) -> str:
    parts = []
    for h in (history or [])[-10:]:
        parts.append(f"[{h.get('role', 'user')}] {h.get('content', '')}")
    parts.append(f"[user] {latest}")
    return "\n".join(parts)


def _extract(history, latest) -> dict:
    prompt = (
        "请从下面对话中抽取隐患上报信息，只返回 JSON，字段："
        "categoryList(隐患类别列表，最多 3 条，按重要程度从高到低排序，第一条为主类别，"
        "每条必须使用 major_code/subcategory_code 格式)，"
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
        # categoryList 归一化成 canonical major/subcategory 形式：
        # 丢弃解析不出的、按原顺序去重、最多保留 MAX_CATEGORY_LIST 条（第一条为主类别）。
        category_list = _normalize_category_list(data.get("categoryList"))
        if not category_list:
            # 兼容模型只给单类别、或 categoryList 坏格式：退回单类别
            category_list = _normalize_category_list(data.get("category"))
        data["categoryList"] = category_list
        data["category"] = category_list[0] if category_list else ""
        data["severity"] = _as_severity(data.get("severity"))
        if not data.get("address"):
            data["address"] = _regex_address(_render(history, latest))
        return data
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("hazard extract failed: %s", e)
        return {"category": "", "categoryList": [], "address": "", "district": "",
                "description": "", "severity": 1}


# 地址结构判据：机器抽出来的"地址"必须带行政/道路/地名标记。
# 为什么必须有它（实测）：轻量抽取器对"楼道""楼下"这类相对位置也给得出文本，
# 而高德会把它匹配到别的城市（实测"楼道" -> 广州番禺区，坐标 113.4/22.96），
# 于是系统会静默建出一条"位置完全错误"的工单 —— 比"没有地址"更糟。
# 所以宁可判空，让流程回到既有的「追问地址」。
_ADDRESS_HINT_RE = re.compile(
    r"(省|市|区|县|镇|乡|街道|社区|村|路|街|大道|巷|弄|号|"
    r"小区|广场|大厦|大楼|园区|公园|车站|医院|学校|超市|商场|工地|桥)"
)


def _looks_like_address(text: str) -> bool:
    """粗判一个字符串像不像"能定位的地址"；宁可判否（回到追问地址）。"""
    value = _as_text(text)
    return len(value) >= 4 and bool(_ADDRESS_HINT_RE.search(value))


def extract_location(history, latest) -> str:
    """轻量预抽取地址，供确认卡片在点确认之前显示。

    为什么单独做一个轻量的：确认卡片要在**出报告之后、点确认之前**就把地址
    显示出来，而 _extract 重抽取器带全套 32 小类清单、还要归一化类别，太慢。
    这里只问地点，只返回 {"address": ..., "district": ...}。LLM 调用失败或返回
    空时用 _regex_address 兜底，都没有则返回空串。
    """
    prompt = (
        "请从下面对话中提取用户描述的隐患地点，只返回 JSON，字段："
        "address(可定位的具体地点，如'XX市XX区XX路XX小区门口'；"
        "如果对话里只有'楼道/楼下/家门口'这类相对位置、或根本没说地点，address 留空)，"
        "district(省/市/区，没有为空)。不要编造，只依据对话。\n"
        f"对话：\n{_render(history, latest)}"
    )
    try:
        resp = _location_extractor._call_llm(
            [{"role": "user", "content": prompt}], cancellation=None)
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
        address = _as_text(data.get("address"))
        if _looks_like_address(address):
            return address
        if address:
            LOGGER.warning("location extract rejected address=%r", address)
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("location extract failed: %s", e)
    fallback = _regex_address(_render(history, latest))
    return fallback if _looks_like_address(fallback) else ""


def submit_from_history(user_id, history, latest, *, address_hint: str = "", coords=None,
                        session_id: str = "", image_url: str = "",
                        image_file_id=None) -> dict:
    """返回 {action, hazardId?, message?}。

    action:
      created      -> 已建任务（旧同步链路，MQ 关闭时）
      accepted     -> 已受理，等待 MQ/Java 建单（MQ 打开时）
      ask_address  -> 缺地址，需要追问用户具体地址
      no_category  -> 无法识别类别
      fail         -> 建库失败

    address_hint: 用户确认或改过的地址字符串，优先于重抽取器结果（可为空）。
    coords: (longitude, latitude) 二元组；用户在图上选点时直接当坐标用，跳过 geocode。
    """
    info = _extract(history, latest)
    category_list = _normalize_category_list(info.get("categoryList"))
    if not category_list:
        # 兼容本次改造前的单类别 info，也兜住 categoryList 坏格式
        category_list = _normalize_category_list(info.get("category"))
    category = _as_text(info.get("category"))
    # 防御：category 为空但 categoryList 非空 -> 用主类别（categoryList[0]）
    if not category and category_list:
        category = category_list[0]
    if not category:
        return {"action": "no_category", "message": "未能识别隐患类别，暂不建任务"}
    # 用户确认/改过的地址优先于重抽取器给出的地址
    address = _as_text(address_hint) or _as_text(info.get("address"))
    if not address:
        return {"action": "ask_address",
                "message": "请提供具体地址（如 XX 市 XX 区 XX 路 XX 小区 / XX 地标），我好帮您定位并创建隐患任务。"}
    if coords:
        # 用户在图上选点：直接当坐标用，不调 geocode
        geo = {"longitude": coords[0], "latitude": coords[1]}
    else:
        geo = geocode(address)
    payload = {
        "userId": user_id,
        "category": category,
        "categoryList": category_list,
        "address": address,
        "district": _as_text(info.get("district")) or _as_text(geo.get("district")),
        "longitude": geo.get("longitude"),
        "latitude": geo.get("latitude"),
        "description": _as_text(info.get("description")),
        "severity": _as_severity(info.get("severity")),
        "imageUrl": _as_text(image_url) or _as_text(info.get("imageUrl")),
        "imageFileId": image_file_id,
        "report": _as_text(info.get("report")),
    }
    LOGGER.info("AI hazard submit payload=%s", payload)

    # MQ 唯一链路：事务内写 request + outbox，返回 accepted（先写库再返回）。
    try:
        accepted = enqueue_hazard_create(user_id, session_id, payload)
    except Exception as e:  # noqa: BLE001
        LOGGER.exception("hazard create enqueue failed")
        return {"action": "fail", "message": f"受理失败：{e}"}
    if accepted.get("ok"):
        return {"action": "accepted", "requestId": accepted.get("requestId"),
                "message": "已受理，正在创建"}
    return {"action": "fail", "message": accepted.get("message", "受理失败")}
