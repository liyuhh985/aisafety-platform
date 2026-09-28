"""Deterministic scope guard for the city-safety hazard assistant."""
import hashlib

from core.uncertainty import DANGER_TERMS, EMERGENCY_SITUATION_TERMS

VALID_SCOPES = {"hazard", "emergency", "smalltalk", "ambiguous", "out_of_scope"}

SMALLTALK = {
    "你好", "您好", "嗨", "哈喽", "在吗", "在么", "在不在",
    "早上好", "中午好", "下午好", "晚上好", "谢谢", "感谢",
}

# 与 core.uncertainty.DANGER_TERMS 共用一份清单：同一个含义只允许有一个定义。
# 原来的"马上/紧急"过宽，实测 4/4 误杀常规隐患上报（紧急出口被堵、马上要下雨、这事很紧急…）。
EMERGENCY_KEYWORDS = DANGER_TERMS

# 依据（2026-09-28 扩表）：这一族原先只有字面「占道」一个词，于是整条范围判据
# 全挂在「规划器是否稳定抽出 issues」上 —— 模型一抖就落到 decide_scope 最后一条
# out_of_scope("no hazard signal")。实测记录过一次真实误拦：
#   db/eval_stage5_e2e.txt:「有人在人行道上摆摊经营」被规划器报成 smalltalk
#   → out_of_scope → boundary_reply（用户描述的是本领域隐患，却被拒绝）。
# 补词的两处依据：
#   1) taxonomy 自己的标签：road_occupancy「占道经营/乱堆乱放」、
#      vehicle_occupancy「车辆占道」、blind_path_occupied「盲道占用」，
#      大类 traffic 的标签是「交通与通行」；
#   2) 语料实际用词：人行道 24 条、堆放 15 条、违停 6 条、乱堆 3 条。
# 有意不收单字「摊」：摊开/摊牌/摊销都是域外说法，收了会把越界输入误放进来。
DOMAIN_KEYWORDS = (
    "隐患", "安全", "占道", "盲道", "消防通道", "消防设施", "消火栓",
    "灭火器", "喷淋", "消防水源", "危房", "裂缝", "倾斜", "沉降",
    "高空坠物", "外墙", "广告牌", "井盖", "窨井", "路面", "塌陷",
    "电线", "漏电", "电缆", "配电箱", "燃气", "管道", "施工", "工地",
    "围挡", "脚手架", "深基坑", "电梯", "垃圾堆积", "污水", "异味",
    "违规搭建", "路灯", "线杆", "排水", "积水",
    # 占道家族（依据见上）
    "人行道", "乱堆", "乱堆放", "堆放", "违停",
    "摆摊", "摊位", "摊贩", "马路市场",
)

AMBIGUOUS_KEYWORDS = (
    "我有个问题", "想问一下", "帮我看看", "这个怎么办", "有个事",
)

EMERGENCY_RESPONSE = (
    "如果现场正在起火、有人被困、燃气泄漏，或存在触电、坍塌等即时危险，"
    "请先确保自身安全并立即拨打 119（火警/救援）或 110。"
    "安全后，再描述具体位置和现场情况，我继续帮你判断隐患。"
)

AMBIGUOUS_RESPONSES = (
    "我主要处理城市安全隐患。你说的情况是否涉及占道、消防、建筑、电气、"
    "燃气、施工、电梯或市政设施等现场隐患？",
    "我这边主要看现场安全隐患。你想问的是哪一类安全问题？如果和占道、消防、"
    "建筑或电气无关，我可能帮不上忙。",
)

OUT_OF_SCOPE_RESPONSES = (
    "我主要负责城市安全隐患的识别、法规案例查询和隐患上报。"
    "你可以描述占道、消防、建筑、电气、燃气、施工、电梯、市政设施等隐患；"
    "其他话题我暂时不能提供专业结论。",
    "这个问题不在我的专业范围内。我主要处理城市安全隐患和上报，"
    "如果是现场安全问题，可以直接描述，我继续帮你判断。",
    "我这边只负责城市安全隐患相关咨询。你可以说说现场有没有占道、消防、"
    "建筑、电气、燃气或施工方面的隐患。",
)

AMBIGUOUS_RESPONSE = AMBIGUOUS_RESPONSES[0]
OUT_OF_SCOPE_RESPONSE = OUT_OF_SCOPE_RESPONSES[0]


# ====== 应急指引（危险场景的产物，见决策 1 / 决策 4）======
# 统一原则：代码负责"必须覆盖什么"，模型负责"怎么说"，代码再核对"有没有覆盖"。
# 每种危险类型给出 points（必含要点，每组是同义并列，命中任意一个即算覆盖）
# 与 fallback（模型没覆盖到要点时，代码前置的兜底句）。
# 顺序 = 识别优先级：燃气排在火灾前面，因为"漏气 + 有烟"要按燃气处理（关阀比撤离更急）。
EMERGENCY_GUIDANCE_TYPES = {
    "gas": {
        "terms": ("煤气味", "燃气味", "煤气泄漏", "燃气泄漏", "漏气"),
        # 开场动作：一句话说全四个要点，用户第一眼就知道该做什么
        "lead": "先关掉燃气总阀、打开窗户通风、不要碰任何电器开关，然后撤到室外，再打 119",
        "points": (("关", "阀门", "总阀"), ("通风", "开窗", "窗户"),
                   ("电器", "明火", "开关"), ("室外", "撤离", "离开", "疏散")),
        "fallback": (
            "请立即开窗通风、关闭燃气总阀，不要开关任何电器或使用明火，"
            "先撤到室外再联系燃气公司抢修；有人不适请立即拨打 119。"
        ),
    },
    "electric": {
        "terms": ("触电", "漏电", "电到"),
        "lead": "先切断电源、不要直接碰伤者，同时拨打 120 急救",
        "points": (("断电", "切断电源", "拉闸", "关掉电源", "绝缘", "不要碰"),
                   ("120", "119", "急救", "报警", "救援")),
        "fallback": (
            "请先切断电源再靠近，不要直接用手触碰伤者或带电体，"
            "有人受伤或昏迷请立即拨打 120 急救、119 救援。"
        ),
    },
    "collapse": {
        "terms": ("坍塌", "塌了", "垮了", "倒塌", "塌方"),
        "lead": "先撤离并远离坍塌区域，同时拨打 119 报警",
        "points": (("撤离", "远离", "离开", "疏散", "不要靠近"),
                   ("119", "120", "报警", "救援", "急救")),
        "fallback": (
            "请立即远离坍塌区域，不要靠近或返回取物；"
            "如有人被埋压，立即拨打 119 等待专业救援，不要自行挖掘。"
        ),
    },
    "earthquake": {
        # 词表复用 uncertainty 里那一份：同一个含义只允许有一个定义。
        "terms": EMERGENCY_SITUATION_TERMS,
        "lead": "先就地蹲下、护住头颈，震动一停就走楼梯到室外空旷处",
        "points": (("蹲下", "趴下", "躲避", "掩护", "躲到", "三角"),
                   ("空旷", "室外", "远离建筑", "远离外墙", "不要乘电梯")),
        "fallback": (
            "请先就近蹲下、护住头颈，远离窗户和吊挂物；"
            "震动停止后走楼梯撤到室外空旷地带，不要乘坐电梯，注意余震，"
            "有人受伤请拨打 120、被困请拨打 119。"
        ),
    },
    "fire": {
        "terms": ("起火", "着火了", "着火", "火烧起来", "冒烟", "浓烟", "烟很大",
                  "油锅", "爆炸", "炸了", "有人被困", "人被困", "被困"),
        "lead": "先低姿撤离到室外安全地带，并立即拨打 119 报警",
        "points": (("撤离", "离开", "疏散", "远离", "逃生", "低姿", "弯腰"),
                   ("119", "报警", "火警", "救援")),
        "fallback": (
            "请立即低姿撤离到室外安全地带并拨打 119 报警，"
            "不要为取回物品返回室内，也不要乘坐电梯。"
        ),
    },
}

# 识别不出具体类型时的兜底要点：只要求"报警 + 避险"这两件最不能漏的事。
GENERIC_EMERGENCY_POINTS = (
    ("119", "110", "120", "报警", "救援", "急救"),
    ("安全", "撤离", "远离", "离开", "疏散", "避开"),
)

# 识别不出类型时的开场动作
GENERIC_EMERGENCY_LEAD = "先撤离到安全地点，并立即拨打 119 报警"


def emergency_guidance_type(text: str) -> str:
    """这段危险输入属于哪一类应急场景；识别不出返回空串。"""
    value = str(text or "")
    for kind, spec in EMERGENCY_GUIDANCE_TYPES.items():
        if any(term in value for term in spec["terms"]):
            return kind
    return ""


def emergency_guidance_points(kind: str) -> tuple:
    spec = EMERGENCY_GUIDANCE_TYPES.get(kind) or {}
    return tuple(spec.get("points") or GENERIC_EMERGENCY_POINTS)


def emergency_guidance_fallback(kind: str) -> str:
    spec = EMERGENCY_GUIDANCE_TYPES.get(kind) or {}
    return spec.get("fallback") or EMERGENCY_RESPONSE


def emergency_guidance_lead(kind: str) -> str:
    """该类型的「开场动作」：第一句就要说全的要点。

    用途是约束模型产出**顺序** —— 关键动作放第一句，首块就不必等到最后一段才发出。
    它和 fallback 的区别：fallback 是"模型没说全时代码前置的兜底句"，
    lead 只是给模型的**示范句式**（模型应自己措辞），两者字符串不同。
    """
    spec = EMERGENCY_GUIDANCE_TYPES.get(kind) or {}
    return spec.get("lead") or GENERIC_EMERGENCY_LEAD


def covers_emergency_points(text: str, kind: str) -> bool:
    """模型输出是否覆盖了该类别的必含要点（关键词级核对，不判语义）。"""
    value = str(text or "")
    return all(any(word in value for word in group) for group in emergency_guidance_points(kind))


def _pick_template(templates: tuple[str, ...], scope_key: str) -> str:
    if not scope_key:
        return templates[0]
    digest = hashlib.md5(scope_key.encode("utf-8")).hexdigest()
    return templates[int(digest, 16) % len(templates)]


def _decision(scope: str, reason: str = "", response: str = "") -> dict:
    return {"scope": scope, "reason": reason, "response": response}


def decide_scope(plan: dict, user_text: str, scope_key: str = "") -> dict:
    """Decide whether the message is in the hazard-assistant scope."""
    text = (user_text or "").strip()
    normalized = text.rstrip("！!。？?～~ ").strip()
    if not text:
        return _decision(
            "ambiguous",
            reason="empty message",
            response=_pick_template(AMBIGUOUS_RESPONSES, scope_key),
        )

    if any(keyword in text for keyword in EMERGENCY_KEYWORDS):
        return _decision("emergency", reason="emergency keyword", response=EMERGENCY_RESPONSE)

    if normalized in SMALLTALK:
        return _decision("smalltalk", reason="greeting/thanks")

    plan = plan if isinstance(plan, dict) else {}
    issues = plan.get("issues") or []
    if issues:
        return _decision("hazard", reason="planner resolved hazard issues")

    if any(keyword in text for keyword in DOMAIN_KEYWORDS):
        return _decision("hazard", reason="precise domain keyword")

    planner_scope = str(plan.get("scope") or "").strip()
    try:
        scope_confidence = float(plan.get("scope_confidence", 0.0))
    except (TypeError, ValueError):
        scope_confidence = 0.0

    if planner_scope == "hazard" and scope_confidence >= 0.7:
        return _decision("hazard", reason="planner hazard scope")
    if planner_scope == "emergency":
        return _decision("emergency", reason="planner emergency scope", response=EMERGENCY_RESPONSE)
    if planner_scope == "ambiguous":
        return _decision(
            "ambiguous",
            reason="planner ambiguous scope",
            response=_pick_template(AMBIGUOUS_RESPONSES, scope_key),
        )
    if planner_scope == "out_of_scope":
        return _decision(
            "out_of_scope",
            reason="planner out-of-scope",
            response=_pick_template(OUT_OF_SCOPE_RESPONSES, scope_key),
        )

    if any(keyword in text for keyword in AMBIGUOUS_KEYWORDS):
        return _decision(
            "ambiguous",
            reason="ambiguous request",
            response=_pick_template(AMBIGUOUS_RESPONSES, scope_key),
        )

    return _decision(
        "out_of_scope",
        reason="no hazard signal",
        response=_pick_template(OUT_OF_SCOPE_RESPONSES, scope_key),
    )
