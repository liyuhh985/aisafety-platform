"""Structured semantic understanding for the safety assistant dialogue."""
import json
import re

from config import MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL, PLANNER_HISTORY_MESSAGES
from core.agent import Agent
from core.hazard_taxonomy import (
    ALL_SUBCATEGORY_CODES,
    HAZARD_TAXONOMY,
    MAJOR_LABELS,
    SUBCATEGORY_DEFAULT_RISK,
    SUBCATEGORY_LABELS,
    format_hazard_type,
    normalize_taxonomy,
)
from core.slot_schemas import (
    get_slot_schema,
    missing_decision_slots,
    missing_report_slots,
)

_planner_llm = Agent(
    name="dialogue_planner",
    system_prompt="",
    tools=[],
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
)

_INTENTS = {
    "smalltalk", "quick_assessment", "report_hazard", "ask_regulation",
    "ask_solution", "correction", "create_task", "other",
}
_RELATIONSHIP_HINTS = {"add", "switch", ""}
_QUESTION_RE = re.compile(r"[^？?]*[？?]")


def _first_question(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = _QUESTION_RE.search(text)
    return match.group(0).strip() if match else text


_INTERROGATIVE_TOKENS = ("吗", "请", "方便", "什么", "哪", "怎么", "是否")


def _drop_question_sentences(value: str) -> str:
    """契约约束：既然 question 字段已经承载了追问，answer 就不能再夹问题。"""
    normalized = (value or "").replace("?", "？")
    kept = [
        sentence.strip()
        for sentence in re.split(r"[。！!？]", normalized)
        if sentence.strip()
        and not any(token in sentence for token in _INTERROGATIVE_TOKENS)
    ]
    return ("。".join(kept) + "。") if kept else ""


def _clean_evidence(raw_evidence, allowed_slots, clean_slots) -> list[dict]:
    """Constrain model-supplied evidence to real slots and one primary per slot."""
    out = []
    seen_slots = set()
    for item in raw_evidence or []:
        if not isinstance(item, dict):
            continue
        slot = str(item.get("slot") or "").strip()
        quote = str(item.get("quote") or "").strip()
        source_ref = str(item.get("source_ref") or "").strip()
        if slot not in allowed_slots or slot not in clean_slots:
            continue
        if slot in seen_slots or not quote or not source_ref:
            continue
        seen_slots.add(slot)
        out.append({"slot": slot, "quote": quote, "source_ref": source_ref})
    return out


def _issue_from_values(major_code, subcategory_code, slots, evidence=None) -> dict:
    pair = normalize_taxonomy(f"{major_code}/{subcategory_code}")
    if not pair:
        return {}
    major_code, subcategory_code = pair
    allowed = {slot.key: slot for slot in get_slot_schema(subcategory_code)}
    clean_slots = {}
    if isinstance(slots, dict):
        for key, value in slots.items():
            if key in allowed and value is not None and str(value).strip():
                clean_slots[key] = str(value).strip()
    clean_evidence = _clean_evidence(evidence, allowed, clean_slots)
    missing = [slot.key for slot in missing_decision_slots(subcategory_code, clean_slots)]
    report_missing = [slot.key for slot in missing_report_slots(subcategory_code, clean_slots)]
    return {
        "major_code": major_code,
        "major_label": MAJOR_LABELS.get(major_code, ""),
        "subcategory_code": subcategory_code,
        "risk_level": SUBCATEGORY_DEFAULT_RISK.get(subcategory_code, "medium"),
        "subcategory_label": SUBCATEGORY_LABELS.get(subcategory_code, ""),
        "slots": clean_slots,
        "missing": missing,
        "report_missing": report_missing,
        "evidence": clean_evidence,
    }


def _issues_from_legacy(categories, category_slots) -> list[dict]:
    issues = []
    for category in categories or []:
        pair = normalize_taxonomy(category)
        if not pair:
            continue
        major_code, subcategory_code = pair
        slots = {}
        if isinstance(category_slots, dict):
            slots = category_slots.get(category) or {}
        issue = _issue_from_values(major_code, subcategory_code, slots)
        if issue:
            issues.append(issue)
    return issues


def _issues_from_plan_items(raw_issues) -> list[dict]:
    issues = []
    seen = set()
    for item in raw_issues or []:
        if not isinstance(item, dict):
            continue
        issue = _issue_from_values(
            item.get("major_code"),
            item.get("subcategory_code"),
            item.get("slots"),
            item.get("evidence"),
        )
        key = (issue.get("major_code"), issue.get("subcategory_code"))
        if issue and key not in seen:
            seen.add(key)
            try:
                issue["confidence"] = min(1.0, max(0.0, float(item.get("confidence", 0.0))))
            except (TypeError, ValueError):
                issue["confidence"] = 0.0
            issues.append(issue)
    return issues


def parse_plan(raw: str) -> dict:
    """Parse and constrain a planner response to the supported contract."""
    text = (raw or "").strip()
    if not text:
        return {}
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        data = json.loads(text[start:end + 1])
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}

    issues = _issues_from_plan_items(data.get("issues"))
    if not issues:
        issues = _issues_from_legacy(data.get("categories"), data.get("category_slots"))
    categories = [issue["subcategory_code"] for issue in issues]
    category_slots = {issue["subcategory_code"]: issue["slots"] for issue in issues}

    intent = str(data.get("intent") or "other").strip()
    if intent not in _INTENTS:
        intent = "other"
    relationship_hint = str(data.get("relationship_hint") or "").strip()
    if relationship_hint not in _RELATIONSHIP_HINTS:
        relationship_hint = ""
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))

    needs_search = bool(data.get("needs_search"))
    if issues and not any(issue["missing"] for issue in issues) and intent != "smalltalk":
        needs_search = True
    selected_major_code = str(data.get("selected_major_code") or "").strip()
    if selected_major_code not in MAJOR_LABELS:
        selected_major_code = ""

    risk_level = str(data.get("risk_level") or "medium").strip().lower()
    if risk_level not in {"high", "medium", "low"}:
        risk_level = "medium"
    if issues:
        rank = {"low": 0, "medium": 1, "high": 2}
        risk_level = max(
            (issue.get("risk_level", "medium") for issue in issues),
            key=lambda value: rank.get(value, 1),
        )
    scope = str(data.get("scope") or "").strip()
    if scope not in {"hazard", "emergency", "smalltalk", "ambiguous", "out_of_scope"}:
        scope = ""
    try:
        scope_confidence = float(data.get("scope_confidence", 0.0))
    except (TypeError, ValueError):
        scope_confidence = 0.0
    scope_confidence = min(1.0, max(0.0, scope_confidence))

    question = _first_question(data.get("question"))
    question_target = str(data.get("question_target") or "").strip() if question else ""
    answer = str(data.get("answer") or "").strip()
    if question:
        answer = _drop_question_sentences(answer)

    premises_scope = str(data.get("premises_scope") or "").strip()
    if premises_scope not in {"public", "indoor", "indoor_risk"}:
        premises_scope = "public"

    perceived_major = str(data.get("perceived_major") or "").strip()
    if perceived_major not in MAJOR_LABELS:
        perceived_major = ""

    # 「当前焦点」：用户这句话指向的那一件事属于哪一个小类。
    # 与 perceived_major 同构 —— 都是"直接问模型这一句在说什么"，而不是从 issues 的
    # 位置去推（那条路会被历史拖拽，实测见 db/experiments/measure_history_bleed.py）。
    perceived_subcategory = str(data.get("perceived_subcategory") or "").strip()
    if perceived_subcategory not in ALL_SUBCATEGORY_CODES:
        perceived_subcategory = ""

    return {
        "ok": True,
        "perceived_major": perceived_major,
        "perceived_subcategory": perceived_subcategory,
        "premises_scope": premises_scope,
        "immediate_danger": bool(data.get("immediate_danger")),
        "intent": intent,
        "risk_level": risk_level,
        "scope": scope,
        "scope_confidence": scope_confidence,
        "selected_major_code": selected_major_code,
        "major_mismatch": bool(data.get("major_mismatch")),
        "issues": issues,
        "categories": categories,
        "category_slots": category_slots,
        "question": question,
        "question_target": question_target,
        "answer": answer,
        "needs_search": needs_search,
        "relationship_hint": relationship_hint,
        "confidence": confidence,
    }


def _planner_system_prompt(active_skill_codes=None) -> str:
    active_codes = [
        code for code in (active_skill_codes or [])
        if code in MAJOR_LABELS
    ]
    schema_lines = []
    for item in HAZARD_TAXONOMY:
        if active_codes and item["code"] not in active_codes:
            continue
        subcategories = "、".join(
            f"{label}({code})["
            + ",".join(slot.key for slot in get_slot_schema(code))
            + "]"
            for code, label in item["subcategories"]
        )
        schema_lines.append(f"- {item['label']}({item['code']}): {subcategories}")
    return (
        "你是城市安全隐患对话理解器。请结合完整对话和图片分析，理解用户当前真正想表达什么。\n"
        "只返回 JSON，不要输出 markdown 说明：\n"
        "{\"intent\":\"smalltalk|quick_assessment|report_hazard|ask_regulation|ask_solution|correction|create_task|other\","
        "\"selected_major_code\":\"\",\"major_mismatch\":false,\"risk_level\":\"high|medium|low\","
        "\"scope\":\"hazard|emergency|smalltalk|ambiguous|out_of_scope\",\"scope_confidence\":0.0,"
        "\"issues\":[{\"major_code\":\"\",\"subcategory_code\":\"\","
        "\"slots\":{\"槽key\":\"值\"},"
        "\"evidence\":[{\"slot\":\"槽key\",\"quote\":\"来源中的原样片段\",\"source_ref\":\"uN或vN\"}],"
        "\"confidence\":0.0}],"
        "\"perceived_major\":\"你认为这句话真正属于的大类\","
        "\"perceived_subcategory\":\"你认为用户这句话指向的那一件事属于哪一个小类\","
        "\"premises_scope\":\"public|indoor|indoor_risk\","
        "\"question\":\"最多一个自然问题\",\n"
        "\"question_target\":\"question 针对的那一个槽 key，没有 question 就留空\",\n"
        "\"answer\":\"面向用户的自然回答\",\n"
        "\"needs_search\":false,\"relationship_hint\":\"add|switch|\",\"confidence\":0.0,"
        "\"immediate_danger\":false}\n"
        "允许的两级分类：\n" + "\n".join(schema_lines) + "\n"
        "规则：\n"
        "- major_code 和 subcategory_code 必须来自上面给出的编码，不能自造。\n"
        "- 用户明确说“消防设施”时，必须归为 fire/fire_equipment_fault，不能归为 fire/fire_lane_blocked。\n"
        "- “消防设施故障”和“消防通道占用”是两个不同小类。\n"
        "- 前端预选大类只是提示；如果与用户表达不一致，返回真实 major_code 并令 major_mismatch=true。\n"
        "- risk_level 按小类默认风险：以 SUBCATEGORY_DEFAULT_RISK 为准；多隐患时取最高风险，不再按大类粗暴定级。\n"
        "- 环境与其他中的危化品违规存运为 high，有限空间作业风险为 high，垃圾堆积为 low。\n"
        "- scope 判定问题是否属于城市安全隐患助手范围：hazard=隐患描述/判断/法规/整改/上报；emergency=正在起火、有人被困、燃气泄漏、触电或坍塌；smalltalk=寒暄；ambiguous=无法判断；out_of_scope=明确无关话题。\n"
        "- 不要因为出现“消防”两个字就把“消防员招聘条件”之类问题判成 hazard；只有涉及现场安全隐患才是 hazard。\n"
        "- 设施类小类（交通设施损坏、路灯/线杆损坏、井盖缺失、配电设施故障、高空坠物（含外立面脱落））的判据是\n"
        "  那个物件在**公共空间**。只有道路上、路口、人行道、街边的交通设施（信号灯、护栏、交通标志、\n"
        "  交通标线）才算；商场、办公楼、小区门口、店内的指示牌、导视牌、宣传牌即使长得像交通标志，\n"
        "  也不算 —— 这种输入 scope 判 out_of_scope、issues 留空。\n"
        "- 只填用户明确说过的事实，不要编造。\n"
        "- 输入中的用户消息带有 [uN]、视觉摘要带有 [v1]、助手历史带有 [aN]。\n"
        "- 每个非空槽位都要在 evidence 中给出 quote 和 source_ref；quote 必须从对应来源原样复制，\n"
        "  source_ref 只能填写输入中实际存在的编号，不得自造。assistant 来源只用于理解，禁止作为证据。\n"
        "- 找不到可原样引用的证据时，不要填写 evidence，不要编造 quote；一个槽位最多一条主证据。\n"
        "- 只抽与当前这一条隐患相关的值；如果这句话讲的是别的隐患，\n"
        "  不要为了填满而把别的说法塞进槽位，留空即可。\n"
        "- premises_scope 只描述这些东西在哪，判据是「在谁的地方」：\n"
        "  共享空间一律 public —— 小区公共区域、楼道、电梯、外墙、户外立管、街道、\n"
        "  店铺门口、工地都算；\n"
        "  只有明确在用户自己家门内（家里、厨房、卧室、自家阳台、自家院子）才填 indoor / indoor_risk。\n"
        "  只要说的是小区/楼道/街道这类共享空间，就填 public，不要因为它被燃气影响到就填 indoor。\n"
        "  在用户自己家里、属于私有户内填 indoor；户内但可能危及公共安全（如户内燃气泄漏）填 indoor_risk。\n"
        "  它不影响分类，也不要因为它改变 issues。\n"
        "- perceived_major 必须说真话：无论前端有没有预选大类，都在这里给出你认为这句话\n"
        "  真正属于的大类编码。如果你为了配合前端预选大类而把 issues 写成那个大类，\n"
        "  这里仍然要写你真实的判断（两者不一致时同时令 major_mismatch=true）。\n"
        "- perceived_subcategory：用户「这句话指向的那一件事」属于哪一个小类，原样照抄上面的小类编码，\n"
        "  判断不出来就留空。它表示「当前焦点」，决定这条会话接下来跟哪一条隐患，所以要说真话：\n"
        "  · 用户说「那那个呢」「再往前那段呢」这类指代时，先用上下文把它解析成具体是哪一件事，再给小类；\n"
        "  · 但不要因为前几轮聊过某个隐患，就把它填在这里 —— 这里只写这句话要问的那一件。\n"
        "  前一件事和新一件事都可以留在 issues 里；这个字段只回答「焦点是哪一件」。\n"
        "- intent=correction 只在用户明确否定或修正他之前说的隐患时使用：\n"
        "  例如「不是占道，是消防通道」「你搞错了」「其实是消防设施」。\n"
        "  「另外」「还有」「旁边那个」是新增信息，不是 correction。\n"
        "- immediate_danger：如果对话描述的是正在发生的危险（已经起火、有人被困、正在漏气、\n"
        "  有人受伤或昏迷、结构正在塌落），返回 true；只是描述一个已经存在的隐患则返回 false。\n"
        "- 正常咨询最多问一个问题；已经回答过的信息不要再问。\n"
        "- question_target：给出 question 时，这里写它针对的那一个槽 key\n"
        "  （原样照抄上面给出的槽 key）；没有 question、或确实无从归属时留空。\n"
        "  它只用于核对「问的是不是缺的那个槽」，不会展示给用户。\n"
        "- question 只允许一个信息点，不要用并列问句同时询问多个信息；默认不要追问具体位置、楼层或出入口，除非用户明确准备创建任务。\n"
        "- 如果能够给出初步判断，先回答；追问只能作为补充，不要为了填槽连续追问。\n"
        "- 当 intent=report_hazard 且关键事实已经齐全时，needs_search 必须为 true，进入法规、案例和报告流程。\n"
        "- 用户明确要求法规、案例或详细报告时，needs_search 必须为 true。\n"
        "- 不要引用或编造具体法规和案例。\n"
        "- 所有已识别小类都可以进入建任务询问，不再限制四类。\n"
        "- 用户中途新增其他隐患时，把当前仍有效的问题一起放进 issues；relationship_hint 用 add。\n"
        "- 当前只展开已激活 Skill 的小类和槽位；如果用户明显描述的是未激活大类，\n"
        "  可依据「全部大类索引」返回 perceived_major/selected_major_code 并令 major_mismatch=true，\n"
        "  但不要编造未展开的小类或槽位。\n"
    )


def _planner_focus_context(missing, known_slots, subcategory_code: str) -> str:
    """把「已锁定隐患的已知事实 + 仍缺的决策级信息」交给规划器。

    G1 实测（问句命中目标槽仅 29.4%、35% 该问不问）的直接补救：以前模型得自己猜
    该问什么，猜出来的是位置/资源这类与槽位无关的问题。现在把缺的那个槽点名写进请求。
    """
    keys = [str(item).strip() for item in (missing or []) if str(item).strip()]
    filled = {k: v for k, v in (known_slots or {}).items() if str(v or "").strip()}
    hints = {slot.key: slot.question for slot in get_slot_schema(subcategory_code)}
    label = SUBCATEGORY_LABELS.get(subcategory_code, "")
    if label:
        label = f"{label}({subcategory_code})"
    lines = [f"【当前焦点隐患的槽位状态】{label or subcategory_code or '（未锁定）'}"]
    lines.append("已知事实：" + ("；".join(f"{k}={v}" for k, v in filled.items()) or "（暂无）"))
    if keys:
        described = "、".join(
            f"{k}（想确认的是：{hints[k]}）" if hints.get(k) else k for k in keys
        )
        lines.append("仍缺的决策级信息：" + described)
        lines.append(
            "契约：question 必须针对上面「仍缺的决策级信息」里的其中一个来问，"
            "并且用你自己的话，不要照抄括号里的字；确实无需追问时 question 留空。"
        )
    else:
        lines.append("仍缺的决策级信息：（无）")
        lines.append("契约：关键信息已齐，question 留空，不要为了填表再追问。")
    return "\n".join(lines)


def _message_role_and_content(message):
    """Normalize LangChain messages and dict messages to planner roles."""
    if isinstance(message, dict):
        role = message.get("role") or message.get("type") or ""
        content = message.get("content")
    else:
        role = getattr(message, "type", "") or getattr(message, "role", "")
        content = getattr(message, "content", message)
    role = str(role or "").strip().lower()
    if role == "human":
        role = "user"
    elif role == "ai":
        role = "assistant"
    return role, str(content or "")


def iter_source_messages(messages):
    """Yield (source_ref, planner_role, content) with stable backend-owned refs."""
    user_index = assistant_index = 0
    for message in messages or []:
        role, content = _message_role_and_content(message)
        ref = ""
        if role == "user":
            user_index += 1
            ref = f"u{user_index}"
        elif role == "assistant":
            assistant_index += 1
            ref = f"a{assistant_index}"
        yield ref, role, content


def build_source_map(messages, vision_summary: str = "") -> dict[str, str]:
    """Build the only source namespace the model may cite.

    User and vision sources can ground facts. Assistant refs are exposed so they
    can be recognized and explicitly rejected by deterministic verification.
    """
    source_map = {}
    for ref, _role, content in iter_source_messages(messages):
        if ref and content:
            source_map[ref] = content
    content = str(vision_summary or "").strip()
    if content:
        source_map["v1"] = content
    return source_map


def build_planner_messages(messages: list, vision_summary: str = "",
                           selected_major_code: str = "", missing=None,
                           known_slots=None, subcategory_code: str = "",
                           skill_bodies: dict[str, str] | None = None,
                           active_skill_codes: list[str] | None = None) -> list[dict]:
    """Build a planner request from recent dialogue plus vision context.

    missing / known_slots / subcategory_code 描述「当前锁定隐患还缺哪些决策级槽」，
    由调用方（图节点）从上一轮状态里算出来 —— 只有本会话已锁定小类时才有意义。
    """
    out = [{"role": "system", "content": _planner_system_prompt(active_skill_codes)}]
    if active_skill_codes:
        major_index = "；".join(
            f"{item['label']}({item['code']})" for item in HAZARD_TAXONOMY
        )
        out.append({"role": "system", "content": f"【全部大类索引】{major_index}"})
    selected_major_code = (selected_major_code or "").strip()
    if selected_major_code in MAJOR_LABELS:
        out.append({
            "role": "system",
            "content": f"前端预选大类：{MAJOR_LABELS[selected_major_code]}({selected_major_code})",
        })
    if vision_summary:
        out.append({"role": "system", "content": f"[v1] {vision_summary}"})
    if (subcategory_code or "").strip() or missing:
        out.append({
            "role": "system",
            "content": _planner_focus_context(missing, known_slots, subcategory_code),
        })
    for code, body in (skill_bodies or {}).items():
        if str(body or "").strip():
            out.append({
                "role": "system",
                "content": f"【Skill: {code}】\n{str(body).strip()}",
            })
    visible = list(iter_source_messages(messages))[-max(2, PLANNER_HISTORY_MESSAGES):]
    for ref, role, content in visible:
        if role in {"user", "assistant", "system"} and content:
            if ref:
                content = f"[{ref}] {content}"
            out.append({"role": role, "content": content})
    return out


def understand(messages: list, vision_summary: str = "",
               selected_major_code: str = "", missing=None,
               known_slots=None, subcategory_code: str = "",
               skill_bodies: dict[str, str] | None = None,
               active_skill_codes: list[str] | None = None) -> dict:
    """Return a validated dialogue plan, or an empty plan on planner failure."""
    try:
        response = _planner_llm._call_llm(
            build_planner_messages(
                messages, vision_summary, selected_major_code,
                missing=missing, known_slots=known_slots,
                subcategory_code=subcategory_code,
                skill_bodies=skill_bodies,
                active_skill_codes=active_skill_codes,
            ),
            cancellation=None,
        )
        return parse_plan((response or {}).get("content") or "")
    except Exception:
        return {}


# ====== 追问环节（第 1 轮问句的唯一来源）======
# 为什么不能"再跑一次完整 understand"：
#   1) 成本 —— 第 1 轮会变成两次全量调用，而第 1 轮正是等待感最强的一轮；
#   2) 两次分类可能不一致 —— 第二遍会再判一次小类，锁会乱（一条会话一个活跃隐患是定死的）；
#   3) 它会变成第二个事实写入者 —— 项目不变式是「understand 是唯一的事实写入者」，
#      两处都写 locked_major/issues/category_slots 就等于把「两套真相」换个形式搬回来。
# 所以这里只做一件事：读 missing + 已知事实 + 用户原话，产出一句问句。

_SLOT_QUESTION_SYSTEM = (
    "你是城市安全隐患助手的「追问」环节。只做一件事：针对下面列出的"
    "「仍缺的决策级信息」，用你自己的话问出**一个**问题。\n"
    "- target_slot 必须从「仍缺的决策级信息」里挑一个 key，原样照抄，不要改写、不要翻译。\n"
    "- question 只问一个信息点，口语自然；不要照抄括号里的字；不要用并列问句。\n"
    "- 禁止问具体位置、楼层、出入口、联系方式；禁止问要不要建任务或出报告。\n"
    "只输出一个 JSON 对象，不要解释、不要 Markdown 代码块："
    '{"target_slot": "<key>", "question": "<一句中文问句>"}'
)


def build_slot_question_messages(missing, known_slots, subcategory_code: str,
                                 user_text: str = "") -> list:
    """追问小调用的请求体：只带这条隐患的槽位状态，不带整段对话。"""
    keys = [str(item).strip() for item in (missing or []) if str(item).strip()]
    filled = {k: v for k, v in (known_slots or {}).items() if str(v or "").strip()}
    hints = {slot.key: slot.question for slot in get_slot_schema(subcategory_code)}
    label = SUBCATEGORY_LABELS.get(subcategory_code, "")
    if label:
        label = "%s(%s)" % (label, subcategory_code)
    described = "\n".join(
        "- %s（想确认的是：%s）" % (key, hints[key]) if hints.get(key) else "- %s" % key
        for key in keys
    )
    body = [
        "当前隐患类别：" + (label or subcategory_code or "（未锁定）"),
        "已知事实：" + ("；".join("%s=%s" % (k, v) for k, v in filled.items()) or "（暂无）"),
        "仍缺的决策级信息：",
        described or "（无）",
        "用户原话：" + (str(user_text or "").strip() or "（无）"),
    ]
    return [
        {"role": "system", "content": _SLOT_QUESTION_SYSTEM},
        {"role": "user", "content": "\n".join(body)},
    ]


def parse_slot_question(raw: str) -> dict:
    """从模型输出里取 {question, target_slot}；取不到就返回空，不抛。"""
    text = str(raw or "").strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "question": str(data.get("question") or "").strip(),
        "target_slot": str(data.get("target_slot") or "").strip(),
    }


def slot_question_targets_missing(target_slot, missing_keys) -> bool:
    """纯函数：问句自报的目标槽是否真的在 A 类缺失里。

    靠模型自报 target_slot，而不是去猜问句文本 —— 文本是自由措辞，猜不准；
    自报字段是结构化契约，可判、可测。
    """
    target = str(target_slot or "").strip()
    if not target:
        return False
    return target in {str(key).strip() for key in (missing_keys or [])}


def schema_slot_for_missing(missing_keys, subcategory_code: str) -> str:
    """第三级兜底命中的那一个槽 key（按 schema 书写顺序取第一个缺失的）。

    与 schema_question_for_missing 同一遍历顺序 —— 观测侧靠它把「固定串」
    归属回具体的槽，否则「问句指向哪个槽」就会被记成不可判。
    """
    keys = {str(key).strip() for key in (missing_keys or [])}
    for slot in get_slot_schema(subcategory_code):
        if slot.key in keys:
            return slot.key
    return ""


def schema_question_for_missing(missing_keys, subcategory_code: str) -> str:
    """第三级兜底：按 schema 书写顺序取第一个缺失 A 类槽自带的问句。"""
    key = schema_slot_for_missing(missing_keys, subcategory_code)
    for slot in get_slot_schema(subcategory_code):
        if slot.key == key:
            return slot.question
    return ""


def resolve_slot_question(candidate_question, candidate_target, missing_keys,
                          existing_question, fallback_question):
    """三级降级：新节点（校验通过）→ understand 自带问句 → 槽位 schema 固定问句。

    返回 (question, source)。source 供观测与测试，取值为
    ask_slot_question / understand / slot_schema / none。
    """
    candidate = str(candidate_question or "").strip()
    if candidate and slot_question_targets_missing(candidate_target, missing_keys):
        return candidate, "ask_slot_question"
    existing = str(existing_question or "").strip()
    if existing:
        return existing, "understand"
    fallback = str(fallback_question or "").strip()
    if fallback:
        return fallback, "slot_schema"
    return "", "none"


_question_llm = Agent(
    name="ask_slot_question",
    system_prompt=_SLOT_QUESTION_SYSTEM,
    tools=[],
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
    slot="small",
)


def ask_slot_question(missing=None, known_slots=None, subcategory_code: str = "",
                      user_text: str = "") -> dict:
    """小调用：只产出 {question, target_slot}。失败返回 {}，由调用方降级。"""
    try:
        response = _question_llm._call_llm(
            build_slot_question_messages(missing, known_slots, subcategory_code, user_text),
            cancellation=None,
        )
        return parse_slot_question((response or {}).get("content") or "")
    except Exception:
        return {}
