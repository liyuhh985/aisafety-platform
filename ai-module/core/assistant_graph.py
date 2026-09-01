"""LangGraph 助手：动态槽位 + 类别化检索。
route 先按隐患类别（占道/危房/消防通道/高空坠物...）选 slot schema，再决定追问或检索；
search 用「类别 + 槽位」合成关键词，做类别化检索。
```
"""
import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Generator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from core.assistant_agent import ASSISTANT_SYSTEM
from core.agent import Agent
from core.langgraph_state import AssistantState
from core.cancellation import CancellationToken
from tools.assistant_tools import ASSISTANT_TOOLS
from config import MIMO_BASE_URL, MIMO_API_KEY, MIMO_MODEL

_llm = Agent(
    name="assistant",
    system_prompt="",
    tools=ASSISTANT_TOOLS,
    base_url=MIMO_BASE_URL,
    api_key=MIMO_API_KEY,
    model=MIMO_MODEL,
)
_TOOL_MAP = {t.name: t for t in ASSISTANT_TOOLS}
_stream_local = threading.local()

STATUS_TEXT = {
    "route": "正在分析您的咨询...",
    "clarify": "正在补充信息...",
    "search": "正在检索法规与案例...",
    "report": "正在生成结论...",
}


# ====== 类别化槽位 ======

@dataclass
class Slot:
    key: str
    question: str
    critical: bool = True

CATEGORIES = ("占道", "危房", "消防通道", "高空坠物", "井盖/道路", "电气", "施工", "其他")

SLOT_SCHEMAS: dict[str, list[Slot]] = {
    "占道": [
        Slot("behavior", "具体是什么占道？摆摊、还是车辆停放？"),
        Slot("persistence", "是长期占压还是临时停放？"),
        Slot("blocked", "是完全堵死还是部分占用？"),
    ],
    "危房": [
        Slot("structure", "房屋有没有裂缝、倾斜或沉降？"),
        Slot("occupancy", "现在有人在里面居住或使用吗？"),
        Slot("risk", "有没有明显的即时坍塌风险？"),
    ],
    "消防通道": [
        Slot("blocker", "被什么东西占用了？"),
        Slot("persistence", "是长期还是临时？"),
        Slot("impact", "是否影响消防车或人员通行？", critical=False),
    ],
    "高空坠物": [
        Slot("source", "是从哪掉落的（外墙/阳台/广告牌）？"),
        Slot("target", "下面是人行道还是车行道？", critical=False),
        Slot("exposure", "有没有围挡或警告标志？", critical=False),
    ],
    "井盖/道路": [
        Slot("defect", "井盖是缺失、破损还是松动？"),
        Slot("traffic", "是否影响行人或车辆通行？"),
    ],
    "电气": [
        Slot("source", "是漏电、裸露电线还是设备故障？"),
        Slot("contact", "是否可能被人或车辆接触到？"),
        Slot("risk", "有没有冒烟或火花等迹象？"),
    ],
    "施工": [
        Slot("site", "施工区域是否做了围挡？"),
        Slot("safety", "有无安全警示或防护？"),
        Slot("impact", "是否影响行人或车辆通行？", critical=False),
    ],
    "其他": [
        Slot("describe", "能再具体描述一下这个安全隐患是什么吗？"),
    ],
}

CATEGORY_PRIORITY = {
    "危房": 0, "消防通道": 1, "高空坠物": 2, "电气": 3,
    "施工": 4, "占道": 5, "井盖/道路": 6, "其他": 9,
}

CROSS_SLOT_MAP = {
    ("占道", "blocked"): ("消防通道", "impact"),
    ("占道", "persistence"): ("消防通道", "persistence"),
}

def _dedupe(items):
    return list(dict.fromkeys(items))

def _sort_by_priority(cats):
    return sorted(cats, key=lambda c: CATEGORY_PRIORITY.get(c, 9))

def _score_category(cat, text):
    return sum(1 for k in _CATEGORY_KEYWORDS.get(cat, ()) if k in text)

def _infer_categories(text, vision_category=""):
    if vision_category:
        mapped = _VISION_CATEGORY_MAP.get(vision_category)
        if mapped:
            return [mapped]
    hits = [c for c in CATEGORIES if _score_category(c, text) > 0]
    if hits:
        return _sort_by_priority(_dedupe(hits))
    return [_llm_classify(text) or "其他"]

def _merge_categories(new_cats, old_cats):
    return _sort_by_priority(_dedupe(list(old_cats or []) + list(new_cats or [])))


def rebuild_missing(categories, category_slots) -> list[str]:
    out = []
    for cat in categories:
        for s in SLOT_SCHEMAS.get(cat, []):
            if s.critical and not (category_slots.get(cat, {}).get(s.key) or '').strip():
                out.append(f"{cat}_{s.key}")
    return _sort_by_priority(out)

def add_category_slots(state_categories, category_slots, extracted) -> dict:
    cs = {k: dict(v) for k, v in (category_slots or {}).items()}
    for cat, slots in (extracted or {}).items():
        if cat not in state_categories:
            continue
        cs.setdefault(cat, {})
        for k, v in slots.items():
            if v and str(v).strip():
                cs[cat][k] = v
    return cs

def _detect_other_cats(value, from_cat) -> list[str]:
    if not value:
        return []
    return [c for c in CATEGORIES if c != from_cat
            and any(k in value for k in _CATEGORY_KEYWORDS.get(c, ()))]

def _relocate(value, from_cat, key, categories, category_slots):
    hit_cats = _detect_other_cats(value, from_cat)
    if not hit_cats:
        return None
    new_cats = _merge_categories(hit_cats, categories)
    cs = {k: dict(v) for k, v in (category_slots or {}).items()}
    target = CROSS_SLOT_MAP.get((from_cat, key))
    if target and target[0] in hit_cats:
        tcat, tkey = target
        cs.setdefault(tcat, {})[tkey] = value
        if from_cat in cs and key in cs[from_cat]:
            del cs[from_cat][key]
    return {"categories": new_cats, "category_slots": cs}

_CATEGORY_KEYWORDS = {
    "占道": ("占道", "摆摊", "摊位", "车占", "停车", "挡盲道", "占盲道", "盲道"),
    "危房": ("危房", "裂缝", "倾斜", "沉降", "塌", "危楼", "危墙"),
    "消防通道": ("消防通道", "消防车", "消防", "救援通道"),
    "高空坠物": ("高空", "坠物", "掉落", "外墙", "广告牌", "瓷砖", "玻璃"),
    "井盖/道路": ("井盖", "窨井", "路面", "坑", "破损", "塌陷"),
    "电气": ("漏电", "电线", "短路", "火花", "电缆"),
    "施工": ("施工", "工地", "开挖", "脚手架", "围挡"),
}

# 视觉 hazard_category → 我们的类别 映射（vision 优先用）
_VISION_CATEGORY_MAP = {
    "建筑施工": "施工", "占道经营": "占道", "道路交通": "井盖/道路",
    "消防": "消防通道", "建筑结构": "危房", "高空坠物": "高空坠物",
    "用电安全": "电气", "电气": "电气", "施工": "施工", "占道": "占道",
}


def _infer_category(text: str, vision_category: str = "") -> str:
    """类别推断：vision 优先 → 关键词打分 → 打平才 LLM 兜底。
    - 有图：视觉类别能纠正文案歧义（visio 优先）。
    - 关键词：统计每类命中数，唯一最高分且明显领先 → 直接用（省一次 LLM）。
    - 平手/都零分：歧义或未知，调一次 LLM 分类。
    """
    # 0) 有图优先：视觉类别能纠正文案歧义
    if vision_category:
        mapped = _VISION_CATEGORY_MAP.get(vision_category)
        if mapped:
            return mapped
        for cat, keys in _CATEGORY_KEYWORDS.items():
            if any(k in vision_category for k in keys):
                return cat
    # 1) 关键词打分（不再先到先得）
    scores = {}
    for cat, keys in _CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for k in keys if k in text)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    best_cat, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    # 2) 唯一最高分且明显领先 → 用关键词（省一次 LLM）
    if best_score > 0 and best_score > second_score:
        return best_cat
    # 3) 平手 / 都零分 → 一次 LLM 分类（消除歧义）
    return _llm_classify(text) or "其他"


def _llm_classify(text: str) -> str:
    prompt = (
        "请判断下面这句话主要反映的城市安全隐患类别，只返回一个类别词："
        + " / ".join(CATEGORIES) + "\n文本：" + text
    )
    try:
        resp = _llm._call_llm(
            [SystemMessage(content="你是城市安全隐患分类器"), HumanMessage(content=prompt)],
            cancellation=None,
        )
        content = (resp.get("content") or "").strip()
    except Exception:
        return "其他"
    return next((c for c in CATEGORIES if c in content), "其他")


def _extract_vision_category(vision_summary: str) -> str:
    if not vision_summary:
        return ""
    try:
        s = vision_summary
        if "[" in s:
            s = s[s.index("{"):]
        data = json.loads(s)
        return str(data.get("hazard_category", ""))
    except Exception:
        return ""


def _slots_from_text(text: str, category: str) -> dict:
    slots = {}
    if category == "占道":
        if any(k in text for k in ("长期", "天天", "每天都", "一直")):
            slots["persistence"] = "长期"
        if any(k in text for k in ("临时", "偶尔", "一次")):
            slots["persistence"] = "临时"
        if any(k in text for k in ("完全堵死", "堵死", "走不了", "完全占")):
            slots["blocked"] = "完全堵死"
        elif any(k in text for k in ("部分", "能走", "占了一半")):
            slots["blocked"] = "部分占用"
        if any(k in text for k in ("摊", "摆摊", "占道", "停车", "车占", "挡盲道", "占盲道")):
            slots["behavior"] = text[:8]
    elif category == "危房":
        if any(k in text for k in ("裂缝", "开裂", "倾斜", "沉降")):
            slots["structure"] = "有裂缝/倾斜"
        if any(k in text for k in ("有人", "居住", "使用")):
            slots["occupancy"] = "有人"
        if any(k in text for k in ("塌", "坍塌", "危险", "随时")):
            slots["risk"] = "有即时风险"
    return slots


def _missing_in(category: str, slots: dict) -> list:
    schema = SLOT_SCHEMAS.get(category) or SLOT_SCHEMAS["其他"]
    return [s.key for s in schema if not (slots.get(s.key) or "").strip()]


# ---------- route（分类 → schema → missing → clarify/search） ----------
def _join_text(state) -> str:
    return " ".join(
        getattr(m, "content", "") for m in state.get("messages", [])
        if isinstance(m, (HumanMessage, AIMessage))
    )


def route(state: AssistantState) -> dict:
    text = _join_text(state)
    vision_cat = _extract_vision_category(state.get("vision_summary", ""))
    new_cat = _infer_category(text, vision_cat)
    old_cat = state.get("category", "")
    slots = dict(state.get("slots", {}))

    # 类别切换：只保留公共槽（如 persistence），清掉旧类别专属槽（如 behavior/structure）
    if new_cat != old_cat and old_cat:
        old_keys = {s.key for s in SLOT_SCHEMAS.get(old_cat, [])}
        new_keys = {s.key for s in SLOT_SCHEMAS.get(new_cat, [])}
        common = old_keys & new_keys
        slots = {k: v for k, v in slots.items() if k in common}

    slots.update(_slots_from_text(text, new_cat))
    missing = _missing_in(new_cat, slots)
    decision = "search" if not missing else "clarify"
    return {"category": new_cat, "slots": slots, "missing": missing, "route_decision": decision}


def route_decider(state: AssistantState) -> str:
    return state.get("route_decision", "clarify")


# ---------- clarify（问该类别下一个缺失槽位） ----------
def clarify(state: AssistantState) -> dict:
    category = state.get("category", "其他")
    schema = SLOT_SCHEMAS.get(category) or SLOT_SCHEMAS["其他"]
    missing = state.get("missing") or [s.key for s in schema if not (state.get("slots", {}).get(s.key) or "").strip()]
    if not missing:
        return {"messages": list(state.get("messages", []))}
    slot = next((s for s in schema if s.key == missing[0]), schema[0])
    messages = list(state.get("messages", [])) + [AIMessage(content=slot.question)]
    return {"messages": messages}


# ---------- search（类别化检索） ----------
def search(state: AssistantState) -> dict:
    category = state.get("category", "占道")
    keyword = _pick_keyword(category, state.get("slots", {}))
    reg = _run_tool("search_regulation", keyword)
    case = _run_tool("search_cases", keyword)
    return {"regulation_results": reg, "case_results": case}


def _pick_keyword(category: str, slots: dict) -> str:
    parts = [category]
    for key in ("structure", "behavior", "defect", "source", "blocker", "blocked"):
        v = (slots.get(key) or "").strip()
        if v:
            parts.append(v)
    return (" ".join(parts))[:8]


def _run_tool(name: str, keyword: str) -> str:
    tool = _TOOL_MAP.get(name)
    if not tool:
        return "[检索失败] 未知工具"
    try:
        return str(tool.execute(keyword=keyword))
    except Exception as e:
        return f"[检索失败] {e}"


# ---------- report（流式生成） ----------
def report(state: AssistantState) -> dict:
    messages = list(state.get("messages", []))
    reg = state.get("regulation_results") or "[库内暂未检索到]"
    case = state.get("case_results") or "[库内暂未检索到]"
    vision = state.get("vision_summary") or ""
    category = state.get("category", "")
    ctx = (
        f"[隐患类别] {category}\n"
        f"[视觉分析] {vision}\n"
        f"[检索法规] {reg}\n"
        f"[检索案例] {case}\n"
        "请依据上面的检索结果生成三段式：### 一、触犯法规 / ### 二、安全隐患 / ### 三、类似案例。"
        "没有检索到的内容写「库内暂未检索到」，不要编造；最后加一句「需要我按这个情况生成一个整改建议吗？」"
    )
    final_messages = messages + [HumanMessage(content=ctx)]
    emit = getattr(_stream_local, "emit", None)
    buf = []
    for tok in _llm._call_llm_stream_events(final_messages, cancellation=None):
        buf.append(tok)
        if emit:
            emit("chunk", tok)
    return {"draft_report": "".join(buf)}


# ---------- 图 ----------
def build_graph():
    g = StateGraph(AssistantState)
    g.add_node("route", route)
    g.add_node("clarify", clarify)
    g.add_node("search", search)
    g.add_node("report", report)
    g.set_entry_point("route")
    g.add_conditional_edges(
        "route", route_decider,
        {"clarify": "clarify", "search": "search"},
    )
    g.add_conditional_edges(
        "clarify",
        lambda s: "report" if not _missing_in(s.get("category", "其他"), s.get("slots", {})) else "route",
        {"report": "report", "route": "route"},
    )
    g.add_edge("search", "report")
    g.add_edge("report", END)
    return g.compile(checkpointer=InMemorySaver())


_APP = None
def get_app():
    global _APP
    if _APP is None:
        _APP = build_graph()
    return _APP


# ---------- SSE bridge（asyncio.Queue 真流式） ----------
async def run_stream_events(message: str, history: list[dict], slots: dict,
                            vision_summary: str, session_id: str,
                            max_rounds: int = 5,
                            cancellation: CancellationToken = None) -> Generator[tuple, None, None]:
    app = get_app()
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def emit(kind: str, text: str):
        loop.call_soon_threadsafe(q.put_nowait, (kind, text))

    hc_msgs = [SystemMessage(content=ASSISTANT_SYSTEM)]
    for h in (history or [])[-max_rounds * 2:]:
        role = h.get("role")
        if role == "system":
            hc_msgs.append(SystemMessage(content=h.get("content", "")))
        elif role == "user":
            hc_msgs.append(HumanMessage(content=h.get("content", "")))
        elif role == "assistant":
            hc_msgs.append(AIMessage(content=h.get("content", "")))
    hc_msgs.append(HumanMessage(content=message))

    initial = {
        "session_id": session_id,
        "messages": hc_msgs,
        "slots": slots or {},
        "category": "",
        "missing": [],
        "vision_summary": vision_summary,
        "attempts": 0,
    }
    config = {"configurable": {"thread_id": session_id}}

    def produce():
        _stream_local.emit = emit
        try:
            seen = set()
            for item in app.stream(initial, config, stream_mode="updates"):
                for node in item.keys():
                    if node not in seen:
                        seen.add(node)
                        emit("status", STATUS_TEXT.get(node, "处理中..."))
                if cancellation:
                    cancellation.throw_if_cancelled()
            emit("done", "")
        except Exception as e:
            emit("error", str(e))
        finally:
            try:
                del _stream_local.emit
            except Exception:
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
