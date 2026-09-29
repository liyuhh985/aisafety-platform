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
# 依据（2026-09-28 第二次扩表，补三处同族缺口）：「交通设施损坏」「外立面脱落」「配电设施故障」
# 三个小类原先只有「外墙」「配电箱」两个词兜着 —— 而用户说的是「外立面」「配电设施」，
# 于是整条范围判据又落回「规划器是否稳定抽出 issues」。实测（plan={} 最坏情况，不调模型）：
# 扩表前 10 条本领域表述 10/10 被判 out_of_scope，回复是「不在我的专业范围内」——和占道那次同一种
# 真实误拦形态（用户描述本领域隐患却被拒绝）。
# 语料计数（db/measure_scope_words.py；逐行拼接全字段、每行计一次；case 231 / reg 139 / kb 30）：
#   交通设施 case 8（8/8 落在「交通与通行/交通设施损坏」）、交通标志 case 2、标志牌 case 3、
#   护栏 case 6（6/6 都在本领域类别内）、信号灯 case 0 / reg 1 / kb 1；
#   外立面 case 12（其中 6 条属「外立面脱落」，其余同在建筑安全大类）、墙皮 case 3；
#   配电设施 case 7（其中 6 条属「配电设施故障」）、配电柜 case 2、配电房 case 4。
# 三处依据都能对到 taxonomy 自己的标签：「交通设施损坏」「外立面脱落」「配电设施故障」。
#
# 依据（2026-09-29 第三次扩表，补最后一处已知越界缺口）：「交通标线」—— 扩表前
# 「路上的交通标线看不清了」判 out_of_scope（回复「不在我的专业范围内」），与前面几次同属
# "用户描述本领域隐患却被拒绝"。它的语料计数是 0（case/reg/kb 全 0），所以依据**不是**语料：
#   1) taxonomy 自己的标签：小类 traffic_facility_damage「交通设施损坏」；
#   2) 同族构词：已收录的「交通设施」「交通标志」「标志牌」「信号灯」「护栏」同属该小类；
#   3) 它自带域标记「交通」—— 实测 4 条域外探针 0 命中（见 tests 的反向误伤检查）。
#
# 有意不收（写明理由，免得以后有人凭直觉补回来）：
#   ·「脱落」case 19 条，但跨 4 个类别（外立面脱落 6 / 电梯停运异响 2 / 配电设施故障 2 …），
#     且域外用法多（头发脱落、牙齿脱落、油漆脱落）—— 收了会误放「最近头发脱落得厉害」；
#   ·「变压器」case 2 条且跨类，「变压器的工作原理是什么」是物理题不是隐患上报；
#   ·「电力设施」case 1 条，样本太薄；
#   ·「电箱」case 10 条，但全部来自「配电箱」那些行 —— 是子串，不新增覆盖；
#   ·光杆「标线」：它在语料里是**本领域**用词（case 12 条，分布在 6 个小类，多出现在
#     「施划禁停标线」这类整治措施文本里），但**光杆词有域外家族**（表格标线、图纸标线、
#     衣服标线）—— 与「脱落」同一种排除理由：确定层是子串放行，收录后这 3 条域外探针
#     3/3 会走 "precise domain keyword" 被放行（实测放行后下游模型会自行纠正话题并拒答，
#     代价不高），但按"会误放就不收"的口径仍不收。
#   ·「指示牌」：域外家族更明显（商场指示牌 / 楼层指示牌 / 导览指示牌）。确定层是子串放行
#     （`any(keyword in text)`），光杆词无法区分「路口的指示牌」和「商场的指示牌」——
#     实测收录后 4 条域外探针 4/4 走 "precise domain keyword" 被放行，故不收。
#
# 登记（与词表无关的**既有**缺口，本次未修）：端到端实测发现「商场里的指示牌歪了」
# 「楼层指示牌挂得太低了」会被**规划器**判成隐患（issues 非空 → scope_guard 给出
# "planner resolved hazard issues"），进而生成一份引法规的完整报告。这不是词表造成的 ——
# 词表里没有「指示牌」，这两条在 plan={} 下判 out_of_scope，是规划器自己把它们当成了隐患。
# 属规划器的范围判定缺口，留待单独处理。
#
# 残留（本次有意留下的取舍，靠词表解决不了，如实登记）：
#   ·「地上的标线看不清」「道路标线模糊」—— 不含「交通」，仍判越界；
#   ·「路口的指示牌歪了」—— 光杆「指示牌」不收，故仍判越界。要覆盖它得靠**域锚共现**
#     （指示牌 + 路口/路边/人行道 同现才放行），那要改判据机制（当前是单一
#     `any(keyword in text)`），超出词表改动范围。
#   ·同类未收：「道路标线」（同为含域标记的复合词，但没有任何语料或用户措辞证据）。
#   实际影响比看上去小：确定层判越界之后，规划器还有一次机会 —— 端到端实测
#   「地上的标线看不清」被规划器救住（判成 hazard 并出报告）。词表只在"规划器什么都没给"
#   （plan={}）时才决定结果。
# 「信号灯」「交通标线」是 case 计数为 0 的两个词：收录依据都是它们属「交通设施损坏」的标准
# 用词 —— 「信号灯」另有 reg/kb 各 1 条命中，「交通标线」三条计数全 0（依据见上面第三次
# 扩表那段）。日后若发现这两个词误放，第一个该收回去的就是它们。
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
    # 交通设施 / 外立面 / 配电设施 三族 + 交通标线（依据见上两条注释）
    "交通设施", "交通标志", "标志牌", "护栏", "信号灯", "交通标线",
    "外立面", "墙皮",
    "配电设施", "配电柜", "配电房",
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


# ====== 「要有原文依据」的小类：模型声称的隐患回到原文核对（2026-09-29）======
# 要解决的漏放（复现：db/_diag_planner_leak.py，各 3 次；产物：db/eval_scope_families_e2e_offdomain.txt）：
#   「商场里的指示牌歪了」「楼层指示牌挂得太低了」被**规划器自己**判成 hazard 并给出 issues
#   （traffic/traffic_facility_damage，有时是 environment_other/other），于是下面 decide_scope
#   的 `if issues` 分支直接采信 → 检索 → 一份引《公路安全保护条例》的完整报告。
# 为什么不在词表里解决：DOMAIN_KEYWORDS 是子串放行，收录光杆「指示牌」后 4 条域外探针 4/4
#   被放行（见上面「有意不收」那段），收益小于代价。
# 为什么不能要求"原文必须有域锚"：实测（db/_diag_anchor_coverage.py）40 条现实口吻的本领域
#   表述里 11 条（27.5%）不含任何 DOMAIN_KEYWORDS 词 ——「楼上老是往下扔东西」「楼道里闻到
#   很浓的煤气味」「小区里挖了个大坑，晚上没有灯」。把"必须有域锚"当通用必要条件，会把这
#   27.5% 的真隐患降级成澄清，比漏放更糟。
# 所以规则只对**判据里物件/场所本身就是必要条件**的小类生效：
#   · 物件型（隐患 = 某个物件坏了）：表里 5 类，物件词或场所词必须出现；
#   · 兜底类（其他）：它不是某个物件，只要求原文有"领域词或场所词"。
# 不采信 → 返回 ambiguous（让用户澄清），不用 out_of_scope：项目既有的偏向是
#   "宁可多问一句，也不要把真隐患判成不在专业范围内"。
# 表有意只有这几类；扩表必须先有"模型误判 + 原文没有该物件词"的实例（spec §6）。
# 有意不做物件词的词：光杆「指示牌」（域外家族：商场/楼层/导览牌，与词表同一条理由）、
#   单字「灯」（会放过「商场灯箱」这类无关输入）。
OBJECT_CLASS_EVIDENCE = {
    "traffic_facility_damage": (
        "交通", "标志", "信号灯", "红绿灯", "护栏", "隔离墩", "防撞", "标线", "斑马线",
    ),
    "manhole_damage": (
        "井盖", "窨井", "雨水篦", "雨水口", "盖板", "盖子", "井口",
    ),
    "street_light_pole": (
        "路灯", "线杆", "灯杆", "电线杆", "灯柱", "照明", "杆子",
    ),
    "distribution_box_fault": (
        "配电", "电箱", "电表箱", "变电", "变压器", "电闸",
    ),
    "facade_fall": (
        "外立面", "外墙", "墙面", "墙皮", "瓷砖", "幕墙", "招牌", "广告牌", "雨棚", "楼顶",
    ),
}

# 兜底类：说"其他隐患"时，原文至少要有一个领域词或场所词（它自己不是物件，没有物件词表）。
CATCH_ALL_SUBCATEGORIES = ("other",)

# 公共场所词：命中即算"这件事发生在公共空间"。有意宽松 —— 只用于**放行**（抑制否决），
# 宽松的代价是"少否决"，方向安全，不会造成误拦真隐患。
# 有意不收「小区」「楼道」「院」「门口」这类共享但室内的空间词：门口挂一块导览牌不是交通设施，
# 而这类表述里通常本来就有物件词（井盖/配电箱/路灯）撑着，不需要靠场所词放行。
PUBLIC_SPACE_WORDS = (
    "路", "道", "街", "巷", "桥", "公共", "户外", "室外", "露天", "街边",
    "道边", "路边", "车道", "人行道", "斑马线", "车库", "停车场", "广场",
    "公园", "工地", "天桥", "隧道", "涵洞", "高架", "地铁",
)


def unbacked_hazard_claim(issues, evidence_text: str) -> str:
    """模型声称的隐患，原文（用户原话 + 视觉摘要）里有没有依据。

    返回第一个缺依据的小类编码；都有依据、或不在核对范围内则返回空串。
    纯函数：只读 issues 与文本，不调模型 —— 所以可单测、可做变异实验。
    """
    evidence = str(evidence_text or "")
    has_domain_word = any(word in evidence for word in DOMAIN_KEYWORDS)
    has_place_word = any(word in evidence for word in PUBLIC_SPACE_WORDS)
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("subcategory_code") or "").strip()
        if code in CATCH_ALL_SUBCATEGORIES:
            if has_domain_word or has_place_word:
                continue
            return code
        words = OBJECT_CLASS_EVIDENCE.get(code)
        if not words:
            continue
        if has_domain_word or has_place_word:
            continue
        if any(word in evidence for word in words):
            continue
        return code
    return ""


def _pick_template(templates: tuple[str, ...], scope_key: str) -> str:
    if not scope_key:
        return templates[0]
    digest = hashlib.md5(scope_key.encode("utf-8")).hexdigest()
    return templates[int(digest, 16) % len(templates)]


def _decision(scope: str, reason: str = "", response: str = "") -> dict:
    return {"scope": scope, "reason": reason, "response": response}


def decide_scope(plan: dict, user_text: str, scope_key: str = "",
                 support_text: str = "") -> dict:
    """Decide whether the message is in the hazard-assistant scope.

    support_text：原文的另一部分（目前是视觉摘要）。它只参与"有没有依据"的核对，
    不参与确定性词表判定 —— 词表仍然只看用户这句话。
    """
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
        # 模型说这是隐患 → 回到原文核对（物件词 / 场所词 / 领域词）。
        # 核对不过不是"越界"，是"这条说法没有依据" → 让用户澄清（见本节顶部注释）。
        unbacked = unbacked_hazard_claim(issues, text + "\n" + str(support_text or ""))
        if unbacked:
            return _decision(
                "ambiguous",
                reason="unbacked hazard claim:%s" % unbacked,
                response=_pick_template(AMBIGUOUS_RESPONSES, scope_key),
            )
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
