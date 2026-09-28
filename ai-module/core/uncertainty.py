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

_FULL_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_PUNCT = re.compile(r"[\s，。、；：！？（）()\"'\-—,.!?;:]+")

GROUNDED_COVERAGE = 0.6
WEAK_COVERAGE = 0.34

# 只用于"动作否决"，不用于分类。含"紧急/马上"这类过宽词会误杀常规隐患上报，
# 所以这里只收口语化的即时危险表达。
DANGER_TERMS = (
    "火烧起来", "起火", "着火了", "着火", "冒烟", "浓烟", "烟很大",
    "油锅", "煤气味", "燃气味", "煤气泄漏", "燃气泄漏", "漏气",
    "爆炸", "炸了", "有人被困", "人被困", "被困", "困在里面",
    "人出不来", "出不去", "下不来", "触电", "坍塌", "塌了", "救命",
    "晕倒", "昏迷", "有人掉下去", "掉下去了",
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
        if text == normalized_label or text in normalized_label:
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
    return any(normalize_text(term) in value for term in DANGER_TERMS)


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


def _first_danger_term(text: str) -> str:
    normalized = normalize_text(text)
    for term in DANGER_TERMS:
        if normalize_text(term) in normalized:
            return term
    return ""


def has_active_situation(text) -> bool:
    """正在发生的灾害（地震等）。"""
    value = normalize_text(text)
    if not value:
        return False
    return any(normalize_text(term) in value for term in EMERGENCY_SITUATION_TERMS)


def active_situation_term(text) -> str:
    normalized = normalize_text(text)
    for term in EMERGENCY_SITUATION_TERMS:
        if normalize_text(term) in normalized:
            return term
    return ""


def assess(plan: dict, messages: list, vision_summary: str = "") -> dict:
    """三个信号。

    注意两件事的取文范围**故意不同**：
    - grounding 用整段对话（事实可能在前几轮说过）；
    - 危险判定只看本轮原话（加上模型自己给的 immediate_danger）。
      这里不再做"跨轮延续"：类别已被锁定为一条会话一个隐患，
      连续性交给看得见完整对话的模型，代码不再拿两次分类结果去猜。
    """
    plan = plan if isinstance(plan, dict) else {}
    source = _source_text(messages, vision_summary)
    signals = []
    ungrounded = []
    slots_total = 0
    slots_grounded = 0

    for issue in plan.get("issues") or []:
        code = (issue or {}).get("subcategory_code") or ""
        for key, value in ((issue or {}).get("slots") or {}).items():
            status = slot_status(value, source)
            if status == "empty":
                continue
            slots_total += 1
            if status == "grounded":
                slots_grounded += 1
            elif status == "strong":
                ungrounded.append("%s.%s=%s" % (code, key, value))
                signals.append("ungrounded_slot:%s.%s=%s" % (code, key, value))

    if plan.get("major_mismatch"):
        codes = ",".join((i or {}).get("major_code") or "" for i in plan.get("issues") or [])
        signals.append("major_mismatch:%s->%s" % (plan.get("selected_major_code") or "?", codes))

    danger_term = _first_danger_term(_latest_user_text(messages))
    situation_term = active_situation_term(_latest_user_text(messages))
    model_danger = bool(plan.get("immediate_danger"))
    # 规划器直接判了 emergency 也算危险：词表会漏，immediate_danger 也可能没给，
    # 但模型说"这是紧急情况"时我们必须当危险处理，否则删掉 emergency_reply 分支后
    # 这类输入会一句指引都没有。
    planner_danger = str(plan.get("scope") or "").strip() == "emergency"
    if danger_term:
        signals.append("danger_term:%s" % danger_term)
    elif situation_term:
        signals.append("emergency_situation:%s" % situation_term)
    elif model_danger:
        signals.append("immediate_danger:model")
    elif planner_danger:
        signals.append("emergency_scope:planner")

    cautions = bool(ungrounded) or bool(plan.get("major_mismatch"))
    return {
        "uncertainty_level": "cautious" if cautions else "ok",
        "danger_veto": bool(danger_term) or bool(situation_term)
        or model_danger or planner_danger,
        "ungrounded_slots": ungrounded,
        "grounding_ratio": (slots_grounded / slots_total) if slots_total else 1.0,
        "uncertainty_signals": signals,
    }
