"""Deterministic hazard-major routing with a metadata-only LLM fallback."""
import json

from config import MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL
from core.agent import Agent
from core.uncertainty import normalize_text

STRONG_WEIGHT = 3
LLM_CONFIDENCE_THRESHOLD = 0.7

_NEGATIVE_PHRASES = (
    "消防员招聘", "消防招聘", "燃气费", "燃气缴费", "水电费",
    "招聘条件", "招聘要求",
)

_skill_router_agent = Agent(
    name="skill_route",
    system_prompt="你是城市安全隐患大类路由器，只返回 JSON。",
    tools=[],
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
    slot="small",
)


def _is_negative(text: str) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(phrase) in normalized for phrase in _NEGATIVE_PHRASES)


def route_by_keywords(text, metadata_catalog, max_skills=3):
    """Route only when every candidate has a strong keyword hit."""
    if _is_negative(text):
        return {"active_skills": [], "source": "negative", "confidence": 0.0}
    normalized = normalize_text(text)
    candidates = []
    for index, meta in enumerate(metadata_catalog or []):
        category = str((meta or {}).get("category") or "").strip()
        if not category:
            continue
        hits = []
        first_position = None
        for keyword in (meta.get("routing_keywords") or []):
            key = normalize_text(keyword)
            if not key:
                continue
            position = normalized.find(key)
            if position >= 0:
                hits.append(str(keyword))
                first_position = position if first_position is None else min(first_position, position)
        if not hits:
            continue
        candidates.append({
            "category": category,
            "score": STRONG_WEIGHT * len(hits),
            "has_strong": True,
            "first_position": first_position if first_position is not None else 10**9,
            "index": index,
        })
    if 1 <= len(candidates) <= max_skills:
        candidates.sort(key=lambda item: (item["first_position"], item["index"]))
        return {
            "active_skills": [item["category"] for item in candidates],
            "source": "keyword",
            "confidence": 0.9,
        }
    return {"active_skills": [], "source": "need_llm", "confidence": 0.0}


def route_skills(text, metadata_catalog, selected_major_codes=None,
                 locked_majors=None, vision_categories=None, route_llm=None,
                 max_skills=3):
    valid = {
        str(meta.get("category") or "").strip()
        for meta in (metadata_catalog or [])
        if isinstance(meta, dict) and meta.get("category")
    }

    def canonical(values):
        out = []
        for item in values or []:
            code = str(item or "").strip()
            if code in valid and code not in out:
                out.append(code)
        return out[:max_skills]

    locked = canonical(locked_majors)
    if locked:
        return {"active_skills": locked, "source": "locked", "confidence": 1.0}
    selected = canonical(selected_major_codes)
    if selected:
        return {"active_skills": selected, "source": "frontend", "confidence": 1.0}
    vision = canonical(vision_categories)
    if vision:
        return {"active_skills": vision, "source": "vision", "confidence": 0.9}

    keyword = route_by_keywords(text, metadata_catalog, max_skills=max_skills)
    if keyword["active_skills"]:
        return keyword
    if keyword.get("source") == "negative":
        return keyword
    if route_llm:
        try:
            llm = route_llm(text, metadata_catalog) or {}
            confidence = float(llm.get("confidence") or 0.0)
        except Exception:
            llm, confidence = {}, 0.0
        skills = canonical(llm.get("active_skills") if isinstance(llm, dict) else [])
        if skills and confidence >= LLM_CONFIDENCE_THRESHOLD:
            return {"active_skills": skills, "source": "llm", "confidence": confidence}
    return {"active_skills": [], "source": "fallback", "confidence": 0.0}


def route_llm_with_agent(text, metadata_catalog):
    prompt = (
        "只判断用户文本属于哪些城市安全隐患大类。"
        "只返回 JSON：{\"active_skills\": [...], \"confidence\": 0.0}。"
        "最多三个 category，不允许自造。\n"
        f"metadata={metadata_catalog}\n用户文本={text}"
    )
    try:
        response = _skill_router_agent._call_llm([{"role": "user", "content": prompt}])
        content = (response or {}).get("content") or ""
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end < start:
            return {}
        data = json.loads(content[start:end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


_skill_route_llm = route_llm_with_agent