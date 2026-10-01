"""LangGraph 助手状态定义。"""
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

MAX_THREAD_MESSAGES = 20


def append_messages(left, right) -> list:
    """messages 的 reducer：按 id 追加/覆盖，并保留最近 MAX_THREAD_MESSAGES 条。

    add_messages 的覆盖语义让重放同一批历史是幂等的；截断则避免线程无限增长。
    """
    return add_messages(left or [], right or [])[-MAX_THREAD_MESSAGES:]


def merge_category_results(left, right) -> dict:
    """并发检索分支的 reducer：按类别浅合并；值为 None 表示清空该类别。"""
    merged = {key: dict(value) for key, value in (left or {}).items()}
    for category, value in (right or {}).items():
        if value is None:
            merged[category] = {}
        else:
            merged.setdefault(category, {})
            merged[category].update(value or {})
    return merged


class AssistantState(TypedDict, total=False):
    session_id: str                     # checkpointer 的 thread_id
    user_id: int
    messages: Annotated[list, append_messages]
    # 一条会话一个活跃隐患：大类锁定后只由前端改，小类只由用户纠正改
    locked_major: str
    locked_subcategory: str
    suggested_major_code: str          # 越界时模型认为的真实大类（给前端渲染"改报"入口）
    immediate_danger: bool             # 模型自己判定的即时危险（可观测、可量化）
    premises_scope: str                # public | indoor | indoor_risk（户内/公共边界）
    # 隐患事实（understand 是唯一写入者）
    categories: list[str]               # 有序、去重的 subcategory code
    category_slots: dict[str, dict]     # {subcategory_code: {slot_key: value}}
    category_results: Annotated[dict, merge_category_results]  # {code: {regulation, case}}
    missing: list[str]                  # 全局并集，形如 "{code}_{slot_key}"（只含 A 类）
    question_missing: list[str]         # missing 非空但这轮没问出问题（不静默）
    question_missing_reason: str        # danger_veto | cautious | report | planner_no_question
    question_source: str                # 本轮问句出处：ask_slot_question | understand | slot_schema | ""
    question_dropped: str               # A 类缺失为空却拿到问句 → 丢弃原因（不静默）
    issues: list[dict]                  # canonical issue list from the planner
    facts_snapshot: dict                # 本轮**之前**的事实快照（begin_turn 写）；
                                        # scope_guard 判越界时按它整体回滚，见 spec 决策 7
    vision_summary: str
    # 本轮语义与决策
    dialogue_plan: dict                 # structured semantic plan for this turn
    intent: str                         # planner intent label
    clarification_question: str         # at most one planned question
    question_target: str                # 本轮问句针对的槽 key（写问句的节点自报；供核对与观测）
    next_action: str                    # deterministic policy action
    dialogue_mode: str                  # 产出模式：plain | preliminary | report（决策 10 / M1，跨轮继承）
    report_mode: str                    # "none" | "preliminary" | "full"
    policy_reason: str                  # explainable policy reason
    optional_question: bool             # question is optional, not required
    asked_question_last_turn: bool      # prev turn ended by asking the user a question
    selected_major_code: str            # frontend major-category hint
    major_mismatch: bool                # planner corrected the frontend hint
    # 建任务确认（interrupt 闸门）
    offer_task: bool                    # report decided the task invitation is allowed
    task_offered: bool                  # per-turn: the gate already asked
    task_phase: str                     # "confirm" | "address"
    address_text: str                   # address captured by the gate
    # 不确定性（见 core/uncertainty.py）
    uncertainty_level: str              # "ok" | "cautious" | "fallback"
    danger_veto: bool                   # 正在发生的危险：禁止追问
    ungrounded_slots: list[str]         # 槽位值对不上原文（疑似编造）
    grounding_ratio: float
    uncertainty_signals: list[str]      # 可解释的信号串
    # guidance_emitted:「这次危险事件的安全文本已交给 emergency_guidance」。
    # 图内已无消费者（危险输入一律走 emergency_guidance 节点）；保留是因为 report() /
    # answer_reply() 被直接调用的非图路径仍靠它去重（见 prepend_guidance / _reply_prefix）。
    guidance_emitted: bool
    # 范围护栏
    direct_mode: str                    # "smalltalk" | "emergency_reply" | scope modes | ""
    scope: str                          # hazard | emergency | smalltalk | ambiguous | out_of_scope
    scope_reason: str                   # deterministic scope explanation
    scope_response: str                 # fixed scope-guard response text
    # draft_report: 本轮交付给用户的报告正文（与 messages 同源写入，见 _deliver_report）。
    # 读者：既有测试与 db/measure_* 测量脚本 —— 用「本轮交付正文」核对 "".join(chunks) == draft。
    draft_report: str
