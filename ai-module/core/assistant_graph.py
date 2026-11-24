"""LangGraph 助手：语义理解 + 并行检索 + 报告。

流程：begin_turn -> understand（唯一的事实与决策写入者）-> scope_guard -> route
      -> direct_reply（回答/最多一个追问）
      -> search（Send 并行扇出）-> retrieve -> report
route 只把 understand 定好的 next_action 映射成 Command(goto=...)；
每个隐患的法规与案例检索并行执行，最后由 reducer 汇聚。
汇聚后先经 evaluate_retrieval 自评：不达标就让模型改写检索词（rewrite_query）
回到 search 重查一次（上界 1 次），达标才进 report。
"""
import asyncio
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Annotated, Generator, Literal

from langgraph.graph import StateGraph, END
from langgraph.config import get_stream_writer
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, Send, interrupt
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from config import (
    MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL,
    CHECKPOINT_BACKEND, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_DB,
    REDIS_TIMEOUT_SECONDS, SLOT_EVIDENCE_MODE,
)
from core.agent import Agent
from core.langgraph_state import AssistantState, merge_category_results
from core.cancellation import CancellationToken, StreamCancelled
from core.dialogue_understanding import (
    ask_slot_question as _slot_question_llm,
    resolve_slot_question,
    schema_question_for_missing,
    schema_slot_for_missing,
    slot_question_targets_missing,
    understand as _understand_plan,
)
from core.dialogue_policy import decide_next_action, mode_of_action
from core.hazard_taxonomy import (
    ALL_SUBCATEGORY_CODES,
    HAZARD_TAXONOMY,
    MAJOR_LABELS,
    MAJOR_LABEL_TO_CODE,
    SUBCATEGORY_LABELS,
    SUBCATEGORY_TO_MAJOR,
    format_hazard_type,
    normalize_taxonomy,
)
from core.skill_registry import get_skill_registry
from core.skill_router import (
    _skill_route_llm,
    route_skills as _route_skills,
)
from core.scope_policy import (
    AMBIGUOUS_RESPONSE,
    OUT_OF_SCOPE_RESPONSE,
    covers_emergency_points,
    decide_scope,
    emergency_guidance_fallback,
    emergency_guidance_lead,
    emergency_guidance_points,
    emergency_guidance_type,
)
from core.case_relevance import NO_MATCH, filter_by_major
from core.slot_schemas import (
    get_slot_schema,
    missing_decision_slots,
    missing_report_slots,
)
from core.stream_guard import QUESTION_DROP, guard_stream, question_limiter
from core.uncertainty import active_danger_term, assess, echo_slots
from core.semantic_verifier import verify_weak_slots
from tools.assistant_tools import ASSISTANT_TOOLS
from tools.hazard_create_queue import new_request_id
from tools.hazard_submit import build_task_draft

# report 用不带 tools 的轻量 Agent（流式生成纯文本报告，避免 tools 导致 400）
_report_llm = Agent(
    name="report",
    system_prompt="你是城市安全隐患报告撰写助手。只输出简洁的 Markdown 文本报告；禁止输出任何工具调用、<tool_call>、XML/HTML 标签或代码块；必须基于给定检索结果，不编造，没有就写'库内暂未检索到'。",
    tools=[],
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
)
_TOOL_MAP = {t.name: t for t in ASSISTANT_TOOLS}
_skill_registry = get_skill_registry(
    Path(__file__).parents[1] / "skills",
    {tool.name for tool in ASSISTANT_TOOLS},
)
_TASK_DRAFT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="task-draft")

logger = logging.getLogger(__name__)
_RESULT_FIELD = {"search_regulation": "regulation", "search_cases": "case"}

# 危险场景的产物动作（决策 1 + 决策 4）。它和 report_* / answer_* 一样，
# 是 understand 定好的 next_action，route 只负责映射 —— 决策权仍然只有一处。
EMERGENCY_ACTION = "emergency_guidance"

STATUS_TEXT = {
    "begin_turn": "正在准备本轮对话...",
    "skill_route": "正在判断隐患领域...",
    "understand": "正在理解您的问题...",
    "scope_guard": "正在判断问题范围...",
    "route": "正在分析您的咨询...",
    "search": "正在准备检索...",
    "retrieve": "正在检索「{category}」的法规与案例...",
    "evaluate_retrieval": "正在核对检索结果...",
    "rewrite_query": "正在换个检索词再试一次...",
    "report": "正在生成结论...",
    "after_report": "正在整理结论...",
    "task_gate": "正在等待你的确认...",
    "submit_task": "正在创建隐患任务...",
    "close_task": "正在结束本轮...",
    "boundary_reply": "正在整理回复...",
    "smalltalk_reply": "正在整理回复...",
    "answer_reply": "正在整理回复...",
    "fallback_reply": "正在生成初步判断...",
    "emergency_guidance": "正在给出安全处理指引...",
    "ask_slot_question": "正在整理要问您的信息...",
}

# 状态文案契约（前端也照这个渲染）：
#   1) 只描述"系统正在做什么"，禁止自夸（"解构现场特征"这类是营销词，不是状态）
#   2) 长度上限 20 字；改文案必须过 tests/test_status_text.py
# 上限由最长小类标签（占道经营/乱堆乱放，9 字）决定，不是随手写的数字
STATUS_MAX_LENGTH = 24
STATUS_BANNED_WORDS = ("解构", "深度研判", "智能研判", "赋能", "洞察", "强大", "领先")


# ====== 检索自评重试环（evaluator-optimizer）======
# top1 向量分数低于这个值就算检索不够强。0.58 是量出来的：实测 p10 =
# 0.5426（法规）/ 0.5726（案例），而向量置信门槛 RETRIEVAL_MIN_SCORE = 0.48。
# 依据：docs/superpowers/specs/2026-09-27-retrieval-retry-loop-design.md
WEAK_SCORE = 0.58

# 环的上界：一轮最多重试 1 次。判定由代码做，模型只负责改写检索串。
RETRY_MAX_ATTEMPTS = 1

# 对照实测用的开关：如果实测证明重试没有改善，改成 False 就能整个关掉，
# 而不是留一段死代码。
RETRY_ENABLED = True

# 检索程序返回的检索串长度上限（与 _pick_keyword 对齐）
MAX_RETRIEVAL_KEYWORD = 24

# 图的步数上限。本图最长的合法路径（含一次重试）约 16 步，60 足够宽松。
# 为什么要显式设：新加的重试环是一条回边，一旦上限失效（例如后来有人把节点注解回基类），
# 默认的 10007 会让它转到天荒地老并烧掉大量模型调用。宁可快速报错。
GRAPH_RECURSION_LIMIT = 60

# 是否为“灰色带”多花一次 embedding 取 top1 分数。
# 分数不在检索文本里，只能另跑一次向量检索；实测单次 ~0.94s（embedding 占大头），
# 两张表并发后整轮增加约 +0.9s。买到的是：第一步实测的 8 个触发点里有 4 个
# 只有分数能抓（top1 在 [0.48, 0.58) 的灰色带）。关掉它只剩“完全无结果 /
# 没有语义命中 / T1 / T2”触发，零额外成本。
PROBE_TOP1_SCORE = True


class AssistantGraphState(AssistantState, total=False):
    """图实际使用的状态：在共享状态上加检索重试环自己的通道。

    为什么不直接写进 core/langgraph_state.py：这些通道只服务这张图。而且未声明的键
    会被 LangGraph **静默丢弃**（节点返回未声明键时值不会进 state，已实测），
    所以计数器必须在此显式声明。

    坑（实测）：LangGraph 按**参数的注解**过滤节点输入。节点参数注解成基类
    AssistantState 时，这里新增的通道在节点里读到的是 None（写进去的值在
    state 里，但节点看不见）——环会因此永远不收敛。所以读这些通道的节点
    （plan_retrieval / evaluate_retrieval / rewrite_query）必须注解成 AssistantGraphState。
    """
    retrieval_attempts: int          # 本轮已重试几次（0/1）：环的上界靠它
    retrieval_scores: Annotated[dict, merge_category_results]   # {code: {field: top1 分数}}
    retrieval_keyword_override: dict  # {code: 改写后的检索串}，只在本轮内有效
    retrieval_retry_log: list         # 每次触发的 before/after 记录（观测用）
    retrieval_retry_reason: str       # 本次触发原因（T1/T2/T3），供改写提示词与日志用


def _status_context(update: dict) -> dict:
    results = update.get("category_results") or {}
    category = ""
    if results:
        first = next(iter(results))
        category = SUBCATEGORY_LABELS.get(first, first)
    return {"category": category or "相关"}


def status_text(node: str, update: dict | None = None) -> str:
    """按节点产出状态文案。带上下文的模板用 update 填充，填不上就退化成模板本身。"""
    template = STATUS_TEXT.get(node, "处理中...")
    if "{" not in template:
        return template
    try:
        return template.format(**_status_context(update or {}))
    except (KeyError, IndexError):
        return "正在检索法规与案例..."


# ====== 类别化槽位（共享定义见 core.slot_schemas） ======

def rebuild_missing(categories, category_slots) -> list[str]:
    """确定性重算还缺哪些 **A 类（决策级）** 槽；顺序跟随 categories，不依赖旧优先级表。

    A 类缺失才追问；B 类（报告级）缺失不追问，走 rebuild_report_missing 进报告。
    """
    out = []
    for cat in categories:
        for s in missing_decision_slots(cat, category_slots.get(cat) or {}):
            out.append(f"{cat}_{s.key}")
    return out


def rebuild_report_missing(categories, category_slots) -> list[str]:
    """A+B 类缺失 = 报告「仍需确认」的条件分支材料（阶段 4 消费）。

    本阶段只把字段准备好，不改报告行为。
    """
    out = []
    for cat in categories:
        for s in missing_report_slots(cat, category_slots.get(cat) or {}):
            out.append(f"{cat}_{s.key}")
    return out


# 决策 7 的"事实"集合：越界时按快照把这些整体回滚。
# 刻意不含 category_results —— 它带 reducer（merge_category_results），只能合并不能替换，
# 而且越界那一轮根本走不到 search，本来就不会被改。
_SNAPSHOT_KEYS = ("locked_major", "locked_majors", "locked_subcategory", "categories",
                  "issues", "category_slots", "missing")


def _facts_snapshot(state) -> dict:
    """本轮**之前**的事实快照（理解之前取，见 understand 的 empty）。

    为什么不在 begin_turn 取：`task_gate` 中断回跳时直接 `goto="understand"`，跳过 begin_turn，
    那样拿到的会是上一轮留下的旧快照 —— 回滚就会把 gate 那一轮攒的事实一起抹掉。
    understand 在每条路径上都跑，且在它改写事实**之前**读 state，所以在这里取永远是最新的。
    """
    # 值做类型归一：字段"从没被设过"时 state.get 给 None，直接回滚会写出
    # `categories: None` 这种与声明不符的值。归一之后回滚就是一次干净的还原。
    return {
        "locked_major": str(state.get("locked_major") or ""),
        "locked_majors": list(state.get("locked_majors") or []),
        "locked_subcategory": str(state.get("locked_subcategory") or ""),
        "categories": list(state.get("categories") or []),
        "issues": list(state.get("issues") or []),
        "category_slots": dict(state.get("category_slots") or {}),
        "missing": list(state.get("missing") or []),
    }


def _facts_rollback(state) -> dict:
    """把事实回滚到本轮之前（决策 7：越界撤销本轮，而不是清零）。

    为什么不是清零：用户只是跑题（"今天天气不错"）时，正在跟的那条隐患要留着。
    没有快照就什么都不做 —— 宁可不动，也不要按空快照把事实抹掉。
    """
    snapshot = state.get("facts_snapshot")
    if not isinstance(snapshot, dict) or not snapshot:
        return {}
    return {key: snapshot.get(key) for key in _SNAPSHOT_KEYS}


def _detect_direct_mode(text: str, vision_summary: str = "") -> str:
    """只识别问候语。

    这里不再用关键词判定"简单问题"，因为那会在规划器之前短路，
    让"消火栓坏了算隐患吗"这类问题拿不到检索和报告。
    语义判断统一交给规划器，由 intent=quick_assessment + dialogue_policy 决定。
    """
    value = (text or "").strip().rstrip("！!。？?～~").strip()
    if vision_summary or not value:
        return ""
    if value in {"你好", "您好", "嗨", "哈喽", "在吗", "谢谢", "感谢"}:
        return "smalltalk"
    return ""


_ROLE_BUILDERS = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


def _thread_id(user_id: int | None, session_id: str) -> str:
    """LangGraph checkpoint 必须按用户隔离；生产调用始终有 user_id。"""
    owner = str(user_id) if user_id is not None else "anonymous"
    return f"{owner}:{session_id}"


def build_turn_input(session_id: str, message: str, vision_summary: str,
                     selected_major_code: str, selected_major_codes=None,
                     image_url: str = '', image_file_id: int = None) -> dict:
    """本轮只传新增事实；结构化状态由 checkpointer 持有，不再每轮清空。"""
    state = {
        "session_id": session_id,
        "messages": [HumanMessage(content=message)],
        "vision_summary": vision_summary,
        "selected_major_code": selected_major_code,
        "selected_major_codes": list(selected_major_codes or []),
    }
    # 图片只在本轮有新上传时覆盖；后续确认/补地址继续沿用上轮 fileId。
    if image_file_id is not None:
        state["image_url"] = image_url or ""
        state["image_file_id"] = image_file_id
    return state


def seed_messages(history) -> list:
    """冷启动（进程重启或首次进入该 thread）时，用会话历史给图状态打底。"""
    seeded = []
    for item in history or []:
        builder = _ROLE_BUILDERS.get((item or {}).get("role"))
        if builder is not None:
            seeded.append(builder(content=(item or {}).get("content", "")))
    return seeded


def begin_turn(state: AssistantState) -> dict:
    """重置**本轮**标志位。

    只从 START 进入；task_gate 中断回跳时直接走 understand。

    只清 task_offered（它的读写都在同一轮内）。asked_question_last_turn 故意不清：
    它描述的是"上一轮问没问过"，唯一的读者是**下一轮**的 dialogue_policy —— 在这里
    清零等于让那条分支永远不成立。它每轮由 understand 结尾无条件重写（正常路径显式
    写，寒暄/规划器失败路径经 empty 写 False），所以不会残留成 True。
    """
    # guidance_emitted 同样不复位：它是"这次危险事件已经提醒过"，
    # 由 understand 在危险结束时复位，否则同一场火灾会每轮重复贴指引。
    return {
        "task_offered": False,
    }


def _latest_user_text(state) -> str:
    """取最后一条用户消息的文本（本轮用户最新说的那句）。"""
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage):
            return m.content or ""
    return ""


def _plan_issues(plan: dict) -> list[dict]:
    """规划器契约以 issues 为准。

    若规划器只给了旧的 categories/category_slots 形状，就在这里确定性地补成 issues，
    避免 understand 因为上下游形状漂移而整体失效。
    """
    issues = []
    for raw_issue in (plan.get("issues") or []):
        if not isinstance(raw_issue, dict):
            continue
        code = str(raw_issue.get("subcategory_code") or "").strip()
        if not code:
            continue
        major = SUBCATEGORY_TO_MAJOR.get(code)
        if not major:
            major = str(raw_issue.get("major_code") or "").strip()
        if major not in MAJOR_LABELS:
            continue
        issue = dict(raw_issue)
        issue["major_code"] = major
        issues.append(issue)
    if issues:
        return issues
    slots_by_category = plan.get("category_slots") or {}
    legacy = []
    for raw in plan.get("categories") or []:
        pair = normalize_taxonomy(raw)
        if not pair or pair[1] not in ALL_SUBCATEGORY_CODES:
            continue
        legacy.append({
            "major_code": pair[0],
            "subcategory_code": pair[1],
            "slots": dict(
                slots_by_category.get(raw) or slots_by_category.get(pair[1]) or {}
            ),
        })
    return legacy


def _merge_persisted_slots(issues: list[dict], persisted: dict,
                           persisted_issues: list[dict] | None = None) -> list[dict]:
    """Fold checkpoint slots into this turn while retaining only valid old evidence.

    A slot re-extracted this turn uses this turn's evidence. Evidence for slots
    carried over from the checkpoint remains attached to its original value.
    """
    previous_by_code = {
        issue.get("subcategory_code"): issue
        for issue in (persisted_issues or [])
        if isinstance(issue, dict) and issue.get("subcategory_code")
    }
    merged = []
    for issue in issues:
        code = issue.get("subcategory_code")
        incoming_slots = dict(issue.get("slots") or {})
        kept = dict(persisted.get(code) or {})
        kept.update({k: v for k, v in incoming_slots.items() if v})
        issue = dict(issue)
        issue["slots"] = kept

        evidence = [
            dict(item) for item in (issue.get("evidence") or [])
            if isinstance(item, dict) and item.get("slot")
        ]
        seen_slots = {item.get("slot") for item in evidence}
        previous = previous_by_code.get(code) or {}
        previous_evidence = {
            item.get("slot"): item
            for item in (previous.get("evidence") or [])
            if isinstance(item, dict) and item.get("slot")
        }
        for slot in kept:
            if slot in incoming_slots or slot in seen_slots:
                continue
            old = previous_evidence.get(slot)
            if old:
                evidence.append(dict(old))
                seen_slots.add(slot)
        issue["evidence"] = evidence
        merged.append(issue)
    return merged


_CAUTIOUS_NOTE = (
    "（以下是初步判断：有一条现场信息我无法从你的描述中确认，建议先核实再上报。）"
)


GAS_GUIDANCE_LINE = (
    "如果闻到煤气味或燃气味：立即开窗通风、关闭燃气总阀，"
    "不要开关任何电器、不要使用明火，先撤到室外再联系燃气公司抢修；"
    "情况紧急或已有人不适，请立即拨打 119（救援）或 110。"
)
_GAS_DANGER_TERMS = ("煤气味", "燃气味", "煤气泄漏", "燃气泄漏", "漏气")


def guidance_line(text: str) -> str:
    """危险词决定用哪条指引：燃气场景需要关阀开窗那几句，泛用的 119 指引不够。"""
    term = active_danger_term(text)
    if term and term in _GAS_DANGER_TERMS:
        return GAS_GUIDANCE_LINE
    return GUIDANCE_LINE


def prepend_guidance(text: str, state: AssistantState) -> str:
    """安全指引由代码保证；模型自己已经说了 119 就不重复。

    图内已无消费者（危险输入一律走 emergency_guidance 节点），这里是**非图调用者的安全网**：
    直接调用 answer_reply() 的路径仍靠它把指引前置。guidance_emitted 用来判「这次危险事件
    是否已经发过」，避免同一场危险重复贴。
    """
    if not state.get("danger_veto") or state.get("guidance_emitted"):
        return text
    if "119" in (text or ""):
        return text
    return guidance_line(_latest_user_text(state)) + "\n\n" + (text or "")


def prepend_interpretation(text: str, state: AssistantState) -> str:
    if state.get("uncertainty_level") != "cautious":
        return text
    if _CAUTIOUS_NOTE in (text or ""):
        return text
    return _CAUTIOUS_NOTE + "\n\n" + (text or "")


def _reply_prefix(state: AssistantState) -> str:
    """报告是先流式输出再落 draft，无法事后去重，所以这里只前置、不判重。

    同 prepend_guidance：图内危险路径不会走到这里（走 emergency_guidance），
    它是直接调用 report() 的非图路径的安全网。
    """
    parts = []
    if state.get("danger_veto") and not state.get("guidance_emitted"):
        parts.append(guidance_line(_latest_user_text(state)))
    if state.get("uncertainty_level") == "cautious":
        parts.append(_CAUTIOUS_NOTE)
    return ("\n\n".join(parts) + "\n\n") if parts else ""


GUIDANCE_LINE = (
    "如果现场正在起火、有人被困、燃气泄漏，或存在触电、坍塌等即时危险，"
    "请先确保自身安全并立即拨打 119（火警/救援）或 110，不要为了补全信息而停留。"
)


PREMISES_NOTES = {
    "indoor": "（这属于户内问题：城市隐患上报主要面向公共部位，建议先联系物业或专业维修处理。）",
    "indoor_risk": "（这属于户内问题，但可能影响公共安全，建议同时联系物业或燃气公司；情况紧急请先拨打 119。）",
}
INDOOR_TASK_REMINDER = "（提醒：这属于户内问题，上报后通常仍需你自行联系物业或燃气公司处理。）"


def task_invitation_question(state) -> str:
    """建任务邀请的唯一出口：户内时附带一句提醒。"""
    question = "需要我帮你在系统建一条隐患任务吗？"
    if ((state or {}).get("premises_scope") or "public") in PREMISES_NOTES:
        question += "\n\n" + INDOOR_TASK_REMINDER
    return question


def _major_label(code: str) -> str:
    return MAJOR_LABELS.get(code or "", code or "")


def _major_subcategory_labels(major_code: str) -> list[str]:
    for item in HAZARD_TAXONOMY:
        if item["code"] == major_code:
            return [label for _code, label in item["subcategories"]]
    return []


def _in_major_question(major_code: str) -> str:
    """类内问句由代码生成：它只是把小类表读出来，不需要模型。"""
    label = _major_label(major_code)
    options = _major_subcategory_labels(major_code)[:3]
    if not options:
        return "具体是哪一类%s隐患？" % label
    return "具体是哪一类「%s」隐患？比如%s。" % (label, "、".join(options))


def _scope_notice(locked_majors, other_major: str, tracking: str) -> str:
    """越界只给通知：不改锁、不改小类、不发问句。"""
    scope = "、".join(_major_label(code) for code in (locked_majors or [])) or "这条对话"
    return (
        "（这是「%s」范围的对话，刚才那句更像是「%s」类的问题。"
        "如果确实是这一类，建议另开一个对话并选择对应大类；"
        "如果还是「%s」的问题，直接继续补充就行。）"
        % (scope, _major_label(other_major), tracking)
    )


MAX_ACTIVE_HAZARDS = 3
MAX_ACTIVE_MAJORS = 3


def _vision_major_codes(vision_summary) -> list:
    """Extract explicit hazard majors from a system-generated vision summary."""
    value = str(vision_summary or "")
    found = []
    for label, code in MAJOR_LABEL_TO_CODE.items():
        if label in value and code not in found:
            found.append(code)
    for code, label in SUBCATEGORY_LABELS.items():
        if label in value:
            major = SUBCATEGORY_TO_MAJOR.get(code, "")
            if major and major not in found:
                found.append(major)
    return found[:MAX_ACTIVE_MAJORS]


def _locked_majors(state) -> list:
    """锁定的大类集合。没有集合字段时退回单值字段 —— 兼容旧状态与既有测试。"""
    majors = [str(m) for m in (state.get("locked_majors") or []) if m]
    if majors:
        return majors
    single = str(state.get("locked_major") or "")
    return [single] if single else []


def _major_codes(value) -> list:
    """把前端的大类提示归一成一个集合：支持列表、逗号/空格分隔的串、单个编码。

    为什么支持逗号串：前端多选不必新增字段 —— 把几个 code 用逗号拼进原来那个
    `selected_major_code` 就能用，Java 那一层一个字都不用改。
    """
    if isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = re.split(r"[,，、\s]+", str(value or ""))
    out = []
    for item in raw:
        code = str(item or "").strip()
        if code in MAJOR_LABELS and code not in out:
            out.append(code)
    return out

# 并列追问里的序号：只做展示，不进任何判据。
_CLAUSE_NUMBERS = ("①", "②", "③")
_CLAUSE_COUNTS = {2: "两", 3: "三"}


def _focus_candidate(in_major, plan) -> dict:
    """这一轮把焦点放在哪一条：优先模型说的「这句话指的是哪一件」，其次本轮第一条。

    为什么不信顺序：契约要求模型把「当前仍有效的问题一起放进 issues」，它会把历史里
    那件也报上来 —— 顺序因此不可靠。perceived_subcategory 在契约边界已经校验过
    （不在词表里就清空），这里再要求它必须落在 in_major 里（＝锁定的大类集合内），
    取不到就退回第一条。
    """
    seen = str((plan or {}).get("perceived_subcategory") or "").strip()
    if seen:
        for issue in in_major:
            if issue.get("subcategory_code") == seen:
                return issue
    return in_major[0]


def _active_issues(focus, in_major) -> list:
    """本轮活动的隐患条目：焦点那条打头，其余同大类条目跟上（上限 MAX_ACTIVE_HAZARDS）。

    跨大类的条目刻意不在这里 —— 一张工单只有一个类别，那类只发通知（见 _scope_notice）。
    """
    if not focus:
        return []
    out = [focus]
    seen = {focus.get("subcategory_code")}
    for issue in in_major:
        code = issue.get("subcategory_code")
        if not code or code in seen:
            continue
        out.append(issue)
        seen.add(code)
        if len(out) >= MAX_ACTIVE_HAZARDS:
            break
    return out


def skill_route(state: AssistantState) -> dict:
    """Choose active hazard-major Skills before this turn's fact extraction."""
    selected = _major_codes(state.get("selected_major_codes") or [])
    if not selected:
        selected = _major_codes(state.get("selected_major_code") or "")
    result = _route_skills(
        text=_latest_user_text(state),
        metadata_catalog=_skill_registry.metadata_catalog(),
        selected_major_codes=selected,
        locked_majors=_locked_majors(state),
        vision_categories=_vision_major_codes(state.get("vision_summary") or ""),
        route_llm=_skill_route_llm,
    )
    active = list(result.get("active_skills") or [])[:MAX_ACTIVE_MAJORS]
    return {
        "active_skills": active,
        "skill_route_source": result.get("source", "fallback"),
        "skill_route_confidence": float(result.get("confidence") or 0.0),
        "skill_versions": _skill_registry.versions_for(active),
    }


def understand(state: AssistantState, config=None) -> dict:
    """本轮唯一的结构化事实写入者；下一步动作也在这里定，route 只做去向映射。

    一条会话最多同时跟 MAX_ACTIVE_HAZARDS 条隐患，且**同属锁定的大类集合**
    （前端多选，或自动判断模式下首轮由模型判定 —— 一句话涉及几个大类就锁几个）：
      - 大类集合一旦确定就锁死，只有前端改选才能改；模型只能建议，动不了它；
      - 小类只有用户主动纠正（intent=correction）才能改；
      - 本轮识别到、且落在这个集合里的其余条目照实记下 —— 规划器契约本来就要求
        「把当前仍有效的问题一起放进 issues」，曾经只留一条等于把用户一次说的
        第二件事静默丢掉；集合之外的大类仍然只发通知、不记录（一张工单一个类别）；
      - 每一轮都拿用户这句话去抽**当前锁定类别**的槽位（哪怕这句话在讲别的隐患）。
    """
    user_text = _latest_user_text(state)
    vision_summary = state.get("vision_summary", "")
    selected_major_code = state.get("selected_major_code", "")
    selected_major_codes = state.get("selected_major_codes") or []
    source_messages = list(state.get("messages") or [])
    prev_major = state.get("locked_major") or ""
    prev_majors = _locked_majors(state)
    prev_sub = state.get("locked_subcategory") or ""
    lock_keep = {
        "locked_major": prev_major,
        "locked_majors": prev_majors,
        "locked_subcategory": prev_sub,
        "premises_scope": state.get("premises_scope") or "public",
    }

    # 一、危险场景的产物是「应急指引」（emergency_guidance 节点）：安全文本由它按类型
    # 生成、再由代码核对必含要点。这里**不再**提前发那句通用话 —— 它对火灾和后面的
    # 专属指引重复，对地震还把类型列举错了（那串词里根本没有地震）。
    # 取舍（有意）：understand 原来在调模型之前就把话发出去了，即时反馈更好；改完之后
    # 要等 emergency_guidance 吐文本才有人话。换来的是安全文本只有一个出处，不会再出现
    # 「提前那句」与「专属指引」自相矛盾。
    announced = bool(state.get("guidance_emitted"))
    empty = {
        "issues": [], "missing": [], "clarification_question": "",
        "asked_question_last_turn": False,
        # 阶段 2 校验：missing 非空却没问出问题（按设计不问 / 该问没问），每轮重置
        "question_missing": [], "question_missing_reason": "",
        "question_source": "", "question_dropped": "",
        # 检索重试环按轮重置：每轮最多重试一次，且上一轮改写的检索串不外溢。
        # 放在这里是因为 empty 会被三个返回路径共用，而 understand 是唯一的每轮事实写入者。
        "retrieval_attempts": 0,
        "retrieval_keyword_override": {},
        # 决策 7：本轮**之前**的事实快照，供 scope_guard 判越界时整体回滚。
        # 放在 empty 里 = 三个返回路径都会带上，且是在改写事实之前读的 state。
        "facts_snapshot": _facts_snapshot(state),
    }
    if _detect_direct_mode(user_text, vision_summary):
        verdict = assess({}, source_messages, vision_summary)
        return {
            **empty, **lock_keep,
            "direct_mode": "smalltalk",
            "dialogue_plan": {},
            # 危险优先于寒暄：正在发生的危险一律走应急指引产物
            "next_action": EMERGENCY_ACTION if verdict["danger_veto"] else "answer_now",
            "report_mode": "none",
            **verdict,
            "guidance_emitted": announced if verdict["danger_veto"] else False,
        }

    # 只在已锁定小类时注入「已知事实 + 仍缺的决策级信息」：没有锁定时不存在
    # 「这条隐患缺什么」，塞一段空上下文只会让规划器以为有活跃隐患。
    planner_context = {}
    if prev_sub:
        persisted = dict((state.get("category_slots") or {}).get(prev_sub) or {})
        planner_context = {
            "missing": [s.key for s in missing_decision_slots(prev_sub, persisted)],
            "known_slots": persisted,
            "subcategory_code": prev_sub,
        }
    routed_active_skills = list(state.get("active_skills") or [])
    skill_bodies = {}
    for code in routed_active_skills:
        try:
            skill_bodies[code] = _skill_registry.load_body(code)
        except Exception as exc:
            logger.error("skill_body_load_failed code=%s error=%s", code, type(exc).__name__)
    planner_kwargs = dict(planner_context)
    if routed_active_skills:
        planner_kwargs["active_skill_codes"] = routed_active_skills
    if skill_bodies:
        planner_kwargs["skill_bodies"] = skill_bodies
    plan = _understand_plan(
        source_messages, vision_summary, selected_major_code, **planner_kwargs
    )
    if not plan or not plan.get("ok"):
        # 不静默：规划器拿不到有效计划（回空 / JSON 破）时，这一轮只能走兜底 ——
        # 这条路径原先一声不响，「到底有几次、是回空还是解析不出来」只能靠猜。
        # 先补可观测性：有频率再谈要不要加一次重试，没频率就结案。
        logger.warning("planner_failed reason=%s text=%s",
                       "no_plan" if not plan else "unparsable", user_text[:60])
        verdict = assess({}, source_messages, vision_summary)
        announced = announced or bool(verdict["danger_veto"])
        return {
            **empty, **lock_keep,
            "dialogue_plan": {},
            "categories": [],
            "category_slots": dict(state.get("category_slots") or {}),
            # 规划器挂了也可能正在危险中（漏词的紧急消息）：产物仍然是应急指引
            "next_action": EMERGENCY_ACTION if verdict["danger_veto"] else "answer_now",
            "report_mode": "none",
            "direct_mode": "",
            "policy_reason": "planner_failed",
            **verdict,
            "guidance_emitted": announced if verdict["danger_veto"] else False,
        }

    issues = _merge_persisted_slots(
        _plan_issues(plan), state.get("category_slots") or {},
        state.get("issues") or [],
    )
    # 复述问题不算答过：清掉这类槽，它们会自然落回 missing。
    echoes = echo_slots(issues)
    for issue in issues:
        removed_slots = []
        for item in echoes.get(issue["subcategory_code"], []):
            slot = item.split("=", 1)[0]
            removed_slots.append(slot)
            (issue.get("slots") or {}).pop(slot, None)
        if removed_slots:
            issue["evidence"] = [
                entry for entry in (issue.get("evidence") or [])
                if entry.get("slot") not in removed_slots
            ]
            for slot in removed_slots:
                (issue.get("slot_evidence") or {}).pop(slot, None)

    # 二、定大类**集合**：前端只在"第一次"说话，之后谁都不能改（硬锁）。
    frontend_majors = _major_codes(selected_major_codes) or _major_codes(selected_major_code)
    correction = plan.get("intent") == "correction"
    # 模型"真正认为"的大类：它可能为了配合前端提示而把 issues 写成该大类，
    # 所以不能只看 issues，必须读 perceived_major；没有时再退回 issues。
    planner_major = (plan.get("perceived_major") or "").strip() or next(
        (i.get("major_code") for i in issues if i.get("major_code")), "")
    # 集合一旦锁定，**谁都不能改**：模型动不了（用户纠正也只能换同大类里的小类），
    # 前端中途改选也不再生效 —— 要换大类只能**新开一个对话**（新会话天然重来）。
    # 自动判断模式下，第一次判定时**这一句话涉及几个大类就锁几个** —— 一次说了消防和
    # 市政两件事，就该两条都跟，而不是丢弃一条再说一句"建议另开一个对话"。
    if prev_majors:
        locked_majors = prev_majors
        if frontend_majors and set(frontend_majors) != set(prev_majors):
            # 不静默：前端中途改选被忽略 —— 前端本该把选择器锁上，所以这算异常，用 warning。
            # （用 info 会等于没写：实测本项目 INFO 级日志不上盘，只有 warning 起才落地。）
            logger.warning("major_lock_kept locked=%s frontend=%s",
                           prev_majors, frontend_majors)
    elif frontend_majors:
        locked_majors = frontend_majors[:MAX_ACTIVE_MAJORS]
    else:
        fresh = [i.get("major_code") for i in issues if i.get("major_code")]
        locked_majors = list(dict.fromkeys(fresh))[:MAX_ACTIVE_MAJORS]
    locked_major = locked_majors[0] if locked_majors else ""

    # 三、定小类：只在类内匹配；能匹配到就锁，匹配不到就留空，绝不硬造
    # 越界看"模型认为属于哪个大类"，不看它是否配合提示写了类内的 issues：
    # 配合写出来的那条本身就是硬填，不能采信。
    out_of_major = (
        bool(locked_majors) and bool(planner_major) and planner_major not in locked_majors
    )
    in_major = [] if out_of_major else [
        i for i in issues if i.get("major_code") in locked_majors
    ]
    # 焦点默认**继承**上一轮的锁定小类，只在两种情况下才换：用户明确纠正 / 还没锁过。
    # 大类集合同理：锁定后模型和前端都动不了，只有新开对话才能重来。
    # 换的时候优先听模型说的 perceived_subcategory（「这句话指的是哪一件」），
    # 而不是本轮 issues 的顺序 —— 契约要求模型「把当前仍有效的问题一起放进 issues」，所以
    # 它会把历史里那件也报上来，顺序因此不可靠（实测：两条都报、井盖排在前面时，
    # 锁会被拉回井盖，而模型自己明明说了焦点是路灯杆）。
    # 一句话同时说两件时不需要"选"焦点：两件都进活动集、都会被追问（见 _parallel_slot_question）。
    # 集合锁死之后，唯一还能换小类的就是"用户明确纠正"（外加第一次锁定）。
    # 原来的 `frontend_changed` 已经作废：前端改选大类被硬锁忽略，永远进不来。
    relock_sub = correction or not prev_sub
    locked_subcategory = prev_sub
    focus = None
    if in_major:
        candidate = _focus_candidate(in_major, plan)
        if relock_sub:
            locked_subcategory = candidate["subcategory_code"]
        focus = next((i for i in in_major
                      if i.get("subcategory_code") == locked_subcategory), None)
    if focus is None and locked_subcategory:
        # 锁还在：用锁定的小类继续累积槽位（跨轮补充信息靠这里回捞）。
        # **槽位必须带上已持久化的那一份**：这里曾经硬写 `slots: {}`，于是一旦某一轮规划器
        # 没给出该小类的 issue（跑题、只说"嗯"、判不出来），focus 就被重建成空槽，紧接着
        # `category_slots[code] = {}` 把之前攒的全部覆盖掉 —— 用户被重新问一遍已经答过的问题。
        focus = {"major_code": locked_major,
                 "subcategory_code": locked_subcategory,
                 "slots": dict((state.get("category_slots") or {}).get(locked_subcategory) or {})}
    issues = _active_issues(focus, in_major)

    if out_of_major:
        _emit_chunk(_scope_notice(
            locked_majors, planner_major,
            SUBCATEGORY_LABELS.get(locked_subcategory, _major_label(locked_major)),
        ))

    plan = dict(plan)
    plan["issues"] = issues
    # 二、模型判定的危险（词表漏了）：不在这里发话，只把结果记进状态 ——
    # 安全文本统一由 emergency_guidance 按类型生成并核对覆盖。
    verdict = _apply_evidence_mode(assess(plan, source_messages, vision_summary))
    if echoes:
        verdict["uncertainty_signals"] = list(verdict["uncertainty_signals"]) + [
            "echo_slot:%s" % item for items in echoes.values() for item in items
        ]

    # Runtime semantic review happens before missing/report-missing is rebuilt.
    # Only the enforce mode may spend labeler calls; off/shadow keep legacy behavior.
    if SLOT_EVIDENCE_MODE == "enforce":
        verdict["slot_evidence_audit"] = verify_weak_slots(
            issues,
            verdict.get("slot_evidence_audit") or {},
            _cancel_token(config),
        )

    announced = announced or bool(verdict["danger_veto"])
    # 户内/公共边界：只影响一句说明，不影响分类、不挡流程
    premises_scope = (plan.get("premises_scope") or "public").strip() or "public"
    if premises_scope in PREMISES_NOTES and state.get("premises_scope") != premises_scope:
        _emit_chunk(PREMISES_NOTES[premises_scope] + "\n\n")

    categories = [issue["subcategory_code"] for issue in issues]
    category_slots = dict(state.get("category_slots") or {})
    for issue in issues:
        category_slots[issue["subcategory_code"]] = dict(issue.get("slots") or {})

    audit_by_issue = verdict.get("slot_evidence_audit") or {}
    if SLOT_EVIDENCE_MODE == "enforce":
        _drop_unusable_slots(issues, category_slots, audit_by_issue)
        missing = _rebuild_issue_missing(issues, category_slots)
        # Unusable slots were removed above and now live in missing/report_missing.
        # They must not keep the legacy "cautious" veto alive and suppress a
        # decision-critical follow-up.
        kept = sum(len((issue.get("slots") or {})) for issue in issues)
        grounded = sum(
            1 for issue in issues
            for slot, result in ((audit_by_issue.get(issue["subcategory_code"]) or {}).items())
            if slot in (issue.get("slots") or {})
            and result.get("business_status") in {"grounded", "grounded_by_model"}
        )
        verdict["grounding_ratio"] = grounded / kept if kept else 1.0
        verdict["ungrounded_slots"] = []
        verdict["uncertainty_level"] = (
            "cautious" if plan.get("major_mismatch") else "ok"
        )
        unverified = {}
    else:
        missing = rebuild_missing(categories, category_slots)
        missing_keys = set(missing)
        report_missing_keys = set(rebuild_report_missing(categories, category_slots))
        for issue in issues:
            code = issue["subcategory_code"]
            issue["missing"] = [
                slot.key for slot in get_slot_schema(code)
                if f"{code}_{slot.key}" in missing_keys
            ]
            issue["report_missing"] = [
                slot.key for slot in get_slot_schema(code)
                if f"{code}_{slot.key}" in report_missing_keys
            ]
        unverified = _unverified_by_issue(verdict["ungrounded_slots"])

    for issue in issues:
        issue["unverified"] = (
            [] if SLOT_EVIDENCE_MODE == "enforce"
            else unverified.get(issue["subcategory_code"], [])
        )
        issue["slot_evidence"] = dict(audit_by_issue.get(issue["subcategory_code"]) or {})
    no_questions = verdict["danger_veto"] or verdict["uncertainty_level"] == "cautious"
    policy = decide_next_action(plan, {
        **state, "user_text": user_text, "missing": missing, **verdict,
    })
    action = policy.get("action") or "answer_now"
    report_mode = policy.get("report_mode", "none")
    if action in {"report_full", "report_preliminary"} and issues:
        # 只有一条隐患了：全 → 完整报告，不全 → 初步报告（不再有 mixed）
        if any(issue.get("missing") or issue.get("unverified") for issue in issues):
            action, report_mode = "report_preliminary", "preliminary"
    if no_questions:
        if action in {"ask_critical_question", "answer_with_optional_question"}:
            action = "report_preliminary" if issues else "answer_now"
            report_mode = "preliminary" if issues else "none"
        if report_mode == "full":
            action, report_mode = "report_preliminary", "preliminary"
    question = "" if no_questions else (policy.get("question") or "")
    question_source = "understand" if question else ""
    # 缺口 2 规则：A 类决策级缺失为空 → 丢弃模型/策略给的问句。
    # 这是「B 类不追问」的真保证 —— 缺的只是报告级/装饰级信息时不该消耗用户耐心。
    # 例外（有意）：下面那段代码生成的「类内枚举问句」不受影响 —— 它针对的是
    # 「连小类都定不下来」，那时 missing 必然为空，丢了会话就卡死。
    question_dropped = ""
    if question and not missing:
        question_dropped = "no_decision_class_missing"
        logger.info("question_dropped reason=%s action=%s question=%s",
                    question_dropped, action, question)
        question, question_source = "", ""
    # 四、类内但说不清是哪一类 → 问一句（代码生成的枚举问句）
    if not out_of_major and not issues and locked_major and not locked_subcategory \
            and not no_questions:
        action, report_mode, question = "ask_critical_question", "none", _in_major_question(locked_major)
        question_source = "understand"
    if verdict["danger_veto"]:
        # 决策 1 + 决策 4：危险场景的产物是「应急指引」而不是报告 ——
        # 不进 search/report（因此也不会走到建任务闸门）、不追问、也不做安全确认。
        # 放在最后覆盖：上面那些"降级成初步报告"的分支只对"事实存疑"生效。
        action, report_mode, question = EMERGENCY_ACTION, "none", ""
        question_source = ""
    # 阶段 5a：问句是否指向 A 类缺失 —— 只告警、不改写。
    # 本轮要进 ask_slot_question 时，由那个节点统一审（它才是最终交付的那一句）；
    # 否则审这里定下来的问句（规划器自带的、或代码生成的类内枚举问句 —— 后者
    # missing 必然为空，会自然落到「没有该问的题材」，不会被误报）。
    if not _will_ask_slot_question(action, missing, verdict["danger_veto"]):
        question_target_audit(
            question=question,
            target_slot=str(plan.get("question_target") or ""),
            missing_keys=_decision_keys_of(issues, locked_subcategory),
            origin=question_source or "understand",
            code=locked_subcategory,
        )
    # 阶段 2 校验（不静默）：missing 非空却没问出问题。
    # reason 区分「按设计不问」（危险 / 事实存疑 / 出报告）与「该问没问」，后者报警告。
    question_missing = []
    question_missing_reason = ""
    if missing and not question:
        question_missing = list(missing)
        if verdict["danger_veto"]:
            question_missing_reason = "danger_veto"
        elif verdict["uncertainty_level"] == "cautious":
            question_missing_reason = "cautious"
        elif action in {"report_full", "report_preliminary"} or report_mode != "none":
            question_missing_reason = "report"
        else:
            question_missing_reason = "planner_no_question"
        log = logger.warning if question_missing_reason == "planner_no_question" else logger.info
        log("question_missing reason=%s action=%s missing=%s",
            question_missing_reason, action, question_missing)

    reason = policy.get("reason", "")
    if no_questions:
        reason = "%s | %s" % (reason, ",".join(verdict["uncertainty_signals"])[:180])
    active_skills = routed_active_skills
    skill_route_source = state.get("skill_route_source") or "fallback"
    skill_route_confidence = float(state.get("skill_route_confidence") or 0.0)
    if locked_majors and set(locked_majors) != set(routed_active_skills):
        logger.warning("skill_route_mismatch active=%s locked=%s",
                       routed_active_skills, locked_majors)
        active_skills = list(locked_majors)[:MAX_ACTIVE_MAJORS]
        skill_route_source = "locked"
        skill_route_confidence = 1.0
    return {
        **empty,
        "dialogue_plan": plan,
        "intent": plan.get("intent", ""),
        "issues": issues,
        "categories": categories,
        "category_slots": category_slots,
        "missing": missing,
        "locked_major": locked_major,
        "locked_majors": locked_majors,
        "locked_subcategory": locked_subcategory,
        "suggested_major_code": planner_major if out_of_major else "",
        "immediate_danger": bool(plan.get("immediate_danger")),
        "premises_scope": premises_scope,
        "selected_major_code": plan.get("selected_major_code", selected_major_code),
        "active_skills": active_skills,
        "skill_route_source": skill_route_source,
        "skill_route_confidence": skill_route_confidence,
        "skill_versions": _skill_registry.versions_for(active_skills),
        "major_mismatch": bool(plan.get("major_mismatch")),
        "clarification_question": question,
        "question_source": question_source,
        "question_dropped": question_dropped,
        "optional_question": bool(policy.get("optional_question")) and not no_questions,
        "next_action": action,
        # M1：产物模式跨轮继承。危险 / 兜底不改模式（mode_of_action 会返回原值）。
        "dialogue_mode": mode_of_action(action, state.get("dialogue_mode") or ""),
        "report_mode": report_mode,
        "policy_reason": reason,
        "direct_mode": "",
        "asked_question_last_turn": bool(question),
        **verdict,
        "guidance_emitted": announced if verdict["danger_veto"] else False,
        "question_missing": question_missing,
        "question_missing_reason": question_missing_reason,
    }


_SCOPE_DIRECT_MODES = ("smalltalk",)

# 决策 7：这两种 scope 下要撤销本轮锁定。`smalltalk` 不在此列 ——
# 寒暄走的是 understand 里的 _detect_direct_mode 早退，不经过这里；
# 而 decide_scope 判出的 smalltalk（极少数问候词）本轮暂不处理，保持现状。
_ROLLBACK_SCOPES = ("ambiguous", "out_of_scope")


def scope_guard(state: AssistantState) -> dict:
    """Keep the assistant inside its city-safety hazard scope."""
    if state.get("danger_veto"):
        # 正在发生的危险：不能被范围护栏降级成"越界拒绝"，
        # 也不改 understand 定好的动作（它已经禁掉了追问）。
        return {"scope": "emergency", "scope_reason": "danger veto"}
    if state.get("direct_mode") in _SCOPE_DIRECT_MODES:
        return {}
    plan = state.get("dialogue_plan") or {}
    user_text = _latest_user_text(state)
    scope_key = f"{state.get('session_id', '')}|{len(state.get('messages') or [])}|{user_text}"
    # support_text：视觉摘要也算原文的一部分（用户只说「这个歪了」时，物件在图片说明里）。
    # 它只参与「有没有依据」的核对，不参与确定性词表判定。
    decision = decide_scope(plan, user_text, scope_key=scope_key,
                            support_text=state.get("vision_summary") or "")
    scope = decision.get("scope", "hazard")
    if scope == "hazard":
        return {"scope": "hazard", "scope_reason": decision.get("reason", "")}
    if scope == "emergency":
        # 理论上不可达：危险信号已在上面短路。留着是为了那条不变式 ——
        # 任何 emergency 都绝不能被降级成"越界拒答"，也绝不能被模板替换掉上下文。
        return {"scope": "emergency", "scope_reason": decision.get("reason", "")}
    mode_map = {
        "ambiguous": "anchor_domain",
        "out_of_scope": "out_of_scope",
        "smalltalk": "smalltalk",
    }
    update = {
        "scope": scope,
        "scope_reason": decision.get("reason", ""),
        "scope_response": decision.get("response", ""),
        "direct_mode": mode_map.get(scope, "out_of_scope"),
        # 越界/模糊/紧急一律只回答，不允许走到检索
        "next_action": "answer_now",
        "report_mode": "none",
    }
    if scope in _ROLLBACK_SCOPES:
        # 决策 7：这一句不在范围内 → 撤销本轮对事实造成的改动（见 _facts_rollback）。
        # 不清零：正在跟的那条隐患要留着。
        update.update(_facts_rollback(state))
    return update


def route(state: AssistantState) -> Command[Literal[
        "search", "emergency_guidance", "ask_slot_question", "boundary_reply",
        "smalltalk_reply", "answer_reply", "fallback_reply"]]:
    """纯映射：understand 已经定好下一步动作，这里只决定去哪个节点。"""
    if state.get("next_action") == EMERGENCY_ACTION:
        return Command(goto="emergency_guidance")
    if state.get("next_action") in {"report_full", "report_preliminary"}:
        return Command(goto="search")
    if _should_ask_slot_question(state):
        return Command(goto="ask_slot_question")
    return Command(goto=_reply_destination(state))


def _reply_destination(state: AssistantState) -> str:
    """回复分支的唯一判据。

    顺序与重构前的 direct_reply **逐条对齐**：
    边界模板（direct_mode）先于模型回答，模型回答先于寒暄，最后才是兜底。
    改动这里就等于改动分发优先级，必须同时改 tests/test_reply_routing.py。
    """
    mode = state.get("direct_mode")
    if mode in ("anchor_domain", "out_of_scope"):
        return "boundary_reply"
    if (state.get("dialogue_plan") or {}).get("ok"):
        return "answer_reply"
    if mode == "smalltalk":
        return "smalltalk_reply"
    return "fallback_reply"


_ASK_SLOT_ACTIONS = ("ask_critical_question", "answer_with_optional_question")


def _decision_issue_targets(state: AssistantState) -> list[tuple[str, list[str]]]:
    """Every active issue that still has A-class gaps, in focus/display order.

    Focus only controls ordering. It is not a gate for whether an issue may
    supply the next follow-up question.
    """
    targets = []
    seen = set()
    for issue in _report_issues(state):
        code = str((issue or {}).get("subcategory_code") or "")
        if not code or code in seen:
            continue
        seen.add(code)
        keys = decision_missing_keys(state, code)
        if keys:
            targets.append((code, keys))
    return targets


def _decision_slot_keys(state: AssistantState) -> list:
    """First askable issue's A-class slot keys (kept as a compatibility helper)."""
    targets = _decision_issue_targets(state)
    return list(targets[0][1]) if targets else []


def _decision_target_code(state: AssistantState) -> str:
    targets = _decision_issue_targets(state)
    return targets[0][0] if targets else ""


def _active_issue_codes(state: AssistantState) -> list:
    """本轮活动隐患的小类编码，按 issues 顺序去重。"""
    out = []
    for issue in _report_issues(state):
        code = str((issue or {}).get("subcategory_code") or "")
        if code and code not in out:
            out.append(code)
    return out


def _parallel_slot_question(state: AssistantState) -> str:
    """多条隐患时的并列追问：每条取它自己最靠前的一个 A 类缺失，拼成一句。

    只在「至少两条各缺一个 A 类槽」时才返回；否则返回空串、走原来的单条路径
    （所以单条隐患的行为一个字都没变）。

    为什么让代码拼、不让模型写：多条的归属歧义比单条大得多，而槽位问句本来就
    写死在 slot_schemas 里 —— 交回代码更准，还省掉这一路上那次模型调用。
    每条只问一个槽：并列问点一多用户就答不动，剩下的留到下一轮。
    """
    clauses = []
    codes = _active_issue_codes(state)[:MAX_ACTIVE_HAZARDS]
    for code in codes:
        keys = decision_missing_keys(state, code)
        if not keys:
            continue                      # 这条不缺决策级信息，不占问句名额
        slot = next((s for s in get_slot_schema(code) if s.key == keys[0]), None)
        if slot is None:
            continue
        clauses.append("%s『%s』%s" % (
            _CLAUSE_NUMBERS[len(clauses)], SUBCATEGORY_LABELS.get(code, code),
            slot.question))
    if len(clauses) < 2:
        return ""
    logger.info("slot_question_multi clauses=%d codes=%s", len(clauses), codes)
    return "还想确认%s件事：%s" % (
        _CLAUSE_COUNTS.get(len(clauses), len(clauses)), "".join(clauses))


def _will_ask_slot_question(action, missing, danger_veto: bool) -> bool:
    """这一轮会不会进 ask_slot_question 节点。

    understand 与节点共用同一判据：本轮要进节点时，问句由节点统一审；
    否则两处各审一遍，同一个「指向不明」被报两次，告警就被淹了。
    """
    return bool(action in _ASK_SLOT_ACTIONS and missing and not danger_veto)


def _should_ask_slot_question(state: AssistantState) -> bool:
    """只在「要追问 且 A 类缺失非空」的轮次进新节点。

    G1 实测 73% 的输入 missing 为空 —— 普通轮次不进这个节点，也就不多一次模型调用。
    """
    return _will_ask_slot_question(state.get("next_action"), state.get("missing"),
                                  bool(state.get("danger_veto")))


def ask_slot_question(state: AssistantGraphState, config=None) -> Command:
    """第 1 轮的问句来源：只读事实、只写问句。

    为什么需要它：`missing` 注入只对第 2 轮及以后生效 —— 第 1 轮的锁定小类是规划器
    跑完之后才定的。实测（阶段 2）：首轮「小区消防通道长期被私家车占用」时规划器
    问的是 impact（B 类），而真正缺的 A 类是 persistence。

    三级降级：本节点产出的问句（须自报 target_slot 命中 A 类缺失）→ understand 自带
    问句 → 槽位 schema 的固定问句。固定兜底是阶段 5 的删除对象，这轮必须留着。
    """
    if not _should_ask_slot_question(state):
        return Command(goto=_reply_destination(state))
    code = _decision_target_code(state)
    keys = _decision_slot_keys(state)
    # 多条隐患：这一轮的追问由代码拼（每条一个问点）。**必须放在 keys 判断之前** ——
    # 焦点那条已经齐、缺的是别的条时，keys 是空的，放在后面就永远走不到并列追问。
    # 只有一条缺时它返回空串，走下面的单条路径（三级降级、target 审核都保持原样）。
    parallel = _parallel_slot_question(state)
    if parallel:
        return Command(goto=_reply_destination(state), update={
            "clarification_question": parallel,
            "question_source": "multi_hazard",
            "asked_question_last_turn": True,
        })
    if not keys:
        return Command(goto=_reply_destination(state))
    slots = dict((state.get("category_slots") or {}).get(code) or {})
    candidate = _slot_question_llm(
        missing=keys, known_slots=slots, subcategory_code=code,
        user_text=_latest_user_text(state),
    ) or {}
    fixed = schema_question_for_missing(keys, code)
    question, source = resolve_slot_question(
        candidate.get("question"), candidate.get("target_slot"),
        keys, state.get("clarification_question"), fixed,
    )
    logger.info("slot_question source=%s target=%s missing=%s",
                source, candidate.get("target_slot", ""), keys)
    # 阶段 5a：问句是否指向 A 类缺失 —— 所有问句来源共用的一处核对（只告警，不改写）。
    # 目标槽按优先级取：第 1 级自报的 target_slot → 文本正好等于某个缺失槽的固定问句
    # （第 3 级，以及第 2 级走 dialogue_policy 退回固定串的那一种）→ 规划器自报的
    # question_target（第 2 级自有措辞）。三级都取不到就是判不出来 → 告警，不硬猜。
    target = str(candidate.get("target_slot") or "") if source == "ask_slot_question" else ""
    if not target:
        target = _schema_slot_of_text(question, keys, code) or str(
            (state.get("dialogue_plan") or {}).get("question_target") or "")
    question_target_audit(question=question, target_slot=target, missing_keys=keys,
                          origin=source, code=code)
    # 可观测（阶段 5）：要盯的是「用户会不会看到死板的固定串」，不是「哪一级给的」。
    # 因为第 2 级（understand 自带问句）有时本身就是 dialogue_policy._question_for_missing
    # 退回的固定串 —— 端到端实测见过这种「穿着 understand 外衣的第 3 级」。
    # 所以判据取「交付问句是否等于固定串」，与 source 无关。
    if question and question == fixed:
        logger.warning("slot_question_fixed_string source=%s target=%s missing=%s",
                       source, candidate.get("target_slot", ""), keys)
    return Command(goto=_reply_destination(state), update={
        "clarification_question": question,
        "question_source": source,
        "asked_question_last_turn": bool(question),
    })


def _append_reply(state: AssistantState, answer: str) -> dict:
    return {"messages": list(state.get("messages", [])) + [AIMessage(content=answer)]}


def boundary_reply(state: AssistantState) -> dict:
    """越界 / 模糊：范围之外的只回模板，不检索、不生成。"""
    if state.get("direct_mode") == "anchor_domain":
        answer = state.get("scope_response") or AMBIGUOUS_RESPONSE
    else:
        answer = state.get("scope_response") or OUT_OF_SCOPE_RESPONSE
    _emit_chunk(answer)
    return _append_reply(state, answer)


def smalltalk_reply(state: AssistantState) -> dict:
    """寒暄：纯模板，不追问隐患槽位。"""
    user_text = _latest_user_text(state).strip()
    if user_text.startswith(("谢谢", "感谢")):
        answer = "不客气，有新情况再告诉我就好。"
    elif user_text in {"在吗", "在么", "在不在"}:
        answer = "在的，你说说看。"
    elif user_text in {"嗨", "哈喽"}:
        answer = "嗨，我在。说说现场情况吧。"
    else:
        answer = "你好，我在。你可以直接描述现场隐患，或者上传图片。"
    _emit_chunk(answer)
    return _append_reply(state, answer)


def answer_reply(state: AssistantState) -> dict:
    """模型已经给出回答，这里只负责拼装与前置装饰（指引 / 谨慎提示）。"""
    plan = state.get("dialogue_plan") or {}
    answer = str(plan.get("answer") or "").strip()
    action = state.get("next_action")
    if action:
        question = (
            state.get("clarification_question") or ""
            if action in {"ask_critical_question", "answer_with_optional_question"}
            else ""
        )
    else:
        question = plan.get("question") or state.get("clarification_question") or ""
    if state.get("optional_question") and question and not question.startswith(("如果", "方便", "可以")):
        question = "如果方便，" + question
    # answer / question 是规划器的两个独立字段；"回答里不许夹问题"由
    # dialogue_understanding.parse_plan 在契约边界统一保证，这里只负责拼装。
    parts = [part for part in (answer, question) if part]
    answer = "\n\n".join(parts)
    if not answer:
        answer = "我先记录你描述的情况，如需进一步判断可以继续补充现场信息。"
    answer = prepend_guidance(answer, state)
    answer = prepend_interpretation(answer, state)
    _emit_chunk(answer)
    return _append_reply(state, answer)


def fallback_reply(state: AssistantState, config=None) -> dict:
    """规划器没给出可用回答时的兜底：现调一次模型流式生成初步判断。"""
    user_text = _latest_user_text(state)
    prompt = (
        "请对用户的城市安全隐患判断问题给出简短、自然的初步判断。"
        "不要检索、不要引用具体法规或案例，不要要求用户填写完整上报信息。"
        "先说明是否值得按安全隐患处理，再给出一条现场安全建议；如果信息不足，明确说需要现场核实。\n"
        f"用户问题：{user_text}"
    )
    answer_parts = []
    writer = get_stream_writer()
    prefix = _reply_prefix(state)
    if prefix:
        answer_parts.append(prefix)
        try:
            writer({"chunk": prefix})
        except Exception:
            pass
    for kind, text in _report_llm._call_llm_stream_events(
            [{"role": "user", "content": prompt}], cancellation=_cancel_token(config)):
        if kind == "chunk":
            answer_parts.append(text)
            try:
                writer({"chunk": text})
            except Exception:
                pass
    answer = "".join(answer_parts).strip()
    if not answer:
        answer = "仅凭这句话还不能确认具体风险，建议先避开可能危险区域，并补充现场情况以便进一步判断。"
        try:
            writer({"chunk": answer})
        except Exception:
            pass
    return _append_reply(state, answer)


# ---------- emergency_guidance（危险场景的唯一产物） ----------
def emergency_guidance(state: AssistantState, config=None) -> dict:
    """危险场景给「应急指引」：不检索、不报告、不建单、不追问（决策 1 + 决策 4）。

    分工沿用统一原则：代码给"必须覆盖的安全要点"并识别类型 → 模型负责措辞 →
    代码核对是否覆盖 → 覆盖不到才补上该类型的前置兜底句。

    流式：逐句放行（core.stream_guard），不必攒整篇 —— 问号是句级特征、井号是行级特征，
    都不需要看到全文。唯一必须「先知道结果」的是要不要前置兜底句，而覆盖是不可逆的，
    所以策略是「攒到覆盖为止，之后逐句放行」；模型始终没说全才退回一次性流出。
    """
    user_text = _latest_user_text(state)
    kind = emergency_guidance_type(user_text)
    context = []
    plan_answer = str((state.get("dialogue_plan") or {}).get("answer") or "").strip()
    if plan_answer:
        context.append("助手对现场的先期判断：" + plan_answer)
    labels = [
        SUBCATEGORY_LABELS.get(code, code)
        for code in (state.get("categories") or [])
    ]
    if labels:
        context.append("已识别的情况：" + "、".join(labels))
    context.append("用户原话：" + user_text)
    point_text = "；".join("/".join(group) for group in emergency_guidance_points(kind))
    lead = emergency_guidance_lead(kind)
    prompt = (
        "用户可能正在遭遇即时危险。请用 3~4 句自然、镇定的中文给出现场安全处理指引。\n"
        "必须覆盖这些要点（每条都要说到，措辞自己组织，不要照抄要点里的词）："
        + point_text + "\n"
        "顺序要求（很重要）：第一句就把上面所有要点一口气说完，让用户第一时间看到该做什么，"
        "例如「" + lead + "」；后面几句再展开细节、原因和注意事项。"
        "不要把报警、关阀、断电、撤离这类关键动作留到后面才说。\n"
        "禁止提出任何问题或反问，禁止询问是否创建任务，禁止输出 Markdown 标题，"
        "不要引用法规和案例。\n"
        + "\n".join(context)
    )
    events = _report_llm._call_llm_stream_events(
        [{"role": "user", "content": prompt}], cancellation=_cancel_token(config))
    tokens = (text for kind_of_event, text in events if kind_of_event == "chunk")
    fallback = emergency_guidance_fallback(kind)
    # 逐句流出去，不再攒整篇。但「要不要前置兜底句」必须先知道覆盖情况，
    # 而覆盖是不可逆的（文本越多只会越可能覆盖），所以：攒到覆盖为止，之后逐句放行。
    # 模型始终没说全 → 全程不放行，最后按兜底路径一次性流出。
    released = False
    emitted = []
    held = []
    for piece in guard_stream(tokens, questions=QUESTION_DROP):
        if released:
            emitted.append(piece)
            _emit_chunk(piece)
            continue
        held.append(piece)
        # 空文本不算覆盖：将来若有类型没有必含要点，这里不能把空串当成「已说全」
        if held and covers_emergency_points("".join(held), kind):
            released = True
            emitted.extend(held)
            _emit_chunk("".join(held))
            held = []
    answer = "".join(emitted + held)
    if not released:
        answer = (fallback + "\n\n" + answer) if answer else fallback
        _emit_chunk(answer)
    return _append_reply(state, answer)


# ---------- search（类别化检索：Send 并行扇出 + reducer 汇聚） ----------
def search(state: AssistantState) -> dict:
    """扇出前的栅栏节点：先清空本轮要重查的类别，再由条件边发出 Send。"""
    return {"category_results": {cat: None for cat in (state.get("categories") or [])}}


def plan_retrieval(state: AssistantGraphState) -> list[Send]:
    """每个（隐患类别, 检索工具）一条并行分支；延迟与隐患数量解耦。"""
    override = state.get("retrieval_keyword_override") or {}
    active_skills = state.get("active_skills") or []
    allowed = _skill_registry.resolve_tools(active_skills)
    allowed_retrieval = (
        [name for name in _RESULT_FIELD if name in allowed]
        if active_skills else list(_RESULT_FIELD)
    )
    sends = []
    for category in state.get("categories") or []:
        slots = (state.get("category_slots") or {}).get(category, {})
        # 重试时用模型改写过的检索串；没有就照旧拼
        keyword = override.get(category) or _pick_keyword(
            category, slots, state.get("premises_scope") or "public")
        for tool_name in allowed_retrieval:
            sends.append(Send("retrieve", {
                "category": category,
                "tool": tool_name,
                "keyword": keyword,
            }))
    return sends


def retrieve(state: AssistantState, config=None) -> dict:
    """单条并行分支：只写自己负责的那个字段，由 reducer 合并。"""
    field = _RESULT_FIELD[state["tool"]]
    result = _run_tool(state["tool"], state["keyword"], _cancel_token(config))
    return {"category_results": {state["category"]: {field: result}}}


_OBLIGATION_HINT = "维护 责任"


def _pick_keyword(category: str, slots: dict, premises_scope: str = "public") -> str:
    """返回用于一次检索的字符串。

    **这个串同时是两样东西**：向量检索的 embedding 查询，以及关键词 LIKE 的输入。
    所以小类标签必须留在里面 —— 去掉它向量查询就丢掉隐患语义。
    （标签留在串里会让关键词分支也命中 category 字段，那其实是在做小类过滤、
    纯向量拿不到的精度；所以合并顺序改成"向量在前、关键词只补尾部名额"，
    见 tools/hybrid_search.HybridSearcher._merge_results。）

    槽位值按该小类在 core.slot_schemas 里的**全部**槽位键、依 schema 顺序拼接。
    这里以前硬编码了 9 个 slug，而 31 个小类里有 16 个（施工 site/safety、
    其他 describe、占道 persistence、消防设施 function_impact …）的键都不在其中 ——
    那些小类的槽位值永远进不了检索串。

    参数 category 实际传的是小类 code（也兼容旧的两级标签）。
    """
    label = SUBCATEGORY_LABELS.get(category)
    if not label:
        pair = normalize_taxonomy(category)
        label = SUBCATEGORY_LABELS.get(pair[1], category) if pair else category
    parts = [label]
    for slot in get_slot_schema(category):
        value = (slots.get(slot.key) or "").strip()
        if value:
            parts.append(value)
    base = " ".join(parts)[:24]
    if premises_scope in {"indoor", "indoor_risk"}:
        # 户内多数是维护义务问题，别把检索词都往"处罚/违法"上引
        return (base + " " + _OBLIGATION_HINT)[:34]
    return base


def _run_tool(name: str, keyword: str, cancellation=None) -> str:
    tool = _TOOL_MAP.get(name)
    if not tool:
        return "[检索失败] 未知工具"
    try:
        return str(tool.execute(keyword=keyword, cancellation=cancellation))
    except StreamCancelled:
        raise
    except Exception as e:
        return f"[检索失败] {e}"


# ---------- evaluate_retrieval / rewrite_query（检索自评重试环） ----------

_TABLE_OF_TOOL = {"search_cases": "tb_hazard_case", "search_regulation": "tb_regulation"}

_RESULT_BLOCK = re.compile(r"【(?:结果|法规)\d+】")
_SEMANTIC_BLOCK = re.compile(r"【(?:结果|法规)\d+】\s*\[语义匹配\]")
_EMPTY_RESULT_MARKER = "未找到与"
_FAILURE_MARKERS = ("检索失败", "检索超时", "向量检索不可用",
                    "关键词为空", "retrieval timeout")


def retrieval_quality(text) -> str:
    """把一段检索文本粗分成五类，供重试判定使用。

    empty   确实没有内容（hybrid_search 的空结果文案）
    failure 检索本身失败（超时 / Milvus 不可用）——换词也救不了，不重试
    weak    有结果块，但没有任何语义命中：向量分支没过 RETRIEVAL_MIN_SCORE
    ok      有语义命中（强不强再看分数）
    unknown 不是结果格式（空串、测试里的假文本等）——判不了就不动

    分类而不直接看分数的原因：分数不在检索文本里，而追问一次向量检索要多一次 embedding。
    这里只拿“免费”的结构信号；真要分数时由 _probe_top1_score 取。
    """
    text = text or ""
    if any(marker in text for marker in _FAILURE_MARKERS):
        return "failure"
    if _EMPTY_RESULT_MARKER in text:
        return "empty"
    if not _RESULT_BLOCK.search(text):
        return "unknown"
    if not _SEMANTIC_BLOCK.search(text):
        return "weak"
    return "ok"


def _issue_major(state, category: str) -> str:
    for issue in state.get("issues") or []:
        if (issue or {}).get("subcategory_code") == category:
            return (issue or {}).get("major_code") or ""
    return state.get("locked_major") or ""


def should_retry_retrieval(state) -> tuple[bool, str]:
    """要不要为“检索不够好”再试一次。**纯函数**：只看 state，不联网、不调模型。

    判定权在代码（可验证信号），模型只负责“怎么改写”。三个条件任一成立即触发：

      T1 ungrounded_slots 非空：槽位值在原文里找不到依据，检索串被幻觉词污染；
      T2 命中的条目全部不属于锁定大类（filter_by_major 判成 NO_MATCH）；
      T3 完全没有结果 / 没有任何语义命中 / top1 分数已知且低于 WEAK_SCORE。

    上界：retrieval_attempts >= RETRY_MAX_ATTEMPTS 时一律不触发（环必须收敛）。
    """
    if not RETRY_ENABLED:
        return False, "disabled"
    attempts = int(state.get("retrieval_attempts") or 0)
    if attempts >= RETRY_MAX_ATTEMPTS:
        return False, "attempt_limit"
    ungrounded = state.get("ungrounded_slots") or []
    if ungrounded:
        return True, "T1:ungrounded:%s" % ungrounded[0]
    results = state.get("category_results") or {}
    scores = state.get("retrieval_scores") or {}
    for category, result in results.items():
        major = _issue_major(state, category)
        for field in _RESULT_FIELD.values():
            text = (result or {}).get(field)
            if not text:
                continue
            quality = retrieval_quality(text)
            if quality in ("failure", "unknown"):
                continue
            if quality == "empty":
                return True, "T3:empty:%s.%s" % (category, field)
            if major and filter_by_major(text, major) == NO_MATCH:
                return True, "T2:out_of_major:%s.%s" % (category, field)
            if quality == "weak":
                return True, "T3:no_semantic:%s.%s" % (category, field)
            score = (scores.get(category) or {}).get(field)
            if score is not None and float(score) < WEAK_SCORE:
                return True, "T3:weak_score:%s.%s=%.4f" % (category, field, float(score))
    return False, ""


def _current_keyword(state, category: str) -> str:
    """本轮真正使用的检索串：重试后是改写值，否则按槽位拼。"""
    override = state.get("retrieval_keyword_override") or {}
    if override.get(category):
        return override[category]
    slots = (state.get("category_slots") or {}).get(category) or {}
    return _pick_keyword(category, slots, state.get("premises_scope") or "public")


def _probe_top1_score(keyword: str, table: str, cancellation=None):
    """取向量分支 top1 分数（拿不到返回 None）。

    这是额外一次向量检索（多一次 embedding），所以只在“结果里确实有内容块”时才发，
    见 _collect_retrieval_scores。拿不到分数时不猜：让 T3 回到免费的结构信号上。
    """
    if not keyword or not keyword.strip():
        return None
    try:
        from tools.hybrid_search import searcher

        rows = searcher.vector_search(
            keyword.strip(), table, top_k=1, cancellation=cancellation)
    except StreamCancelled:
        raise
    except Exception:
        return None
    if not rows:
        return 0.0
    score = rows[0].get("match_score")
    return float(score) if score is not None else None


def _pending_probes(state) -> list:
    """哪些 (类别, 字段) 该取分数。没有结果块、检索失败的都不取。"""
    pending = []
    for category in state.get("categories") or []:
        result = (state.get("category_results") or {}).get(category) or {}
        for tool_name, field in _RESULT_FIELD.items():
            if _RESULT_BLOCK.search(result.get(field) or ""):
                pending.append((category, field,
                                _current_keyword(state, category),
                                _TABLE_OF_TOOL[tool_name]))
    return pending


def _collect_retrieval_scores(state, cancellation=None) -> dict:
    """给“已经有结果块”的表补一次 top1 分数。

    只在文本里确实有【结果N】/【法规N】块时才发探测请求：
      - 没有结果 → 不需要分数（T3 的 empty 分支直接命中）；
      - 检索失败 → 不该重试，也不需要分数。
    这个门控还让“用假文本跑图”的测试天然不会发起网络调用。

    两张表并发取：每次探测都是一次 embedding+Milvus，串行要多等一次。
    """
    if not PROBE_TOP1_SCORE:
        return {}
    pending = _pending_probes(state)
    if not pending:
        return {}
    out = {}
    if len(pending) == 1:
        category, field, keyword, table = pending[0]
        score = _probe_top1_score(keyword, table, cancellation)
        return {category: {field: score}} if score is not None else {}
    with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
        futures = {
            pool.submit(_probe_top1_score, keyword, table, cancellation): (category, field)
            for category, field, keyword, table in pending
        }
        for future in as_completed(futures):
            category, field = futures[future]
            try:
                score = future.result()
            except StreamCancelled:
                for pending_future in futures:
                    pending_future.cancel()
                raise
            except Exception:
                continue
            if score is not None:
                out.setdefault(category, {})[field] = score
    return out


def _merge_scores(base: dict, extra: dict) -> dict:
    merged = {key: dict(value) for key, value in (base or {}).items()}
    for category, fields in (extra or {}).items():
        merged.setdefault(category, {}).update(fields or {})
    return merged


def evaluate_retrieval(state: AssistantGraphState, config=None) -> Command[
        Literal["rewrite_query", "report"]]:
    """检索自评：代码判定要不要重试；模型只在 rewrite_query 里决定“怎么改写”。

    这个节点在 Send 扇出的汇聚点之后，**每轮只跑一次**（与 report 同位置）。
    """
    probed = _collect_retrieval_scores(state, _cancel_token(config))
    scores = _merge_scores(state.get("retrieval_scores") or {}, probed)
    update = {"retrieval_scores": probed} if probed else {}
    # 重试跑完的这一遍：把“重试后分数”补进日志，形成 触发前 → 触发后 的对照
    attempts = int(state.get("retrieval_attempts") or 0)
    log = list(state.get("retrieval_retry_log") or [])
    if attempts >= 1 and log and "after_scores" not in log[-1]:
        entry = dict(log[-1])
        entry["after_scores"] = {key: dict(value) for key, value in scores.items()}
        log[-1] = entry
        update["retrieval_retry_log"] = log
    retry, reason = should_retry_retrieval({**state, "retrieval_scores": scores})
    update["retrieval_retry_reason"] = reason if retry else ""
    return Command(goto="rewrite_query" if retry else "report", update=update)


_REWRITE_SYSTEM_PROMPT = (
    "你在为一次知识库检索换检索词。库里是「隐患类别名 + 现场关键词」这样的短语。\n"
    "只输出一行检索词：2 到 14 个字，由类别名和现场关键词组成，用空格分隔；"
    "不要标点、不要引号、不要解释、不要换行；确实想不出更好的，就原样返回给你的检索词。"
)

_rewrite_llm = Agent(
    name="rewrite_query",
    system_prompt=_REWRITE_SYSTEM_PROMPT,
    tools=[],
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
)


def _sanitize_keyword(raw, fallback: str) -> str:
    """把模型输出压成“标签 + 槽位值”的形状（_pick_keyword 的契约）。

    不能让它变成自然语言长句：关键词分支是整串 LIKE，长句会直接退化成 0 命中。
    """
    text = str(raw or "").strip()
    for stop in ("\n", "。", "！", "？", "；", "："):
        text = text.split(stop)[0]
    text = text.strip("「」『』\"'`*#- —")
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:MAX_RETRIEVAL_KEYWORD].strip()
    return text or fallback


def rewrite_query(state: AssistantGraphState, config=None) -> Command:
    """让模型换一个检索词，然后回到 search 重查。

    只重试检索：locked_major / locked_subcategory / 槽位都不动。
    """
    category = (state.get("categories") or [""])[0]
    slots = (state.get("category_slots") or {}).get(category) or {}
    current = _current_keyword(state, category)
    reason = state.get("retrieval_retry_reason") or ""
    known = "、".join("%s=%s" % (k, v) for k, v in slots.items() if v) or "（暂无）"
    prompt = (
        "当前检索词：%s\n"
        "触发重试的原因：%s\n"
        "用户原话：%s\n"
        "隐患类别：%s\n"
        "已知现场关键词：%s\n"
        "请给一个更容易在知识库里命中的检索词。"
        % (current, reason or "检索结果不够相关",
           _latest_user_text(state)[:200],
           SUBCATEGORY_LABELS.get(category, category), known)
    )
    raw = ""
    try:
        response = _rewrite_llm._call_llm(
            [{"role": "user", "content": prompt}],
            cancellation=_cancel_token(config),
        )
        raw = (response or {}).get("content") or ""
    except StreamCancelled:
        raise
    except Exception:
        raw = ""
    if raw.startswith("调用失败"):
        raw = ""                      # 模型不可用：不把错误文本当检索词
    new_keyword = _sanitize_keyword(raw, current)
    log = list(state.get("retrieval_retry_log") or [])
    log.append({
        "category": category,
        "reason": reason,
        "before_keyword": current,
        "after_keyword": new_keyword,
        "before_scores": {k: dict(v) for k, v in (state.get("retrieval_scores") or {}).items()},
    })
    return Command(goto="search", update={
        "retrieval_attempts": int(state.get("retrieval_attempts") or 0) + 1,
        "retrieval_keyword_override": {category: new_keyword},
        # 重查前作废上一批分数，否则“重试后分数”会读到旧值
        "retrieval_scores": {category: None},
        "retrieval_retry_log": log[-10:],
        "retrieval_retry_reason": "",
    })


# ---------- report（流式生成） ----------
def can_offer_task_creation(state: AssistantState) -> bool:
    """是否邀请建任务。

    闸门刻意仍然要求"全部隐患都完整"：上报链路（tools/hazard_submit._extract）
    是独立再调一次模型从对话里抽类别，不看这里的 issues。
    所以放宽成"有一条完整就邀请"会建成那条不完整的。
    等上报链路支持"指定目标隐患"之后，这里才能放宽到逐隐患。
    """
    if state.get("report_mode") == "preliminary":
        return False
    issues = state.get("issues") or []
    if not issues:
        categories = state.get("categories") or []
        issues = [{"subcategory_code": category} for category in categories]
    return bool(issues) and not (state.get("missing") or [])


def _fallback_task_draft(state: AssistantState) -> dict:
    categories = state.get("categories") or []
    if not isinstance(categories, (list, tuple)):
        categories = [categories]
    category_list = []
    for code in categories:
        pair = normalize_taxonomy(str(code or ""))
        full = format_hazard_type(pair[0], pair[1]) if pair else ""
        if full and full not in category_list:
            category_list.append(full)
        if len(category_list) >= 3:
            break
    return {
        "categoryList": category_list,
        "address": str(state.get("address_text") or ""),
        "district": state.get("district") or "",
        "description": "",
        "severity": 1,
        "longitude": state.get("picked_longitude"),
        "latitude": state.get("picked_latitude"),
        "image_file_id": state.get("image_file_id"),
    }


def _finish_task_draft(state: AssistantState, future, update: dict) -> dict:
    if future is None:
        return {**update, "task_draft": {}}
    try:
        draft = future.result(timeout=20)
    except Exception as e:  # noqa: BLE001
        logger.warning("task draft unavailable, using state fallback: %s", e)
        future.cancel()
        draft = _fallback_task_draft(state)
    if not isinstance(draft, dict):
        draft = _fallback_task_draft(state)
    return {**update, "task_draft": draft}


def _slot_questions(code, missing_keys) -> list[str]:
    """把缺的槽翻译成代码里已有的固定问句：别让模型去猜"仍需确认"什么。"""
    wanted = set(missing_keys or [])
    return [slot.question for slot in get_slot_schema(code) if slot.key in wanted]


def _report_issues(state: AssistantState) -> list[dict]:
    issues = [i for i in (state.get("issues") or []) if (i or {}).get("subcategory_code")]
    if issues:
        return issues
    # 兼容只给了 categories 的旧形状
    return [{"subcategory_code": c, "missing": []} for c in state.get("categories") or []]


def _is_preliminary(state: AssistantState) -> bool:
    """初步报告 = 事实没齐。以材料本身为准（issues 的 missing/unverified），
    不只看 report_mode —— 两者若不一致，格式要跟着材料走，否则会自相矛盾。
    """
    if (state.get("report_mode") or "") == "preliminary":
        return True
    return any(
        (issue or {}).get("missing") or (issue or {}).get("unverified")
        for issue in _report_issues(state)
    )


def _split_ungrounded(entry: str):
    """把 "dangerous_building.structure=有裂缝" 拆成 (code, slot, value)。"""
    left, _, value = str(entry or "").partition("=")
    code, _, slot = left.partition(".")
    return code, slot, value


def _effective_ungrounded_slots(verdict) -> list[str]:
    """Choose legacy or evidence-backed ungrounded slots for the active rollout mode."""
    legacy = list(
        (verdict or {}).get("legacy_ungrounded_slots")
        or (verdict or {}).get("ungrounded_slots")
        or []
    )
    if SLOT_EVIDENCE_MODE in {"off", "shadow"}:
        return legacy
    if not (verdict or {}).get("slot_evidence_audit"):
        return legacy
    if "evidence_ungrounded_slots" in (verdict or {}):
        return list((verdict or {}).get("evidence_ungrounded_slots") or [])
    return legacy


def _apply_evidence_mode(verdict: dict) -> dict:
    """Apply off/shadow/enforce without leaking internal audit into public output."""
    verdict = dict(verdict or {})
    verdict["ungrounded_slots"] = _effective_ungrounded_slots(verdict)
    if SLOT_EVIDENCE_MODE in {"off", "shadow"}:
        legacy_level = verdict.get("legacy_uncertainty_level")
        legacy_ratio = verdict.get("legacy_grounding_ratio")
        if legacy_level is not None:
            verdict["uncertainty_level"] = legacy_level
        if legacy_ratio is not None:
            verdict["grounding_ratio"] = legacy_ratio
    audit = verdict.get("slot_evidence_audit") or {}
    if SLOT_EVIDENCE_MODE == "shadow":
        summary = [
            f"{code}.{slot}={result.get('status', '')}/{result.get('reason', '')}"
            for code, slots in audit.items()
            for slot, result in slots.items()
        ]
        logger.info("slot_evidence_audit mode=shadow entries=%s", summary)
    return verdict


def _drop_unusable_slots(issues, category_slots, audit) -> list[str]:
    """Remove rejected/unavailable values before missing is rebuilt."""
    removed = []
    for issue in issues or []:
        code = str((issue or {}).get("subcategory_code") or "")
        for slot in list((issue.get("slots") or {}).keys()):
            result = ((audit.get(code) or {}).get(slot) or {})
            if result.get("business_status") not in {"rejected", "unavailable"}:
                continue
            issue["slots"].pop(slot, None)
            (category_slots.setdefault(code, {}) or {}).pop(slot, None)
            removed.append(f"{code}.{slot}")
            logger.info("slot_evidence_removed code=%s slot=%s status=%s",
                        code, slot, result.get("business_status"))
    return removed


def _rebuild_issue_missing(issues, category_slots) -> list[str]:
    categories = [
        str(issue["subcategory_code"]) for issue in issues or []
        if issue.get("subcategory_code")
    ]
    missing = rebuild_missing(categories, category_slots)
    report_missing = rebuild_report_missing(categories, category_slots)
    missing_keys = set(missing)
    report_keys = set(report_missing)
    for issue in issues:
        code = issue["subcategory_code"]
        issue["missing"] = [
            slot.key for slot in get_slot_schema(code)
            if f"{code}_{slot.key}" in missing_keys
        ]
        issue["report_missing"] = [
            slot.key for slot in get_slot_schema(code)
            if f"{code}_{slot.key}" in report_keys
        ]
    return missing


def _public_issues(issues) -> list[dict]:
    """Return issue objects safe for SSE/API callers: no evidence internals."""
    out = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        public = dict(issue)
        public.pop("evidence", None)
        public.pop("slot_evidence", None)
        out.append(public)
    return out


def _unverified_by_issue(entries) -> dict:
    grouped = {}
    for entry in entries or []:
        code, slot, value = _split_ungrounded(entry)
        if code and slot:
            grouped.setdefault(code, []).append("%s=%s" % (slot, value))
    return grouped


def _issue_blocks(state: AssistantState) -> list[str]:
    """每个隐患一段材料，并标出它自己完整不完整、还缺什么。

    这样"逐隐患模板"才有可能：完整的那条能写三段式，不完整的那条写初步式。
    """
    results = state.get("category_results") or {}
    vision = state.get("vision_summary") or ""
    blocks = []
    for index, issue in enumerate(_report_issues(state), 1):
        code = (issue or {}).get("subcategory_code") or ""
        pair = normalize_taxonomy(code)
        label = SUBCATEGORY_LABELS.get(pair[1], code) if pair else code
        missing = list((issue or {}).get("missing") or [])
        unverified = list((issue or {}).get("unverified") or [])
        result = results.get(code) or {}
        issue_major = (issue or {}).get("major_code") or ""
        # "完整"必须同时满足：关键槽都填了，且填的值在用户原话里找得到依据
        complete = not missing and not unverified
        block = [
            "[隐患%d] %s（%s）" % (
                index, label, "信息完整" if complete else "信息不完整"),
            "[视觉分析] " + vision,
            "[检索法规] " + filter_by_major(
                result.get("regulation") or "库内暂未检索到", issue_major),
            "[检索案例] " + filter_by_major(
                result.get("case") or "库内暂未检索到", issue_major),
        ]
        questions = _slot_questions(code, missing)
        if questions:
            # 标出「这一项由末尾那一个追问承载」：报告要写的是分情况判断，
            # 但它载的是 B 类；同一条信息不要既写分支又问一遍（规则见 _report_rules）。
            block.append("[仍缺信息] " + "；".join(questions)
                         + "（这一项由本轮末尾的那一个追问承载）")
        # B 类（报告级）缺失：不追问，但要进材料 —— 缺的这项不影响结论与处置方向，
        # 却会改变适用的法规条款 / 责任归属 / 处罚档次，所以报告必须写成分情况判断，
        # 不能省略、也不能写「信息尚不完整、建议进一步核实」这类空话。
        # 只取 B 类（report_missing 减掉 A 类），A 类已经走 [仍缺信息] 那一行了。
        report_missing = [str(k) for k in ((issue or {}).get("report_missing") or [])]
        b_only = [k for k in report_missing if k not in set(missing)]
        b_questions = _slot_questions(code, b_only)
        if b_questions:
            block.append("[法规适用待确认] " + "；".join(b_questions)
                         + "（缺它不影响结论和处置方向，但会改变适用的法规条款、"
                           "责任归属或处罚档次）")
        for item in unverified:
            slot, _, value = item.partition("=")
            question = next(
                (s.question for s in get_slot_schema(code) if s.key == slot), slot)
            block.append(
                "[待核实] %s（当前填写「%s」，用户原话里没有依据，不要当成已确认事实）"
                % (question, value))
        blocks.append("\n".join(block))
    return blocks


# ---------- 初步报告的必含三块 + 单问句兜底（决策 b） ----------
# 代码管「必须包含什么」：① 初步判断 ② 缺失信息 ③ 一个指向 A 类缺失槽的追问；
# 模型管「怎么说」；代码核对「有没有包含」—— 与 emergency_guidance 同一形状。
_PRELIM_JUDGMENT_MARKERS = (
    "属于", "构成", "判定", "判断", "认定", "算是", "定性", "违法", "违规",
)
_PRELIM_MISSING_MARKERS = (
    "仍需", "还需", "还需要", "需要确认", "待确认", "不清楚", "不明确", "尚不",
    "补充", "缺少", "仍缺", "不完整",
    # 实测补的：真实模型写的是「目前仍然缺的就是占用时长」「这一项尚未确认」，
    # 第一版标记表只收「仍缺」「待确认」，把这两句都漏掉了（只告警，不影响交付）。
    "仍然缺", "尚未确认", "还没确认",
    # 阶段 6 补的：「还差一项会影响定档的信息」「目前还缺两个方面」—— 阶段 5a 线上复现的措辞。
    "还差", "还缺",
)


def has_question_mark(text) -> bool:
    return any(mark in str(text or "") for mark in ("？", "?"))


def decision_missing_keys(state: AssistantState, code: str) -> list:
    """这个小类还缺的 A 类（决策级）槽 key —— 只读 state["missing"] 与 issues。"""
    prefix = (code or "") + "_"
    keys = [str(m)[len(prefix):] for m in (state.get("missing") or [])
            if str(m).startswith(prefix)]
    if keys:
        return keys
    for issue in _report_issues(state):
        if (issue or {}).get("subcategory_code") == code:
            return [str(k) for k in (issue.get("missing") or [])]
    return []


def preliminary_question_tail(state: AssistantState, body: str) -> str:
    """初步报告必须含「一个指向 A 类缺失槽的追问」；模型一个都没问就由代码补上。

    为什么只补一个：一轮最多一个问句。模型自己写了就原样用它 ——
    「至多一个」由 stream_guard.question_limiter(1) 在流上保证。
    这个兜底是弱层次：它只保证「报告里有一个问句」，不判定这个问句是否真问在缺的那个槽上
    （那需要语义判定，代码做不到）。真正指向 A 类缺失由提示词里的 [仍缺信息] 承担。
    """
    if has_question_mark(body):
        return ""
    code = str(state.get("locked_subcategory") or "")
    if not code:
        code = next((str((i or {}).get("subcategory_code") or "")
                     for i in _report_issues(state)), "")
    questions = _slot_questions(code, decision_missing_keys(state, code))
    if not questions:
        return ""
    return "\n\n" + questions[0]


def preliminary_coverage(text) -> dict:
    """弱层次的必含核对：判断 / 缺失 / 追问三块在不在。

    为什么只到「弱」：用的是词面标记，不是语义判定 —— 实测第 1 轮真实报告写的是
    「仍缺的关键点」，第一版标记表就漏检了（所以补了「仍缺」「不完整」）。
    它只用来（a）决定要不要补上确定性的那一个追问，（b）把「三块齐不齐」
    变成可测、可观测的；不用来改写正文。
    兜不住的：内容是否与上一轮**实质重复** —— 实测两个客观指标都抓不住
    （db/eval_increment_turns.txt：整篇重合度 0.162、逐句重复率 0.00），
    只能靠提示词 + 人工抽查。见 docs/superpowers/plans/2026-09-27-dialogue-quality-execution.md。
    """
    value = str(text or "")
    return {
        "judgment": any(m in value for m in _PRELIM_JUDGMENT_MARKERS),
        "missing": any(m in value for m in _PRELIM_MISSING_MARKERS),
        "question": has_question_mark(value),
    }


_EMPTY_TALK_MARKERS = (
    "建议进一步核实", "建议进一步确认", "建议进一步了解", "建议进一步查明",
    "建议自行核实", "建议自行确认", "建议核实",
    "有待进一步核实", "有待核实", "需进一步核实", "尚待核实", "待进一步核实",
)


def empty_talk_hits(text) -> list[str]:
    """空话检测（弱层次，只告警、不改写正文）：把不确定性丢回给用户、自己没做判断的表述。

    为什么只收「把核实退回给用户」的措辞，而不是「信息不完整」这类断言本身：
    线上第 1 轮实测的合格文本里就有「目前信息还不完整，需要确认的问题是：被什么东西占用了」——
    它说了「不完整」，但紧跟一个具体到槽位的确认项，是合格写法。按断言本身去抓会误伤它。
    所以标记表只收明确往回推的句式（建议进一步核实 / 有待核实 …）。

    兜不住的：它只做词面命中，不判语义。「信息不完整」+ 空话混写、或换一种说法往回推，
    都可能漏检。所以这一层和 preliminary_coverage 一样：只告警，不改写正文。
    """
    value = str(text or "")
    return [marker for marker in _EMPTY_TALK_MARKERS if marker in value]


def report_branch_keys(state: AssistantState) -> list[str]:
    """本轮所有隐患里「只缺 B 类」的槽 key 并集 —— 报告要就这些写分情况判断。

    取 report_missing 减掉 A 类：A 类缺了就走追问（[仍缺信息]），不是分支的题材。
    """
    out = []
    for issue in _report_issues(state):
        missing = set(str(k) for k in ((issue or {}).get("missing") or []))
        for key in (issue or {}).get("report_missing") or []:
            key = str(key)
            if key not in missing and key not in out:
                out.append(key)
    return out


# ---------- 阶段 5a：消冗余的观测侧（只告警、不改写正文） ----------
# 分工按 A/B/C 类走，不靠「抑制某一侧」：
#   A 决策级 -> 由末尾那一个追问承载；B 报告级 -> 由正文分情况判断承载，不再追问；
#   C 装饰级 -> 都不。
# 这里的每一条都只是「让我们能看见」：判得出来的用结构化字段判，
# 判不出来的（正文里那句自由措辞的问句指向哪个槽）只告警，不硬猜。
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？?!；;\n])")


def question_sentences(text) -> list[str]:
    """正文里能算「问句」的整句 —— 取严口径，避免用疑问词计数造成假告警。

    为什么不用「什么/怎么/多少/是否」这类词：它们在建议句和从句里大量出现，
    实测把「向现场人员问清占用从什么时候开始的」这种建议句误判成问句。
    所以只认两种：带问号，或以 吗/呢 结尾（后者是 question_limiter
    把多余问号去掉之后的残留形态）。
    """
    out = []
    for sentence in _SENTENCE_SPLIT.split(str(text or "")):
        value = sentence.strip()
        if not value:
            continue
        if "？" in value or "?" in value:
            out.append(value)
            continue
        if value.rstrip("。！!；;，,、 ").endswith(("吗", "呢")):
            out.append(value)
    return out


def _cjk_ngrams(text, size: int = 3) -> set:
    grams = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", str(text or "")):
        for i in range(len(run) - size + 1):
            grams.add(run[i:i + size])
    return grams


def slot_question_overlap(text, slot_question, size: int = 3, threshold: int = 2) -> bool:
    """启发式：正文与某个槽位自带问句共享足够多的三字片段。

    这是已经认过的那层局限的补丁 —— 「正文里给哪条槽写了分支」没有结构化判据，
    所以只做词面重叠、只告警。宁可比实际宽一点：告警是给人看的线索，不是判决。
    """
    if not text or not slot_question:
        return False
    shared = _cjk_ngrams(text, size) & _cjk_ngrams(slot_question, size)
    return len(shared) >= threshold


def redundancy_reasons(state: AssistantState, body: str) -> list:
    """冗余重叠检测：同一条缺失信息既写成条件分支、又在正文里被问。

    判据（前两条结构化，后两条启发式）：
      question_without_decision_missing  正文有问句，但 A 类缺失为空 —— 这一问没有
          A 类题材。缺口 2 的规则只覆盖 clarification_question，覆盖不到报告正文里
          模型自发的问句（线上复现的正是这一条）。
      b_class_also_branched              B 类缺失已经写成分支，正文又问一遍（真正的冗余）。
      extra_question_beside_followup     A 类缺失非空（本该只有末尾那一个追问），
          正文却出现一个以上问句 —— 多出来的那句很可能落在 B 类上。
      a_slot_expanded_beside_followup:<k>  启发式：正文（问句之外的部分）提到了某条
          A 类缺失槽 —— 它该由追问承载。
      b_slot_question_overlap:<k>       启发式：正文的问句与某条 B 类槽自带的问句重叠 —— 
          B 类该写分支、不该问。
    """
    reasons = []
    questions = question_sentences(body)
    branches = report_branch_keys(state)
    decision_missing = [str(k) for issue in _report_issues(state)
                        for k in ((issue or {}).get("missing") or [])]
    if not decision_missing:
        # 兼容只给了 categories 的旧形状：那种 issues 是 _report_issues 兜出来的、
        # missing 恒为空 —— 不补这一句就会把「A 类缺失为空」误判成事实。
        decision_missing = [str(k) for k in (state.get("missing") or [])]
    if questions and not decision_missing:
        reasons.append("question_without_decision_missing")
        if branches:
            reasons.append("b_class_also_branched")
    if questions and decision_missing and branches and len(questions) > 1:
        reasons.append("extra_question_beside_followup")
    for issue in _report_issues(state):
        code = str((issue or {}).get("subcategory_code") or "")
        missing = set(str(k) for k in ((issue or {}).get("missing") or []))
        for key in (issue or {}).get("report_missing") or []:
            key = str(key)
            if key in missing:
                continue                       # A 类那一项走 [仍缺信息]，不在这里判
            hint = _slot_questions(code, [key])
            if hint and any(slot_question_overlap(q, hint[0]) for q in questions):
                reasons.append("b_slot_question_overlap:%s" % key)
    if questions and decision_missing:
        asked = set(questions)
        statements = " ".join(
            s for s in _SENTENCE_SPLIT.split(str(body or ""))
            if s.strip() and s.strip() not in asked)
        for issue in _report_issues(state):
            code = str((issue or {}).get("subcategory_code") or "")
            for key in (issue or {}).get("missing") or []:
                hint = _slot_questions(code, [str(key)])
                if hint and slot_question_overlap(statements, hint[0]):
                    reasons.append("a_slot_expanded_beside_followup:%s" % str(key))
    return list(dict.fromkeys(reasons))


def _followup_pending(state: AssistantState) -> bool:
    """本轮还有 A 类（决策级）缺失要追问吗 —— 决定提示词要不要讲「只承载一次」。"""
    if any((issue or {}).get("missing") for issue in _report_issues(state)):
        return True
    return bool(state.get("missing"))


def _warn_redundancy(state: AssistantState, body: str) -> None:
    reasons = redundancy_reasons(state, body)
    if not reasons:
        return
    logger.warning(
        "report_question_redundancy reasons=%s code=%s decision_missing=%s branch_keys=%s",
        reasons, state.get("locked_subcategory"),
        [str(k) for issue in _report_issues(state)
         for k in ((issue or {}).get("missing") or [])],
        report_branch_keys(state))


def _decision_keys_of(issues, code) -> list:
    """本轮的 A 类缺失槽 key —— 只用刚算好的 issues，不读上一轮 state。"""
    for issue in issues or []:
        if (issue or {}).get("subcategory_code") == code:
            return [str(k) for k in ((issue or {}).get("missing") or [])]
    return []


def _schema_slot_of_text(question, keys, code: str) -> str:
    """问句文本正好等于某个缺失槽自带的固定问句时，归属到那个槽（真实归属，不是猜）。"""
    value = str(question or "").strip()
    if not value or not code:
        return ""
    for key in keys or []:
        if value == str(schema_question_for_missing([key], code) or "").strip():
            return str(key)
    return ""


def question_target_audit(*, question, target_slot, missing_keys, origin: str,
                          code: str = "") -> dict:
    """问句是否指向 A 类（决策级）缺失 —— 所有问句来源共用的一处核对。

    这是这一轮唯一能拿到「真保证」的地方，而且它不加任何措辞约束：
    只读结构化字段（目标槽 key）与代码算好的 missing，不改写任何文本。

    判得出来就判、判不出来就告警，不硬猜：
      no_question       本轮没有问句
      no_missing        A 类缺失为空 —— 没有该问的题材（丢弃由缺口 2 的规则负责）
      ok                目标槽确实在 A 类缺失里
      target_mismatch   报了目标槽，但它不在 A 类缺失里（G1 记录的「问位置」就是这种）
      target_unknown    没报目标槽，无从判断指向哪个槽（老规划器 / 模型漏填）
    """
    value = str(question or "").strip()
    keys = [str(k).strip() for k in (missing_keys or []) if str(k).strip()]
    if not value:
        return {"judged": False, "ok": False, "reason": "no_question", "target": ""}
    if not keys:
        return {"judged": False, "ok": False, "reason": "no_missing", "target": ""}
    target = str(target_slot or "").strip()
    if not target:
        logger.warning("question_target_unknown origin=%s code=%s missing=%s question=%s",
                       origin, code, keys, value)
        return {"judged": False, "ok": False, "reason": "target_unknown", "target": ""}
    if slot_question_targets_missing(target, keys):
        return {"judged": True, "ok": True, "reason": "ok", "target": target}
    logger.warning("question_target_mismatch origin=%s code=%s target=%s missing=%s question=%s",
                   origin, code, target, keys, value)
    return {"judged": True, "ok": False, "reason": "target_mismatch", "target": target}


def _warn_empty_talk(state: AssistantState, body: str) -> None:
    hits = empty_talk_hits(body)
    if not hits:
        return
    pending = [str(k) for issue in _report_issues(state)
               for k in ((issue or {}).get("report_missing") or [])]
    logger.warning(
        "report_empty_talk hits=%s code=%s report_missing=%s",
        hits, state.get("locked_subcategory"), pending)


def _deliver_report(state: AssistantState, body: str, offer_task: bool) -> dict:
    """把交付给用户的报告正文同时写进 messages 与 draft_report。

    修的是断链：原实现只写 draft_report，而全项目没有任何地方读它 ——
    下一轮的规划器只看得见用户说过什么，看不见上一轮引了哪些法条、下了什么结论，
    于是同一件事会被重新分析、重新检索，甚至引出不同法条（同一段对话两套分析）。
    messages 才是归宿：规划器会把最近的 assistant 轮次一起读进去
    （core/dialogue_understanding.build_planner_messages）。
    draft_report 保留为「本轮交付正文」的记录（既有测试与可观测性读它）。
    """
    return {
        **_append_reply(state, body),
        "draft_report": body,
        "offer_task": offer_task,
    }


# 报告提示词里的去重规则。提成模块常量有两个原因：
#   1) 可以单独钉住它的措辞，不必从整段提示词里捞；
#   2) 它只提「材料里标着…的那一项」而不照抄带方括号的材料标签 ——
#      照抄会让「材料里不该出现某一行的」那类断言被规则文案本身触发（实测踩过）。
REPORT_DEDUP_RULE = (
    "同一条缺失信息不要承载两次：材料里标着「法规适用待确认」的那一项"
    "（会改变法规适用、责任归属或处罚档次），由分情况判断承载；"
    "材料里标着「仍缺信息」的那一项（缺了它处置方向会判错），"
    "由末尾那一个追问承载 —— 已经用分情况判断写过的，不要再问一遍。"
)


def _report_rules(premises_scope: str, preliminary: bool = False,
                  branch: bool = False, followup: bool = False,
                  issue_count: int = 1) -> str:
    """户内不能套「触犯法规」：多数户内报修是燃气公司/物业的维护义务，住户是报修方。

    完整报告是文档（法规和案例要能对照），保留三段式；
    初步报告只是一段判断，不用小标题 —— 强制小标题正是「模板感 / 生硬」的来源。
    """
    indoor = (premises_scope or "public") in {"indoor", "indoor_risk"}
    heading = "相关法规与责任归属" if indoor else "触犯法规"
    indoor_note = (
        "这是户内场景：多数情况下责任在燃气公司、物业或设备方的维护义务，住户是报修方。"
        "不要把它写成用户违法，也不要预设有人违规。"
        if indoor else ""
    )
    # 只有材料里真的出现了 B 类缺失时，才给这段要求：否则这段说明本身会让模型
    # 以为还有信息没确认（也避免把「[法规适用待确认]」这个标签写进无关的提示词）。
    branch_rule = (
        "材料里标了「[法规适用待确认]」的，是缺了也不影响结论和处置方向、"
        "但会改变适用的法规条款、责任归属或处罚档次的那一项。"
        "这种信息不要省略，也不要写「信息尚不完整」「建议进一步核实」这类把核实退回给用户的空话；"
        "要用「若…则…」的分情况判断，把每一种可能各自的适用依据都写出来"
        "（例如：若为长期占用，适用某条、可处罚；若为临时占用，适用另一条、以责令改正为主）。"
    )
    increment = (
        "如果对话历史里你已经给过这个隐患的分析，不要重讲一遍："
        "已经说过的结论用一句话带过，本轮只讲新增信息带来的变化、仍然缺的"
        + ("、以及那一个追问。" if preliminary else "。")
        + "注意是「只输出增量」，不是「换一种说法把同一份分析重讲一遍」。"
    )
    # 去重规则：只描述「同一条信息只承载一次」这层关系，不列禁止词。
    # 为什么不用「A 类不许展开」那种表述：报告里给 A 类写「若长期…若临时…」本身对用户有价值，
    # 真正要避免的只是「同一件事既写成分支、又在末尾问一遍」。
    if preliminary:
        # 内容要求一个都不能少（初步判断 / 仍需确认 / 一个追问 / 建议动作），只是不再用标题表达。
        # 「仍需确认」只允许针对下面列出的待确认问题，不许凭空猜。
        # 追问是决策 (b) 新增的必含块：只允许一个，由 question_limiter(1) 在流上兜住。
        shape = (
            "标注「信息不完整」时不要用任何小标题、不要输出 Markdown 井号或「一、二、三」式分节，"
            "用自然、口语化的两三段话写出来：先说你的初步判断是什么，"
            "再说明目前仍需确认哪些信息（只能针对下面列出的待确认问题，不要凭空猜），"
            "最后用你自己的话追问其中最关键的那一个，并给出建议动作；"
            "整段话最多只能有一个问句，不要问第二个问题。"
        )
    else:
        shape = (
            "标注「信息完整」时用三段式：### 一、" + heading +
            " / ### 二、安全隐患 / ### 三、类似案例。"
            "完整报告里不要提出任何问题，也不要邀请用户补充信息。"
            + ("材料里标着「[法规适用待确认]」的那一项不能写成问句。" if branch else "")
        )
    return (
        "\n本次对话共有 %d 条活动隐患，请逐条覆盖全部隐患，不遗漏任何一条；"
        "焦点只决定输出顺序。" % max(1, int(issue_count or 1))
        + shape + indoor_note + increment + (branch_rule if branch else "")
        + (REPORT_DEDUP_RULE if preliminary else "") +
        "法规和案例必须来自上面的检索结果，没有就写「库内暂未检索到」，不编造。"
        "不要询问是否创建任务，也不要提出上报邀请——这一步由对话流程单独负责。"
    )


def _skill_report_rules(state: AssistantState) -> str:
    parts = []
    for code in state.get("active_skills") or []:
        try:
            section = _skill_registry.load_section(code, "报告约束")
        except Exception as exc:
            logger.error("skill_report_section_load_failed code=%s error=%s",
                         code, type(exc).__name__)
            continue
        if section.strip():
            parts.append(section.strip())
    return "\n\n".join(parts)


def report(state: AssistantState, config=None) -> dict:
    messages = list(state.get("messages", []))
    ask_create = can_offer_task_creation(state)
    draft_future = None
    if ask_create:
        draft_state = dict(state)
        draft_state["messages"] = list(messages)
        draft_future = _TASK_DRAFT_EXECUTOR.submit(
            build_task_draft, draft_state, _cancel_token(config))
    preliminary = _is_preliminary(state)
    skill_report_rules = _skill_report_rules(state)
    ctx = ("\n\n".join(_issue_blocks(state))
           + _report_rules(state.get("premises_scope"), preliminary,
                           branch=bool(report_branch_keys(state)),
                           followup=_followup_pending(state),
                           issue_count=len(_report_issues(state))))
    if skill_report_rules:
        ctx += "\n\n【Skill 报告约束】\n" + skill_report_rules
    # 把 langchain 消息转成 dict，供 _call_llm_stream_events 的 payload 序列化
    dict_msgs = []
    _ROLE_MAP = {"system": "system", "human": "user", "ai": "assistant", "tool": "tool"}
    for m in messages:
        dict_msgs.append({"role": _ROLE_MAP.get(getattr(m, "type", "user"), "user"), "content": getattr(m, "content", "")})
    dict_msgs.append({"role": "user", "content": ctx})
    prefix = _reply_prefix(state)
    events = _report_llm._call_llm_stream_events(
        dict_msgs, cancellation=_cancel_token(config))
    tokens = (text for kind, text in events if kind == "chunk")
    if preliminary:
        # 初步报告逐句流出去：行首井号由执行器零延迟剥掉；追问最多放行一个 ——
        # 决策 (b)：这一档里判断、缺失、追问在同一段话里，所以「一轮最多一个问句」
        # 必须在流上按句计数（question_limiter），不能像普通报告那样整篇放行。
        _emit_chunk(prefix)
        pieces = []
        for piece in guard_stream(tokens, strip_headings=True, questions=question_limiter(1)):
            pieces.append(piece)
            _emit_chunk(piece)
        body = prefix + "".join(pieces)
        tail = preliminary_question_tail(state, body)
        if tail:
            # 模型一个字都没问：补上该小类的固定问句（不静默，留日志）
            logger.info("preliminary_question_fallback code=%s missing=%s",
                        state.get("locked_subcategory"),
                        decision_missing_keys(state, str(state.get("locked_subcategory") or "")))
            _emit_chunk(tail)
            body += tail
        _warn_empty_talk(state, body)
        _warn_redundancy(state, body)
        coverage = preliminary_coverage(body)
        if not all(coverage.values()):
            # 弱层次核对：词面标记漏检是已知的，所以只告警、不改写正文
            logger.warning("preliminary_coverage_missing blocks=%s code=%s",
                           coverage, state.get("locked_subcategory"))
        return _finish_task_draft(
            state, draft_future, _deliver_report(state, body, ask_create))
    # 完整报告也走同一个逐句执行器：项目原则是「同一个约束不要两套判定」。
    # 为什么不用「token 粒度只剥问号」那套：它只处理问号、不管别的约束，以后必然分叉。
    # 问号上限是 0（不是 1）：完整报告里不许出现任何问句，模型多写出来的问句
    # 一律只去掉问号、不丢整句；初步报告那一档仍是 1（要带一个追问）。
    # 行首井号不剥（这一档是文档，三段式标题要保留）。
    buf = []
    if prefix:
        buf.append(prefix)
        _emit_chunk(prefix)
    for piece in guard_stream(tokens, strip_headings=False, questions=question_limiter(0)):
        buf.append(piece)
        _emit_chunk(piece)
    body = "".join(buf)
    _warn_empty_talk(state, body)
    _warn_redundancy(state, body)
    return _finish_task_draft(
        state, draft_future, _deliver_report(state, body, ask_create))


# ---------- 建任务确认闸门（durable human-in-the-loop） ----------
_TASK_DECLINE_MARKERS = ("不需要", "不用了", "不要", "取消", "不建", "不用", "先不用", "否")
_TASK_CONFIRM_EXACT = {
    "需要", "要", "好", "好的", "可以", "行", "没问题", "建", "创建", "上报",
    "是的", "确定", "确认", "嗯", "嗯嗯",
}
_TASK_CONFIRM_PREFIX = (
    "好的", "可以", "那就", "麻烦你", "帮我建", "请建", "创建", "上报",
    "确定", "确认", "没问题", "建", "要", "嗯",
)


def classify_task_reply(message: str) -> str:
    """把用户对"要不要建任务"的回答归成 confirm / decline / other。

    只用精确匹配或前缀匹配，绝不用子串匹配：否则"我要投诉物业"会被当成同意建任务。
    是否已提问、问过没有，都由图的挂起状态表达，不在这里维护。
    """
    text = (message or "").strip()
    if not text:
        return "other"
    if any(marker in text for marker in _TASK_DECLINE_MARKERS):
        return "decline"
    if text in _TASK_CONFIRM_EXACT:
        return "confirm"
    if len(text) <= 12 and text.startswith(_TASK_CONFIRM_PREFIX):
        return "confirm"
    return "other"


def parse_interrupt_reply(raw) -> dict | None:
    """把前端传来的 interrupt_reply JSON 字符串解析成 dict。

    只认 dict：坏 JSON、非 dict、空串一律返回 None，让调用方回落到
    classify_task_reply 的老路径，行为与改造前完全一致。
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _cancel_token(config):
    """取消令牌走 config（不是图状态）：实测并行 Send 分支里同样可见。"""
    return ((config or {}).get("configurable") or {}).get("cancel_token")


def _emit_chunk(text: str) -> None:
    if not text:
        return
    try:
        get_stream_writer()({"chunk": text})
    except Exception:
        pass

def _emit_event(kind: str, payload) -> None:
    """推一个结构化 SSE 事件：前端按 type 分流渲染。

    为什么不用 chunk 传：chunk 是给人读的正文，把“机器要读的字段”（工单 id、
    跳转目标）拼进正文，等于让前端去正则抠字符串 —— 同一条约束两处判定。
    """
    try:
        get_stream_writer()({"event": {"type": kind, "content": payload}})
    except Exception:
        pass


def _clean_task_draft(draft, state: AssistantState) -> dict:
    raw = draft if isinstance(draft, dict) else {}
    locked = set(_locked_majors(state))
    category_list = []
    categories = raw.get("categoryList")
    if isinstance(categories, str):
        categories = [categories]
    elif not isinstance(categories, (list, tuple)):
        categories = []
    for item in categories:
        if not isinstance(item, str):
            continue
        pair = normalize_taxonomy(item)
        if not pair or (locked and pair[0] not in locked):
            continue
        code = format_hazard_type(pair[0], pair[1])
        if code and code not in category_list:
            category_list.append(code)
        if len(category_list) >= 3:
            break

    address = raw.get("address")
    address = address.strip()[:200] if isinstance(address, str) else ""
    description = raw.get("description")
    description = description[:500] if isinstance(description, str) else ""
    severity = raw.get("severity")
    if not (isinstance(severity, int) and not isinstance(severity, bool)
            and severity in (0, 1, 2)):
        severity = 1

    def coord(value):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    district = raw.get("district")
    return {
        "categoryList": category_list,
        "address": address,
        "district": district if isinstance(district, str) else "",
        "description": description,
        "severity": severity,
        "longitude": coord(raw.get("longitude")),
        "latitude": coord(raw.get("latitude")),
        "image_file_id": state.get("image_file_id"),
    }


def task_gate(state: AssistantState) -> Command:
    """中断等待用户决定；恢复值由下一轮请求以 Command(resume=...) 传入。

    这段代码在恢复时整体重跑，所以 interrupt() 之前不能有副作用。
    """
    phase = state.get("task_phase") or "confirm"
    request_id = str(state.get("request_id") or "").strip()
    draft = dict(state.get("task_draft") or {})
    if not draft.get("address"):
        draft["address"] = str(state.get("address_text") or "")
    if draft.get("longitude") is None:
        draft["longitude"] = state.get("picked_longitude")
    if draft.get("latitude") is None:
        draft["latitude"] = state.get("picked_latitude")
    if phase == "address":
        answer = interrupt({
            "type": "ask_address",
            "question": "请提供具体地址（如 XX 市 XX 区 XX 路 XX 小区或明显地标），我好帮你定位并创建隐患任务。",
            "request_id": request_id,
            "draft": draft,
        })
        return Command(
            goto="submit_task",
            update={
                "address_text": str(answer or "").strip(),
                "task_offered": True,
                "request_id": request_id or new_request_id(),
            },
        )
    answer = interrupt({
        "type": "confirm_create_task",
        "question": task_invitation_question(state),
        "issues": _public_issues(state.get("issues") or []),
        "address": str(state.get("address_text") or ""),
        "request_id": request_id,
        "draft": draft,
    })
    if isinstance(answer, dict):
        # 新路径：前端把确认卡片连同改过的草稿 / 地址 / 图选点坐标一起回传
        decision = str(answer.get("decision") or "other")
        supplied_request_id = str(answer.get("request_id") or "").strip()
        if supplied_request_id and request_id and supplied_request_id != request_id:
            _emit_chunk("⚠️ 确认信息已失效，请重新发起建单")
            return Command(goto=END, update={"task_offered": True})
        request_id = request_id or supplied_request_id or new_request_id()
        address = str(answer.get("address") or "").strip()
        longitude = answer.get("longitude")
        latitude = answer.get("latitude")
        update = {"task_offered": True, "request_id": request_id}
        cleaned_draft = None
        if "draft" in answer:
            cleaned_draft = _clean_task_draft(answer.get("draft"), state)
            if not cleaned_draft["categoryList"]:
                _emit_chunk("⚠️ 所选隐患类别不在当前对话范围，暂不创建任务")
                return Command(goto=END, update={
                    "task_offered": True, "task_draft": cleaned_draft,
                })
            update["task_draft"] = cleaned_draft
            address = address or cleaned_draft["address"]
            if longitude is None:
                longitude = cleaned_draft["longitude"]
            if latitude is None:
                latitude = cleaned_draft["latitude"]
        else:
            # 旧前端只回 decision/address：继续走 _extract，不使用报告期草稿。
            update["task_draft"] = {}
        has_coords = (
            isinstance(longitude, (int, float))
            and not isinstance(longitude, bool)
            and isinstance(latitude, (int, float))
            and not isinstance(latitude, bool)
        )
        if address:
            update["address_text"] = address[:200]
        if has_coords:
            update["picked_longitude"] = float(longitude)
            update["picked_latitude"] = float(latitude)
        elif cleaned_draft is not None:
            update["picked_longitude"] = None
            update["picked_latitude"] = None
        if decision == "confirm":
            # 最终地址仍为空（预抽取为空且用户没改）-> 回到地址追问（既有恢复路径）
            final_address = address if cleaned_draft is not None else (
                address or str(state.get("address_text") or "").strip())
            if not final_address:
                return Command(
                    goto="task_gate",
                    update={
                        "task_phase": "address",
                        "task_offered": True,
                        "request_id": request_id,
                    },
                )
            return Command(goto="submit_task", update=update)
        if decision == "decline":
            return Command(goto="close_task", update=update)
        return Command(goto="understand", update=update)
    # 老路径：整段文本回复，回到纯文本分类
    decision = classify_task_reply(answer if isinstance(answer, str) else "")
    request_id = request_id or new_request_id()
    if decision == "confirm":
        if not str(state.get("address_text") or "").strip():
            return Command(
                goto="task_gate",
                update={
                    "task_phase": "address",
                    "task_offered": True,
                    "request_id": request_id,
                    "task_draft": {},
                },
            )
        return Command(
            goto="submit_task",
            update={"task_offered": True, "request_id": request_id, "task_draft": {}},
        )
    if decision == "decline":
        return Command(goto="close_task", update={"task_offered": True})
    return Command(goto="understand", update={"task_offered": True})


def submit_task(state: AssistantState) -> Command:
    from tools.hazard_submit import submit_from_history

    history = [
        {
            "role": "assistant" if isinstance(m, AIMessage) else "user",
            "content": getattr(m, "content", ""),
        }
        for m in (state.get("messages") or [])
        if isinstance(m, (AIMessage, HumanMessage))
    ]
    latest = (state.get("address_text") or "").strip() or (
        history[-1]["content"] if history else ""
    )
    picked_longitude = state.get("picked_longitude")
    picked_latitude = state.get("picked_latitude")
    coords = (
        (picked_longitude, picked_latitude)
        if picked_longitude is not None and picked_latitude is not None
        else None
    )
    image_args = {}
    if state.get("image_file_id") is not None:
        image_args = {
            "image_url": state.get("image_url") or "",
            "image_file_id": state.get("image_file_id"),
        }
    submit_kwargs = {
        "address_hint": state.get("address_text") or "",
        "coords": coords,
        "session_id": state.get("session_id") or "",
        "request_id": state.get("request_id") or "",
        **image_args,
    }
    draft = state.get("task_draft")
    if draft:
        submit_kwargs["draft"] = draft
    result = submit_from_history(
        state.get("user_id"), history, latest, **submit_kwargs)
    action = result.get("action")
    if action == "accepted":
        # MQ 模式：只表示"已受理"，不代表已落库；前端按 request_id 轮询。
        request_id = result.get("requestId")
        _emit_chunk("✅ 已受理，正在创建隐患任务")
        if request_id:
            _emit_event("task_accepted", {"request_id": request_id, "status": "PENDING"})
        return Command(goto=END, update={
            "address_text": "", "task_phase": "", "request_id": "",
            "image_url": "", "image_file_id": None,
        })
    if action == "ask_address":
        return Command(goto="task_gate", update={"task_phase": "address"})
    _emit_chunk("⚠️ " + str(result.get("message")))
    return Command(goto=END, update={"address_text": "", "task_phase": "", "request_id": ""})


def close_task(state: AssistantState) -> dict:
    # 只往 messages 里追加；SSE 桥会把它流出去，避免重复输出
    return {
        "messages": [AIMessage(
            content="好的，那我不建任务。如果还有其他现场情况，直接说就行。"
        )],
        "image_url": "",
        "image_file_id": None,
        "request_id": "",
    }


def after_report(state: AssistantState) -> dict:
    """出报告后、点确认前，把地址预抽出来写进 state，供确认卡片显示。

    这个节点每次只跑一次：刻意放在 task_gate 之外 —— task_gate 恢复时整段会
    重跑，interrupt() 之前的模型调用会执行两次，把地址抽取放里面就白跑一遍。
    """
    if not can_offer_task_creation(state):
        return {}
    update = {}
    if not str(state.get("request_id") or "").strip():
        update["request_id"] = new_request_id()
    if str(state.get("address_text") or "").strip():
        return update
    from tools.hazard_submit import extract_location

    history = [
        {
            "role": "assistant" if isinstance(m, AIMessage) else "user",
            "content": getattr(m, "content", ""),
        }
        for m in (state.get("messages") or [])
        if isinstance(m, (AIMessage, HumanMessage))
    ]
    latest = ""
    for item in reversed(history):
        if item["role"] == "user":
            latest = item["content"]
            break
    update["address_text"] = extract_location(history, latest)
    return update


def route_after_report(state: AssistantState):
    if state.get("offer_task") and not state.get("task_offered"):
        return "task_gate"
    return END


def build_graph(checkpointer=None):
    """编译助手图。checkpointer 由 get_checkpointer() 按 CHECKPOINT_BACKEND 决定。"""
    g = StateGraph(AssistantGraphState)
    g.add_node("begin_turn", begin_turn)
    g.add_node("skill_route", skill_route)
    g.add_node("understand", understand)
    g.add_node("scope_guard", scope_guard)
    g.add_node("route", route)
    g.add_node("search", search)
    g.add_node("retrieve", retrieve)
    g.add_node("evaluate_retrieval", evaluate_retrieval)
    g.add_node("rewrite_query", rewrite_query)
    g.add_node("report", report)
    g.add_node("after_report", after_report)
    g.add_node("task_gate", task_gate)
    g.add_node("submit_task", submit_task)
    g.add_node("close_task", close_task)
    g.add_node("boundary_reply", boundary_reply)
    g.add_node("smalltalk_reply", smalltalk_reply)
    g.add_node("answer_reply", answer_reply)
    g.add_node("fallback_reply", fallback_reply)
    g.add_node("emergency_guidance", emergency_guidance)
    g.add_node("ask_slot_question", ask_slot_question)
    g.set_entry_point("begin_turn")
    g.add_edge("begin_turn", "skill_route")
    g.add_edge("skill_route", "understand")
    g.add_edge("understand", "scope_guard")
    g.add_edge("scope_guard", "route")
    # route 返回 Command(goto=...)，不需要额外的条件边
    g.add_conditional_edges("search", plan_retrieval)
    # 检索自评重试环：扇出汇聚 → 判定 →（不达标）改写检索词回到 search
    g.add_edge("retrieve", "evaluate_retrieval")
    g.add_edge("rewrite_query", "search")
    g.add_edge("report", "after_report")
    g.add_conditional_edges(
        "after_report", route_after_report, {"task_gate": "task_gate", END: END}
    )
    g.add_edge("close_task", END)
    for _reply_node in ("boundary_reply", "smalltalk_reply", "answer_reply",
                        "fallback_reply", "emergency_guidance"):
        g.add_edge(_reply_node, END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


def _checkpoint_backend() -> str:
    """运行时读取后端，便于测试和不改代码切换；非法值按 memory 处理。"""
    value = os.getenv("CHECKPOINT_BACKEND", CHECKPOINT_BACKEND).strip().lower()
    return value if value in {"memory", "redis"} else "memory"


def _build_redis_checkpointer():
    """构造 Redis checkpointer，返回 (saver, error)。

    任何一步失败都不外抛，交给 get_checkpointer() 降级到 InMemorySaver：
    没装 langgraph-checkpoint-redis、Redis 连不上、Redis 没有 RediSearch 模块
    （自建 Redis / redis:7-alpine 没有 FT.* 命令，setup() 会失败）都算在这一类。
    """
    try:
        import redis as redis_module
        from langgraph.checkpoint.redis import RedisSaver
    except Exception as exc:
        # 兼容适配：这套包是可选依赖，没装/版本不对都不影响服务启动
        return None, (
            f"langgraph-checkpoint-redis 不可用: {exc}"
            "（pip install -r requirements.txt 后重启；或先用 CHECKPOINT_BACKEND=memory）"
        )

    try:
        client = redis_module.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD or None,
            db=REDIS_DB,
            decode_responses=False,
            socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
            socket_timeout=REDIS_TIMEOUT_SECONDS,
        )
        saver = RedisSaver(redis_client=client)
    except Exception as exc:
        return None, f"RedisSaver 初始化失败: {exc}"

    try:
        client.ping()
    except Exception as exc:
        return None, f"Redis 连不上 {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}: {exc}"

    try:
        # setup() 建 RediSearch 索引，需要 Redis Stack；幂等，重复调用只补索引。
        saver.setup()
    except Exception as exc:
        # 关键约束：RedisSaver 依赖 RedisJSON + RediSearch（Redis Stack 专属模块），
        # 普通 redis:7-alpine 没有 FT.* / JSON.* 命令，必然走到这里。
        return None, (
            "RedisSaver.setup() 失败（Redis 缺 RediSearch/RedisJSON 模块）: "
            f"{exc}"
            "（换成 redis/redis-stack-server 镜像后再开 CHECKPOINT_BACKEND=redis；"
            "否则多 worker 的 interrupt 状态无法跨进程恢复）"
        )

    return saver, None


_CHECKPOINTER = None
_CHECKPOINTER_KEY = None          # 配置要求的后端（缓存键）
_CHECKPOINTER_EFFECTIVE = None    # 实际生效的后端：redis | memory
_CHECKPOINTER_ERROR = None


def get_checkpointer():
    """按 CHECKPOINT_BACKEND 返回 checkpointer（带缓存，同一个后端只构造一次）。

    memory -> InMemorySaver：进程内，单 worker/本地开发（重启即丢，符合原行为）
    redis  -> RedisSaver  ：跨 worker / 跨重启恢复 interrupt，多副本必须用这个
    """
    global _CHECKPOINTER, _CHECKPOINTER_KEY, _CHECKPOINTER_EFFECTIVE, _CHECKPOINTER_ERROR
    backend = _checkpoint_backend()
    if _CHECKPOINTER is not None and _CHECKPOINTER_KEY == backend:
        return _CHECKPOINTER

    saver, error, effective = None, None, "memory"
    if backend == "redis":
        saver, error = _build_redis_checkpointer()
        if saver is None:
            logger.warning(
                "checkpoint backend=redis 不可用，降级 InMemorySaver"
                "（多 worker 会各存一份，interrupt 跨 worker 恢复不了）: %s",
                error,
            )
        else:
            effective = "redis"
    if saver is None:
        saver = InMemorySaver()

    _CHECKPOINTER = saver
    _CHECKPOINTER_KEY = backend
    _CHECKPOINTER_EFFECTIVE = effective
    _CHECKPOINTER_ERROR = error
    return _CHECKPOINTER


def checkpoint_backend_status() -> dict:
    """给 /api/ai/health 和排障用：配置的后端、实际生效的后端、降级原因。"""
    get_checkpointer()  # 先确保缓存就绪，status 才反映"真的在用哪个"
    backend = _checkpoint_backend()
    effective = _CHECKPOINTER_EFFECTIVE or "memory"
    return {
        "configured": backend,
        "effective": effective,
        "error": _CHECKPOINTER_ERROR,
    }


def clear_thread(user_id: int, session_id: str) -> None:
    """Delete one user's LangGraph checkpoint after authorization was checked."""
    get_checkpointer().delete_thread(_thread_id(user_id, session_id))


def reset_checkpointer() -> None:
    """清空 checkpointer 缓存与图缓存（测试用；生产只在切后端时用）。"""
    global _APP, _CHECKPOINTER, _CHECKPOINTER_KEY, _CHECKPOINTER_EFFECTIVE, _CHECKPOINTER_ERROR
    _APP = None
    _CHECKPOINTER = None
    _CHECKPOINTER_KEY = None
    _CHECKPOINTER_EFFECTIVE = None
    _CHECKPOINTER_ERROR = None


_APP = None


def get_app():
    global _APP
    if _APP is None:
        _APP = build_graph(checkpointer=get_checkpointer())
    return _APP


async def run_stream_events(message: str, history: list[dict], slots: dict,
                            vision_summary: str, session_id: str,
                            max_rounds: int = 5,
                            cancellation: CancellationToken = None,
                            user_id: int = None,
                            selected_major_code: str = "",
                            selected_major_codes=None,
                            interrupt_reply: str = "",
                            image_url: str = "",
                            image_file_id: int = None) -> Generator[tuple, None, None]:
    app = get_app()
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def emit(kind: str, text: str):
        loop.call_soon_threadsafe(q.put_nowait, (kind, text))

    config = {
        "configurable": {
            "thread_id": _thread_id(user_id, session_id),
            "cancel_token": cancellation,
        },
        "recursion_limit": GRAPH_RECURSION_LIMIT,
    }
    initial = build_turn_input(
        session_id, message, vision_summary, selected_major_code,
        selected_major_codes, image_url=image_url, image_file_id=image_file_id,
    )
    initial["user_id"] = user_id


    def produce():
        try:
            snapshot = app.get_state(config)
            # 上一轮停在建任务闸门：用 Command(resume=...) 恢复，
            # 恢复值同时把本轮用户消息并进状态。
            if tuple(snapshot.next or ()) == ("task_gate",):
                phase = snapshot.values.get("task_phase") or "confirm"
                if phase == "address":
                    resume_value = message
                else:
                    # 前端可选的 interrupt_reply（JSON 字符串）优先；坏 JSON 或
                    # 缺失时回落老路径，行为与改造前完全一致。
                    resume_value = (
                        parse_interrupt_reply(interrupt_reply)
                        or {"decision": classify_task_reply(message)}
                    )
                # 结构化确认可以不带 message：不要把占位文案写进对话历史
                resume_update = (
                    {"messages": [HumanMessage(content=message)]} if message else {}
                )
                payload = Command(resume=resume_value, update=resume_update)
            else:
                payload = initial
                if not snapshot.values.get("messages"):
                    seed = seed_messages((history or [])[-max_rounds * 2:])
                    if seed:
                        payload = {**initial, "messages": seed + initial["messages"]}
            seen = set()
            for mode, item in app.stream(payload, config, stream_mode=["updates", "custom"]):
                if mode == "custom":
                    # report 逐 token 写的 {"chunk": text} -> 作为 chunk 流出
                    if isinstance(item, dict) and "chunk" in item:
                        emit("chunk", item["chunk"])
                    elif isinstance(item, dict) and "event" in item:
                        evt = item["event"]
                        emit(evt["type"], evt["content"])
                    continue
                # mode == "updates"：节点级更新
                interrupts = item.get("__interrupt__") if isinstance(item, dict) else None
                if interrupts:
                    value = dict(interrupts[0].value)
                    # 问句仍然以 chunk 流出（现前端直接显示），
                    # 另发结构化 interrupt 事件给前端渲染确认按钮。
                    question = str(value.get("question") or "").strip()
                    if question:
                        emit("chunk", "\n\n" + question)
                    emit("interrupt", value)
                    continue
                for node, update in item.items():
                    if node not in seen:
                        seen.add(node)
                        emit("status", status_text(node, update))
                    if node == "understand" and (
                        (update or {}).get("issues")
                        or (update or {}).get("locked_major")
                        or (update or {}).get("suggested_major_code")
                    ):
                        emit("taxonomy", {
                            "selected_major_code": (update or {}).get(
                                "selected_major_code", selected_major_code
                            ),
                            "major_mismatch": bool(
                                (update or {}).get("major_mismatch")
                            ),
                            "issues": _public_issues((update or {}).get("issues") or []),
                            # 锁定状态与危险标志：给前端渲染"改报"入口，也给量化用
                            "locked_major": (update or {}).get("locked_major", ""),
                            "locked_majors": (update or {}).get("locked_majors", []),
                            "locked_subcategory": (update or {}).get("locked_subcategory", ""),
                            "suggested_major_code": (update or {}).get("suggested_major_code", ""),
                            "immediate_danger": bool((update or {}).get("immediate_danger")),
                            "premises_scope": (update or {}).get("premises_scope", "public"),
                        })
                    # close_task 等节点直接追加的回复也要流出给前端
                    if node in ("close_task",):
                        msgs = (update or {}).get("messages") or []
                        if msgs:
                            content = getattr(msgs[-1], "content", None) or ""
                            if content:
                                emit("chunk", content)
                    # 注意：report 正文现在走 custom 流，这里不再从 updates 取（避免重复）
                if cancellation:
                    cancellation.throw_if_cancelled()
            emit("done", "")
        except Exception as e:
            if isinstance(e, StreamCancelled) or (cancellation and cancellation.is_cancelled()):
                return
            emit("error", str(e))
        finally:
            pass

    worker = asyncio.create_task(asyncio.to_thread(produce))
    try:
        while True:
            try:
                kind, text = await asyncio.wait_for(q.get(), timeout=0.1)
            except asyncio.TimeoutError:
                if cancellation and cancellation.is_cancelled():
                    break
                continue
            yield (kind, text)
            if kind in ("error", "done"):
                break
    finally:
        if not worker.done():
            worker.cancel()





