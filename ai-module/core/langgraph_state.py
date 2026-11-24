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
    # 一条会话最多 MAX_ACTIVE_HAZARDS 条活跃隐患，且都落在 locked_majors 里：
    # 大类集合锁定后只由前端改（模型只能建议），小类只由用户纠正改；
    # 集合之外的条目只发通知、不记录
    locked_major: str                   # 集合的第一项（兼容 SSE / 前端状态条）
    locked_majors: list[str]            # 锁定的大类集合：前端多选或首轮模型判定，之后只由前端改
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
    question_source: str                # 本轮问句出处：ask_slot_question | understand
                                        # | slot_schema | multi_hazard（多条并列，代码拼）| ""
    question_dropped: str               # A 类缺失为空却拿到问句 → 丢弃原因（不静默）
    issues: list[dict]                  # 本轮活动隐患：焦点打头，同大类，上限 MAX_ACTIVE_HAZARDS
    facts_snapshot: dict                # 本轮**之前**的事实快照（begin_turn 写）；
                                        # scope_guard 判越界时按它整体回滚，见 spec 决策 7
    vision_summary: str
    image_url: str                    # 本轮上传图片的受控 URL
    image_file_id: int               # 本轮上传图片的 fileId（Java/MQ 用于附加）
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
    selected_major_code: str            # frontend major-category hint（可逗号分隔多个 code）
    selected_major_codes: list[str]     # 同上，列表形态；空则看 selected_major_code
    major_mismatch: bool                # planner corrected the frontend hint
    active_skills: list[str]            # 当前激活的 canonical major Skills
    skill_route_source: str             # locked | frontend | vision | keyword | llm | fallback | negative
    skill_route_confidence: float
    skill_versions: dict[str, str]      # 仅版本元数据；正文不得进入 checkpoint
    # 建任务确认（interrupt 闸门）
    offer_task: bool                    # report decided the task invitation is allowed
    task_draft: dict                     # report 阶段并行生成、确认时直接提交的建单草稿
    task_offered: bool                  # per-turn: the gate already asked
    task_phase: str                     # "confirm" | "address"
    address_text: str                   # address captured by the gate
    request_id: str                     # confirmation-level idempotency key, allocated before interrupt
    # 用户在图上选点得到的坐标，来自确认卡片的 interrupt_reply；有值时跳过地理编码
    picked_longitude: float             # float 或 None，默认 None
    picked_latitude: float              # float 或 None，默认 None
    # 不确定性（见 core/uncertainty.py）
    uncertainty_level: str              # "ok" | "cautious" | "fallback"
    danger_veto: bool                   # 正在发生的危险：禁止追问
    ungrounded_slots: list[str]         # 槽位值对不上原文（疑似编造）
    grounding_ratio: float
    uncertainty_signals: list[str]      # 可解释的信号串
    slot_evidence_audit: dict           # 内部证据审计；不得进入 SSE / 报告
    legacy_ungrounded_slots: list[str]  # 证据模式切换前的旧结果
    legacy_uncertainty_level: str
    legacy_grounding_ratio: float
    evidence_ungrounded_slots: list[str]
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
