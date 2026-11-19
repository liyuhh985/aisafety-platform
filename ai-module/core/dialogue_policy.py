"""Deterministic next-best-action policy for the safety dialogue."""
from core.hazard_taxonomy import SUBCATEGORY_TO_MAJOR
from core.slot_schemas import get_slot_schema

HIGH_RISK_MAJORS = {"fire", "building", "utility"}
STOP_PHRASES = (
    "别问", "不用问", "直接说", "直接给", "就这些",
    "别兜", "直接出报告", "直接给结论",
)
REPORT_PHRASES = (
    "查法规", "查案例", "法规和案例", "出报告", "生成报告",
    "详细报告", "正式报告", "帮我查",
)
REPORT_INTENTS = {"report_hazard", "ask_regulation", "ask_solution"}
CASUAL_JUDGMENT_PHRASES = (
    "算", "是不是", "属于", "有隐患吗", "危险吗", "安全吗", "要紧吗", "严重吗",
)


def _issue_major(issue: dict) -> str:
    major = (issue or {}).get("major_code") or ""
    if major:
        return major
    return SUBCATEGORY_TO_MAJOR.get((issue or {}).get("subcategory_code"), "")


def _complete_issues(plan: dict) -> list[dict]:
    return [
        issue for issue in (plan.get("issues") or [])
        if not (issue or {}).get("missing")
    ]


def _incomplete_issues(plan: dict) -> list[dict]:
    return [
        issue for issue in (plan.get("issues") or [])
        if (issue or {}).get("missing")
    ]


def _risk_level(plan: dict, issues: list[dict]) -> str:
    if any(_issue_major(issue) in HIGH_RISK_MAJORS for issue in issues):
        return "high"
    risk = str(plan.get("risk_level") or "medium").strip().lower()
    return risk if risk in {"high", "medium", "low"} else "medium"


def _question_for_missing(plan: dict) -> str:
    question = str(plan.get("question") or "").strip()
    if question:
        return question
    for issue in _incomplete_issues(plan):
        missing = set(issue.get("missing") or [])
        for slot in get_slot_schema(issue.get("subcategory_code")):
            if slot.key in missing:
                return slot.question
    return ""


# M1（闭环）：产物由**代码可判的判据**定，不由模型这一轮的 intent 定。
# 理由与实测见 私有历史设计文档 §3：
# 同一句话跑 10 次，模型给出 4 种 intent（report_hazard 6 / quick_assessment 2 / other 1 / 空 1），
# 而 intent 是决定进哪个节点的唯一输入 —— 产物就跟着飘。
MODE_PLAIN = "plain"
MODE_PRELIMINARY = "preliminary"
MODE_REPORT = "report"
MODES = (MODE_PLAIN, MODE_PRELIMINARY, MODE_REPORT)


_MODE_OF_ACTION = {
    "answer_now": MODE_PLAIN,
    "answer_with_optional_question": MODE_PLAIN,
    # 追问分两种档：
    #   answer_with_optional_question = 纯回答档顺带问一句（"是不是隐患" → 先给判断）
    #   ask_critical_question          = 关键信息缺失、必须先问 → 属「初步判断 + 追问」档
    # 后者能被追问补全后升级成完整报告；前者不能（决策 5 的天花板）。
    "ask_critical_question": MODE_PRELIMINARY,
    "report_preliminary": MODE_PRELIMINARY,
    "report_full": MODE_REPORT,
}


def mode_of_action(action: str, current: str = "") -> str:
    """算这一轮的产物模式。**危险与兜底不改模式** —— 返回原值。

    危险是临时的（一场火不该把会话永久变成"应急模式"），兜底是异常路径，
    两者都不该覆盖用户真正的对话意图。
    """
    return _MODE_OF_ACTION.get(str(action or ""), str(current or ""))


def wants_report(text: str) -> bool:
    """用户这一句里有没有明确的「要报告 / 要法规」信号。代码可判，不看模型。

    这是**从纯回答档升级到报告档的唯一通道**（见 decide_next_action 里的模式继承）。
    """
    return any(phrase in (text or "") for phrase in REPORT_PHRASES)


def _is_casual_judgment(text: str) -> bool:
    value = (text or "").strip()
    return any(phrase in value for phrase in CASUAL_JUDGMENT_PHRASES)


def _decision(action: str, *, reason: str = "", question: str = "",
              optional_question: bool = False, needs_search: bool = False,
              report_mode: str = "none") -> dict:
    return {
        "action": action,
        "reason": reason,
        "question": question,
        "optional_question": optional_question,
        "needs_search": needs_search,
        "report_mode": report_mode,
    }


def _decide_next_action_inner(plan: dict, state: dict) -> dict:
    """Choose the next best dialogue action without another model call."""
    if not plan or not plan.get("ok"):
        return _decision("fallback", reason="no valid dialogue plan")

    user_text = str(state.get("user_text") or "").strip()
    issues = list(plan.get("issues") or [])
    complete = _complete_issues(plan)
    incomplete = _incomplete_issues(plan)
    risk = _risk_level(plan, issues)
    intent = str(plan.get("intent") or "other")
    answer = str(plan.get("answer") or "").strip()

    if intent == "smalltalk":
        return _decision("answer_now", reason="small talk")

    if intent == "create_task" and complete and not incomplete:
        return _decision(
            "report_full",
            reason="user explicitly asked to create a task and facts are complete",
            needs_search=True,
            report_mode="full",
        )

    if any(phrase in user_text for phrase in STOP_PHRASES):
        if issues:
            return _decision(
                "report_preliminary",
                reason="user explicitly refused further questions",
                needs_search=True,
                report_mode="preliminary",
            )
        return _decision("answer_now", reason="user refused questions and no issue is defined")

    explicit_report = any(phrase in user_text for phrase in REPORT_PHRASES)
    if explicit_report:
        mode = "full" if complete and not incomplete else "preliminary"
        return _decision(
            "report_full" if mode == "full" else "report_preliminary",
            reason="user explicitly requested regulations/report",
            needs_search=True,
            report_mode=mode,
        )

    # 「正在回答上一轮的追问」优先于模式继承：
    # 用户只回了一个槽位值时，不能被上一轮的 plain 模式粘住，
    # 否则「追问 → 回答」链路永远进不了报告。
    if state.get("asked_question_last_turn") and issues:
        if complete and not incomplete:
            return _decision(
                "report_full",
                reason="user answered the clarification; facts are complete",
                needs_search=True,
                report_mode="full",
            )
        question = _question_for_missing(plan)
        if question:
            return _decision(
                "ask_critical_question",
                reason="user answered one slot; next critical fact is still missing",
                question=question,
            )
        return _decision(
            "report_preliminary",
            reason="user answered the clarification but facts are still incomplete",
            needs_search=True,
            report_mode="preliminary",
        )

    # M1：明确信号都用完之后，才轮到「沿用上一轮模式」。
    # 它同时干两件事：
    #   ① 解省略句 —— 用户说「那 X 呢」时单看这一句判不出要什么产物，沿用上一轮；
    #   ② 当「纯回答档的天花板」—— 想升级成报告只有一条路：用户明说要报告（上面的分支）。
    prev_mode = str(state.get("dialogue_mode") or "")
    if prev_mode in MODES:
        if prev_mode == MODE_PLAIN:
            return _decision("answer_now", reason="inherit plain mode")
        if prev_mode == MODE_REPORT and complete and not incomplete:
            return _decision(
                "report_full", reason="inherit report mode",
                needs_search=True, report_mode="full",
            )
        if prev_mode == MODE_PRELIMINARY and incomplete:
            return _decision(
                "report_preliminary", reason="inherit preliminary mode",
                needs_search=True, report_mode="preliminary",
            )


    if (
        complete
        and not incomplete
        and risk in {"high", "medium"}
        and not _is_casual_judgment(user_text)
    ):
        return _decision(
            "report_full",
            reason="complete hazard facts should produce a full report",
            needs_search=True,
            report_mode="full",
        )

    if _is_casual_judgment(user_text):
        question = str(plan.get("question") or "").strip()
        if answer:
            if question:
                return _decision(
                    "answer_with_optional_question",
                    reason="quick assessment can answer first",
                    question=question,
                    optional_question=True,
                )
            return _decision("answer_now", reason="quick assessment")
        if question:
            return _decision(
                "answer_with_optional_question",
                reason="quick assessment has only an optional follow-up",
                question=question,
                optional_question=True,
            )
        return _decision("answer_now", reason="quick assessment without extra facts")

    if complete and incomplete:
        return _decision(
            "report_preliminary",
            reason="some issues are complete while others still need facts",
            needs_search=True,
            report_mode="preliminary",
        )

    if incomplete and risk == "high":
        question = _question_for_missing(plan)
        if question:
            return _decision(
                "ask_critical_question",
                reason="high-risk issue is missing a decision-critical fact",
                question=question,
            )

    # 描述隐患（report_hazard / create_task）时，规划器顺手写的一段回答
    # 不能截断报告链路：有缺口就继续问，缺口问不出来就出初步报告。
    if answer and not (issues and intent in {"report_hazard", "create_task"}):
        question = str(plan.get("question") or "").strip()
        if question and incomplete:
            return _decision(
                "answer_with_optional_question",
                reason="answer is useful and remaining fact is optional",
                question=question,
                optional_question=True,
            )
        return _decision("answer_now", reason="planner supplied a usable answer")

    question = _question_for_missing(plan)
    if question:
        return _decision(
            "ask_critical_question",
            reason="one critical fact is still needed",
            question=question,
        )

    if issues:
        if incomplete:
            return _decision(
                "report_preliminary",
                reason="issues exist but facts are incomplete",
                needs_search=True, report_mode="preliminary",
            )
        # 用户描述了隐患、且事实齐全 → 完整报告。这条以前靠 intent in REPORT_INTENTS，
        # 现在靠代码：有 issues + 无缺口，就够了。
        return _decision(
            "report_full",
            reason="complete hazard facts",
            needs_search=True, report_mode="full",
        )

    return _decision("answer_now", reason="no hazard issue was resolved")


def _signals_suffix(state: dict) -> str:
    signals = ",".join(state.get("uncertainty_signals") or [])[:140]
    return (" | 信号禁止追问：" + signals) if signals else " | 信号禁止追问"


def _apply_no_question_guard(decision: dict, plan: dict, state: dict) -> dict:
    """把"不许追问"作为后置约束统一施加，避免在每个分支里各写一遍。

    触发条件：正在发生的危险（danger_veto），或事实存疑（uncertainty_level=cautious）。
    """
    no_questions = bool(state.get("danger_veto")) or \
        state.get("uncertainty_level") == "cautious"
    if not no_questions:
        return decision
    action = decision.get("action")
    reason = (decision.get("reason") or "") + _signals_suffix(state)
    has_issues = bool(plan.get("issues"))
    if action == "ask_critical_question":
        return _decision(
            "report_preliminary" if has_issues else "answer_now",
            reason=reason,
            needs_search=has_issues,
            report_mode="preliminary" if has_issues else "none",
        )
    if action == "answer_with_optional_question":
        return _decision(
            "answer_now", reason=reason, needs_search=bool(decision.get("needs_search")),
        )
    if decision.get("report_mode") == "full":
        return _decision(
            "report_preliminary", reason=reason, needs_search=True,
            report_mode="preliminary",
        )
    return decision


def decide_next_action(plan: dict, state: dict) -> dict:
    """纯函数：由规划器结果与不确定性信号共同决定下一步动作。"""
    return _apply_no_question_guard(_decide_next_action_inner(plan, state), plan, state)
