"""LangGraph 助手状态定义。"""
from typing import TypedDict

class AssistantState(TypedDict, total=False):
    session_id: str                     # checkpointer 的 thread_id
    messages: list
    # 多隐患字段
    categories: list[str]               # 有序、去重
    active_category: str                # 当前正在补哪张表
    category_index: int                 # 指向 categories 下标
    category_slots: dict[str, dict]     # {类别: {slot_key: value}}
    category_results: dict[str, dict]   # {类别: {regulation, case}}
    missing: list[str]                  # 全局并集，形如 "{cat}_{key}"
    relationship: str                   # "add"|"switch"|""
    clarify_count: int
    clarify_stopped: bool
    vision_summary: str
    regulation_results: str
    case_results: str
    draft_report: str
    grade_feedback: str
    attempts: int
    route_decision: str
