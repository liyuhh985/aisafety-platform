"""可验证的不确定性信号：不问模型，只做代码能核对的判断。

三件事：
1. 槽位值能不能在用户原话/视觉摘要里找到依据（grounding）；
2. 这段输入是不是"正在发生的危险"（动作否决，不做分类）；
3. 规划器与前端大类提示是否互相矛盾（major_mismatch）。

阈值刻意偏松：把好值误判成"编造"会让正常回合降级，而漏判只是维持现状。
"""
import re

from core.hazard_taxonomy import (
    MAJOR_LABELS,
    SUBCATEGORY_LABELS,
    normalize_taxonomy,
)
from core.dialogue_understanding import build_source_map
from core.slot_schemas import get_slot_schema

_FULL_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_PUNCT = re.compile(r"[\s，。、；：！？（）()\"'\-—,.!?;:]+")

GROUNDED_COVERAGE = 0.6
WEAK_COVERAGE = 0.34

# 只用于"动作否决"，不用于分类。含"紧急/马上"这类过宽词会误杀常规隐患上报，
# 所以这里只收口语化的即时危险表达。
DANGER_TERMS = (
    "火烧起来", "起火", "着火了", "着火", "冒烟", "浓烟", "烟很大",
    # 2026-10-01 补：实测「楼道里有易燃物品**正在燃烧**，有很大**黑烟**，里面还有人」
    # 一个词都没命中（原词表只收"起火/着火/冒烟/浓烟/烟很大"这几种说法），
    # 于是危险只剩模型一道防线 —— 那是唯一能压过一切的通道，不能只有一道。
    # 只收明确的燃烧/明火表达，不收光杆"燃烧"（"露天焚烧垃圾"这类不该走应急指引）。
    "正在燃烧", "燃烧起来", "烧起来", "明火", "黑烟", "火势",
    "油锅", "煤气味", "燃气味", "煤气泄漏", "燃气泄漏", "漏气",
    "爆炸", "炸了", "有人被困", "人被困", "被困", "困在里面",
    "人出不来", "出不去", "下不来", "触电", "坍塌", "塌了", "救命",
    "晕倒", "昏迷", "有人掉下去", "掉下去了",
    # v2b：有限空间急性暴露与危化品闪燃的即时危险表达
    "硫化氢", "中毒", "晕厥", "易燃溶剂", "闪燃",
)

# 正在发生的灾害（目前只有地震一类）：原 DANGER_TERMS 只收火灾/燃气/被困这类
# 城市现场隐患，收不进它。但决策 1/4 要求它同样走"应急指引"产物，所以单列一份，
# 由 assess 并入 danger_veto。词表故意收窄（不写单字"晃"），避免误杀常规隐患上报。
EMERGENCY_SITUATION_TERMS = (
    "地震", "余震", "震感", "房子在晃", "楼在晃", "地在晃", "摇得厉害",
)


def normalize_text(value) -> str:
    return _PUNCT.sub("", str(value or "").translate(_FULL_DIGITS))


def _coverage(value: str, source: str) -> float:
    chars = set(value)
    if not chars:
        return 1.0
    return len(chars & set(source)) / len(chars)


def _has_bigram(value: str, source: str) -> bool:
    if len(value) < 2:
        return value in source
    return any(value[i:i + 2] in source for i in range(len(value) - 1))


def _digits_preserved(value: str, source: str) -> bool:
    return all(digit in source for digit in re.findall(r"\d+", value))


def slot_status(value, source: str) -> str:
    """grounded | weak | strong | empty。只有 strong 会影响动作。"""
    normalized = normalize_text(value)
    if not normalized:
        return "empty"
    normalized_source = normalize_text(source)
    if not _digits_preserved(normalized, normalized_source):
        return "strong"
    if _has_bigram(normalized, normalized_source):
        return "grounded"
    coverage = _coverage(normalized, normalized_source)
    if coverage >= GROUNDED_COVERAGE:
        return "grounded"
    if coverage >= WEAK_COVERAGE:
        return "weak"
    return "strong"


def _echo_labels(code) -> set:
    """这条隐患自己的名字（小类名 + 大类名）。"""
    pair = normalize_taxonomy(code)
    if not pair:
        return set()
    labels = set()
    subcategory = SUBCATEGORY_LABELS.get(pair[1])
    if subcategory:
        labels.add(subcategory)
    major = MAJOR_LABELS.get(pair[0])
    if major:
        labels.add(major)
    return labels


# 「包含在事件名字里」这条路要加长度下限：选项词大多是两个字（缺失/破损/松动），
# 而它们往往正好是事件名字的一部分（「井盖缺失/破损」含「缺失」）。
# 实测：用户答「楼下井盖是缺失的」→ 被当成复述丢掉 → 同一道题再问一遍，永远问不完。
ECHO_SUBSTRING_MIN_LENGTH = 3


def is_echo_slot(value, code) -> bool:
    """槽位值只是把隐患名称复述了一遍，不算回答。

    实测：用户只说"旁边还有一栋危房"，规划器把"危房"填进 structure 槽；
    接地检查看到"危房"确实在用户原话里，就判它有依据，于是这条隐患被当成"信息完整"
    写了三段式。但它并没有回答 structure 那个问题（有没有裂缝、倾斜或沉降）。
    """
    text = normalize_text(value)
    if len(text) < 2:
        return False
    for label in _echo_labels(code):
        normalized_label = normalize_text(label)
        if not normalized_label:
            continue
        if text == normalized_label:
            return True
        if len(text) >= ECHO_SUBSTRING_MIN_LENGTH and text in normalized_label:
            return True
    return False


def echo_slots(issues) -> dict:
    """按隐患分组列出"复述问题"的槽位。"""
    grouped = {}
    for issue in issues or []:
        code = (issue or {}).get("subcategory_code") or ""
        for key, value in ((issue or {}).get("slots") or {}).items():
            if is_echo_slot(value, code):
                grouped.setdefault(code, []).append("%s=%s" % (key, value))
    return grouped


def active_danger_term(text) -> str:
    """命中的危险词（没有就返回空串），用于选对口的避险指引。"""
    return _first_danger_term(text)


def has_active_danger(text) -> bool:
    value = normalize_text(text)
    if not value:
        return False
    return bool(_first_danger_term(text))


def _latest_user_text(messages) -> str:
    for message in reversed(_message_dicts(messages)):
        if (message or {}).get("role") in (None, "user"):
            return str((message or {}).get("content") or "")
    return ""


def _message_dicts(messages) -> list:
    out = []
    for message in messages or []:
        if isinstance(message, dict):
            out.append(message)
        else:
            role = "user" if type(message).__name__ == "HumanMessage" else "assistant"
            out.append({"role": role, "content": getattr(message, "content", "")})
    return out


def _source_text(messages, vision_summary: str) -> str:
    parts = [
        str((m or {}).get("content") or "")
        for m in _message_dicts(messages)
        if (m or {}).get("role") in (None, "user")
    ]
    if vision_summary:
        parts.append(str(vision_summary))
    return " ".join(parts)


_NEGATION_RE = re.compile(
    r"(?:没有|并没有|没|无(?!法)|未(?:见|发现|出现|发生)?|不是|并非|暂无|并无|已排除|排除|已清理|已恢复|已修复|已整改)"
)
_CONTRAST_RE = re.compile(r"(?:但|可是|不过|然而|却|已经|仍然|还是|反而|随后|后来)")


def _is_negated_term(normalized: str, start: int) -> bool:
    """Return True only when this occurrence is clearly negated nearby."""
    prefix = normalized[max(0, start - 16):start]
    matches = list(_NEGATION_RE.finditer(prefix))
    if not matches:
        return False
    tail = prefix[matches[-1].end():]
    if len(tail) > 10 or _CONTRAST_RE.search(tail):
        return False
    return True


def _first_active_term(text: str, terms) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""
    for term in terms:
        term_norm = normalize_text(term)
        if not term_norm:
            continue
        start = 0
        while True:
            index = normalized.find(term_norm, start)
            if index < 0:
                break
            if not _is_negated_term(normalized, index):
                return term
            start = index + len(term_norm)
    return ""


def _first_danger_term(text: str) -> str:
    return _first_active_term(text, DANGER_TERMS)


def has_active_situation(text) -> bool:
    """正在发生的灾害（地震等）。"""
    value = normalize_text(text)
    if not value:
        return False
    return bool(active_situation_term(text))


def active_situation_term(text) -> str:
    return _first_active_term(text, EMERGENCY_SITUATION_TERMS)


def _numeric_text(value: str) -> str:
    """Normalize common Chinese numerals that carry facts, without changing text."""
    return (
        str(value or "")
        .translate(_FULL_DIGITS)
        .replace("两", "2")
        .replace("二", "2")
    )


def _quote_in_source(quote: str, source: str) -> bool:
    quote_norm = normalize_text(_numeric_text(quote))
    source_norm = normalize_text(_numeric_text(source))
    return bool(quote_norm) and quote_norm in source_norm


def _value_supported_by_quote(value: str, quote: str) -> bool:
    value_norm = normalize_text(_numeric_text(value))
    quote_norm = normalize_text(_numeric_text(quote))
    return bool(value_norm) and value_norm in quote_norm


def _negated_near_quote(source: str, quote: str, value: str) -> bool:
    """Detect negation that scopes to this quote/value, not a later clause."""
    source_norm = normalize_text(source)
    quote_norm = normalize_text(quote)
    value_norm = normalize_text(value)
    if not source_norm or not quote_norm or not value_norm:
        return False
    start = source_norm.find(quote_norm)
    if start < 0:
        return False
    leading_negation = _NEGATION_RE.match(quote_norm)
    if leading_negation:
        # A quote/value that itself states the absence ("无围挡", "未设置围挡")
        # is a positive fact for that slot, not a contradiction.
        return not value_norm.startswith(leading_negation.group(0))

    raw_source = str(source or "")
    raw_quote = str(quote or "").strip()
    raw_start = raw_source.find(raw_quote) if raw_quote else -1
    if raw_start >= 0:
        prefix = raw_source[max(0, raw_start - 32):raw_start]
        boundary = max(prefix.rfind(ch) for ch in "，。；;")
        clause_prefix = normalize_text(prefix[boundary + 1:])
        return bool(_NEGATION_RE.search(clause_prefix))
    return _is_negated_term(source_norm, start)


def business_status_for(result) -> str:
    """Map detailed audit statuses onto the four public business states."""
    status = str((result or {}).get("status") or "")
    if status in {"grounded", "grounded_by_model"}:
        return status
    if status in {"contradicted", "unverified", "rejected"}:
        return "rejected"
    if status in {"unavailable", "weak", "echo", "missing"}:
        return "unavailable"
    if status == "strong" and (result or {}).get("reason") == "legacy":
        return "unavailable"
    return "unavailable"


def _with_business_status(result: dict) -> dict:
    result["business_status"] = business_status_for(result)
    return result


def verify_slot_evidence(slot_key, value, evidence, source_map, category) -> dict:
    """Verify model-cited evidence using deterministic text operations only."""
    value = str(value or "").strip()
    if not value:
        return _with_business_status({
            "status": "missing", "reason": "empty_value", "value": value,
        })

    allowed = {slot.key for slot in get_slot_schema(category)}
    if slot_key not in allowed:
        return _with_business_status({
            "status": "unverified", "reason": "slot_not_allowed",
            "value": value, "quote": "", "source_ref": "",
        })
    if is_echo_slot(value, category):
        return _with_business_status({
            "status": "echo", "reason": "echo_slot_name",
            "value": value, "quote": "", "source_ref": "",
        })

    evidence = evidence if isinstance(evidence, dict) else {}
    quote = str(evidence.get("quote") or "").strip()
    source_ref = str(evidence.get("source_ref") or "").strip()
    base = {"value": value, "quote": quote, "source_ref": source_ref}

    if not quote:
        return _with_business_status({
            "status": "unverified", "reason": "no_evidence", **base,
        })
    if not source_ref:
        return _with_business_status({
            "status": "unverified", "reason": "invalid_source_ref", **base,
        })
    if source_ref.startswith("a"):
        return _with_business_status({
            "status": "unverified", "reason": "assistant_source", **base,
        })
    if source_ref not in source_map:
        return _with_business_status({
            "status": "unverified", "reason": "invalid_source_ref", **base,
        })
    if source_ref[:1] not in {"u", "v"}:
        return _with_business_status({
            "status": "unverified", "reason": "invalid_source_ref", **base,
        })

    quote_length = len(normalize_text(quote))
    if quote_length < 2:
        return _with_business_status({
            "status": "unverified", "reason": "quote_too_short", **base,
        })
    if quote_length > 80:
        return _with_business_status({
            "status": "unverified", "reason": "quote_too_long", **base,
        })

    source = str(source_map.get(source_ref) or "")
    if not _quote_in_source(quote, source):
        return _with_business_status({
            "status": "unverified", "reason": "quote_not_found", **base,
        })
    if not all(
        digit in normalize_text(_numeric_text(source))
        for digit in re.findall(r"\d+", normalize_text(_numeric_text(value)))
    ):
        return _with_business_status({
            "status": "unverified", "reason": "numeric_mismatch", **base,
        })
    if _negated_near_quote(source, quote, value):
        return _with_business_status({
            "status": "contradicted", "reason": "negation_conflict", **base,
        })
    if _value_supported_by_quote(value, quote):
        return _with_business_status({
            "status": "grounded", "reason": "", **base,
        })
    return _with_business_status({
        "status": "weak", "reason": "value_not_in_quote", **base,
    })


def assess(plan: dict, messages: list, vision_summary: str = "") -> dict:
    """Return both legacy grounding and internal evidence audit.

    ``legacy_*`` fields preserve the pre-evidence behavior for off/shadow mode.
    The evidence fields become authoritative only when the graph selects enforce
    mode; direct callers still receive a complete, inspectable audit.
    """
    plan = plan if isinstance(plan, dict) else {}
    source = _source_text(messages, vision_summary)
    source_map = build_source_map(messages, vision_summary)
    signals = []
    legacy_ungrounded = []
    legacy_total = 0
    legacy_grounded = 0
    evidence_total = 0
    evidence_grounded = 0
    evidence_ungrounded = []
    audit = {}

    for issue in plan.get("issues") or []:
        issue = issue if isinstance(issue, dict) else {}
        code = issue.get("subcategory_code") or ""
        evidence_by_slot = {
            item.get("slot"): item
            for item in (issue.get("evidence") or [])
            if isinstance(item, dict) and item.get("slot")
        }
        for key, value in (issue.get("slots") or {}).items():
            legacy_status = slot_status(value, source)
            if legacy_status == "empty":
                continue
            legacy_total += 1
            if legacy_status == "grounded":
                legacy_grounded += 1
            elif legacy_status == "strong":
                legacy_ungrounded.append("%s.%s=%s" % (code, key, value))
                signals.append("ungrounded_slot:%s.%s=%s" % (code, key, value))

            typed_evidence = evidence_by_slot.get(key)
            if typed_evidence:
                result = verify_slot_evidence(
                    key, value, typed_evidence, source_map, code,
                )
            else:
                result = _with_business_status({
                    "status": legacy_status, "reason": "legacy", "value": str(value),
                })

            evidence_total += 1
            if result.get("status") == "grounded":
                evidence_grounded += 1
            if result.get("status") in {"unverified", "contradicted", "strong"}:
                evidence_ungrounded.append("%s.%s=%s" % (code, key, value))
            audit.setdefault(code, {})[key] = result

    if plan.get("major_mismatch"):
        codes = ",".join((i or {}).get("major_code") or "" for i in plan.get("issues") or [])
        signals.append("major_mismatch:%s->%s" % (plan.get("selected_major_code") or "?", codes))

    danger_term = _first_danger_term(_latest_user_text(messages))
    situation_term = active_situation_term(_latest_user_text(messages))
    model_danger = bool(plan.get("immediate_danger"))
    planner_danger = str(plan.get("scope") or "").strip() == "emergency"
    if danger_term:
        signals.append("danger_term:%s" % danger_term)
    elif situation_term:
        signals.append("emergency_situation:%s" % situation_term)
    elif model_danger:
        signals.append("immediate_danger:model")
    elif planner_danger:
        signals.append("emergency_scope:planner")

    legacy_cautions = bool(legacy_ungrounded) or bool(plan.get("major_mismatch"))
    evidence_cautions = bool(evidence_ungrounded) or bool(plan.get("major_mismatch"))
    return {
        "uncertainty_level": "cautious" if evidence_cautions else "ok",
        "danger_veto": bool(danger_term) or bool(situation_term)
        or model_danger or planner_danger,
        "ungrounded_slots": evidence_ungrounded,
        "grounding_ratio": (evidence_grounded / evidence_total) if evidence_total else 1.0,
        "uncertainty_signals": signals,
        "slot_evidence_audit": audit,
        "evidence_ungrounded_slots": evidence_ungrounded,
        "legacy_ungrounded_slots": legacy_ungrounded,
        "legacy_uncertainty_level": "cautious" if legacy_cautions else "ok",
        "legacy_grounding_ratio": (legacy_grounded / legacy_total) if legacy_total else 1.0,
    }