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

    if complete and state.get("asked_question_last_turn"):
        return _decision(
            "report_full",
            reason="user answered the clarification and facts are complete",
            needs_search=True,
            report_mode="full",
        )

    if intent in REPORT_INTENTS and complete and not incomplete:
        return _decision(
            "report_full",
            reason="report intent with complete facts",
            needs_search=True,
            report_mode="full",
        )

    if (
        complete
        and not incomplete
        and risk in {"high", "medium"}
        and not (intent == "quick_assessment" and _is_casual_judgment(user_text))
    ):
        return _decision(
            "report_full",
            reason="complete hazard facts should produce a full report",
            needs_search=True,
            report_mode="full",
        )

    if intent == "quick_assessment":
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

    if answer:
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
        return _decision(
            "report_preliminary",
            reason="issues exist but facts are incomplete",
            needs_search=True,
            report_mode="preliminary",
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
