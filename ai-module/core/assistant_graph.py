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

# report 用不带 tools 的轻量 Agent（流式生成纯文本报告，避免 tools 导致 400）
_report_llm = Agent(
    name="report",
    system_prompt="",
    tools=[],
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

# 否定/转折词：这些词说明类别判断有歧义（"不是X""虽然有X但Y"），交给 LLM 判别而非关键词硬判
_NEGATION_WORDS = ("不是", "并非", "但有", "但是", "其实", "并不", "并不是", "要说")


def _infer_categories(text, vision_category=""):
    # 0) 含否定/转折词 → 交给 LLM 判别（不硬判，避免"不是占道"误判为占道）
    if any(w in text for w in _NEGATION_WORDS):
        llm_cats = _llm_infer_categories(text)
        if llm_cats:
            return llm_cats
        # 模型没判出 → 回退到关键词

    # 晚融合：图算图的类别，文本算文本的类别，最后合并（不再图覆盖文）
    cats = []
    # 1) 图算一票（如果能映射到已知类别）
    if vision_category:
        mapped = _VISION_CATEGORY_MAP.get(vision_category)
        if mapped:
            cats.append(mapped)
    # 2) 文本算一票（关键词打分命中>0）
    hits = [c for c in CATEGORIES if _score_category(c, text) > 0]
    cats = _sort_by_priority(_dedupe(cats + hits))
    if cats:
        return cats
    # 3) 两者都无命中 → 才 LLM 兜底
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


def _llm_extract_slots(message: str, categories: list[str], category_slot_keys: dict) -> dict:
    prompt = (
        "请从用户消息中，按类别抽取能填的槽位。只返回 JSON，没提到的填空字符串。\n"
        "类别槽位定义：\n" +
        "\n".join(f"{cat}: {keys}" for cat, keys in category_slot_keys.items()) +
        f"\n用户消息：{message}"
    )
    try:
        resp = _llm._call_llm(
            [{"role": "system", "content": "你是槽位抽取器"}, {"role": "user", "content": prompt}],
            cancellation=None,
        )
        content = (resp.get("content") or "").strip()
        # 宽松解析：剥 markdown 代码块，截取 {...} 再 json.loads
        if "```" in content:
            content = content.split("```")[1] if content.find("```") < content.rfind("```") else content
            if content.startswith("json"):
                content = content[4:]
        s = content.find("{")
        e = content.rfind("}")
        if s != -1 and e != -1:
            return json.loads(content[s:e+1])
        return json.loads(content)
    except Exception:
        return {}


def _llm_infer_categories(text: str) -> list[str]:
    """判别一句话真正反映哪几个隐患类别（可返回多个）。用于含否定/转折的句子。"""
    prompt = (
        "请判断下面这句话反映的城市安全隐患类别，可以是一个或多个。"
        "只返回类别名，用 / 分隔；没有提到的类别不要列。\n"
        "可选类别：" + " / ".join(CATEGORIES) + "\n文本：" + text
    )
    try:
        resp = _llm._call_llm(
            [{"role": "system", "content": "你是城市安全隐患多类别判别器"}, {"role": "user", "content": prompt}],
            cancellation=None,
        )
        content = (resp.get("content") or "").strip()
    except Exception:
        return []
    # 解析出出现的类别（去重、按优先级排）
    found = [c for c in CATEGORIES if c in content]
    return _sort_by_priority(_dedupe(found))


def _llm_classify(text: str) -> str:
    prompt = (
        "请判断下面这句话主要反映的城市安全隐患类别，只返回一个类别词："
        + " / ".join(CATEGORIES) + "\n文本：" + text
    )
    try:
        resp = _llm._call_llm(
            [{"role": "system", "content": "你是城市安全隐患分类器"}, {"role": "user", "content": prompt}],
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


def _join_text(state) -> str:
    return " ".join(
        getattr(m, "content", "") for m in state.get("messages", [])
        if isinstance(m, (HumanMessage, AIMessage))
    )



def _latest_user_text(state) -> str:
    """取最后一条用户消息的文本（本轮用户最新说的那句）。"""
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage):
            return m.content or ""
    return ""


def route(state: AssistantState) -> dict:
    # 识别只拿本轮最新用户消息（避免历史旧类别被全文捞回）
    user_text = _latest_user_text(state)
    full_text = _join_text(state)
    vision_cat = _extract_vision_category(state.get("vision_summary", ""))

    # 识别（可能多个）类别，并并进已有清单（去重 + 按优先级）
    new_cats = _infer_categories(user_text, vision_cat)
    old_cats = list(state.get("categories") or [])
    cats = _merge_categories(new_cats, old_cats)

    # LLM 抽槽：用全文（含历史），信息越全越好
    slot_keys = {c: [s.key for s in SLOT_SCHEMAS.get(c, [])] for c in cats}
    extracted = _llm_extract_slots(full_text, cats, slot_keys)
    category_slots = add_category_slots(cats, state.get("category_slots") or {}, extracted)

    # 分流转发：防止串类别（如占道槽值里提到 "消防" -> 转到消防）
    categories_after = cats
    for from_cat in list(category_slots.keys()):
        for key in list(category_slots[from_cat].keys()):
            val = category_slots[from_cat].get(key)
            if val:
                res = _relocate(str(val), from_cat, key, categories_after, category_slots)
                if res:
                    categories_after = res["categories"]
                    category_slots = res["category_slots"]

    # 代码重算还缺哪些 critical 槽
    missing = rebuild_missing(categories_after, category_slots)
    can_search = (not missing) or (state.get("clarify_count", 0) >= 3) or state.get("clarify_stopped", False)

    ret = {
        "categories": categories_after,
        "category_slots": category_slots,
        "missing": missing,
        "route_decision": "search" if can_search else "clarify",
    }
    if categories_after and not state.get("active_category"):
        ret["active_category"] = categories_after[0]
        ret["category_index"] = 0
    return ret


def route_decider(state: AssistantState) -> str:
    if state.get("relationship") == "pending" and state.get("missing"):
        return "meta_clarify"
    if (not state.get("missing")) or state.get("clarify_count", 0) >= 3 or state.get("clarify_stopped"):
        return "search"
    return "clarify"

# ---------- clarify（问该类别下一个缺失槽位） ----------
def _llm_phrase(slot_keys, context) -> str:
    prompt = (
        "请把下面要问的槽位，措辞成一句自然、友好、一次只问一个问题的中文问句（不要列序号）。\n"
        f"当前上下文：{context}\n要问的槽：{'、'.join(slot_keys)}\n只输出问句。"
    )
    try:
        resp = _llm._call_llm(
        [{"role": "system", "content": "你是澄清问句生成器"}, {"role": "user", "content": prompt}],
        cancellation=None,
    )
        return (resp.get("content") or "").strip() or "能再具体说说吗？"
    except Exception:
        return "能再具体说说吗？"


def clarify(state: AssistantState) -> dict:
    cats = state.get("categories") or []
    active = state.get("active_category") or (cats[0] if cats else "其他")
    missing = state.get("missing") or []
    # 代码选槽：优先当前类别缺槽，取 top1-2
    active_slots = [m for m in missing if m.startswith(active + "_")]
    chosen = active_slots[:2] if active_slots else missing[:2]
    # LLM 措辞成自然问句
    question = _llm_phrase(chosen, active)
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]
    return {"messages": msgs, "relationship": "", "clarify_count": state.get("clarify_count", 0) + 1}


def meta_clarify(state: AssistantState) -> dict:
    question = _llm_phrase(["判断关系"], state.get("active_category", ""))
    msgs = list(state.get("messages", [])) + [AIMessage(content=question)]
    return {"messages": msgs, "relationship": "pending"}


# ---------- search（类别化检索） ----------
def search(state: AssistantState) -> dict:
    cats = state.get("categories") or []
    results = dict(state.get("category_results") or {})
    for cat in cats:
        kw = _pick_keyword(cat, state.get("category_slots", {}).get(cat, {}))
        reg = _run_tool("search_regulation", kw)
        case = _run_tool("search_cases", kw)
        results[cat] = {"regulation": reg, "case": case}
    return {"category_results": results}


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
    cats = state.get("categories") or []
    results = state.get("category_results") or {}
    vision = state.get("vision_summary") or ""
    lines = []
    for cat in cats:
        r = results.get(cat, {})
        reg = r.get("regulation") or "库内暂未检索到"
        case = r.get("case") or "库内暂未检索到"
        lines.append(
            "[隐患类别] " + cat + "\n"
            "[视觉分析] " + vision + "\n"
            "[检索法规] " + reg + "\n"
            "[检索案例] " + case
        )
    ctx = (
        "\n\n".join(lines) +
        "\n请对每个隐患用一节输出：### 一、触犯法规 / ### 二、安全隐患 / ### 三、类似案例。" +
        "法规和案例必须来自上面检索结果，没有就写「库内暂未检索到」，不编造。" +
        "多隐患时每个隐患精炼、突出结论；法规引用完整准确。信息不足写「信息不足，未确认」。" +
        "最后加一句「需要我按这个情况生成一个整改建议吗？」"
    )
    # 把 langchain 消息转成 dict，供 _call_llm_stream_events 的 payload 序列化
    dict_msgs = []
    _ROLE_MAP = {"system": "system", "human": "user", "ai": "assistant", "tool": "tool"}
    for m in messages:
        dict_msgs.append({"role": _ROLE_MAP.get(getattr(m, "type", "user"), "user"), "content": getattr(m, "content", "")})
    dict_msgs.append({"role": "user", "content": ctx})
    emit = getattr(_stream_local, "emit", None)
    buf = []
    for kind, text in _report_llm._call_llm_stream_events(dict_msgs, cancellation=None):
        if kind == "chunk":
            buf.append(text)
            if emit:
                emit("chunk", text)
    return {"draft_report": "".join(buf)}


def build_graph():
    g = StateGraph(AssistantState)
    g.add_node("route", route)
    g.add_node("meta_clarify", meta_clarify)
    g.add_node("clarify", clarify)
    g.add_node("search", search)
    g.add_node("report", report)
    g.set_entry_point("route")
    g.add_conditional_edges(
        "route", route_decider,
        {"meta_clarify": "meta_clarify", "clarify": "clarify", "search": "search"},
    )
    g.add_edge("meta_clarify", END)   # 问完"同一处/单独"即结束本轮，等用户下一轮
    g.add_edge("clarify", END)        # 问完槽位即结束本轮，等用户下一轮
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
        "categories": [],
        "active_category": "",
        "category_index": 0,
        "category_slots": {},
        "category_results": {},
        "missing": [],
        "relationship": "",
        "clarify_count": 0,
        "clarify_stopped": False,
        "vision_summary": vision_summary,
        "attempts": 0,
    }
    config = {"configurable": {"thread_id": session_id}}

    def produce():
        _stream_local.emit = emit
        try:
            seen = set()
            for item in app.stream(initial, config, stream_mode="updates"):
                for node, update in item.items():
                    if node not in seen:
                        seen.add(node)
                        emit("status", STATUS_TEXT.get(node, "处理中..."))
                    # 澄清节点：把新追加的询问作为 chunk 流出给前端
                    if node in ("clarify", "meta_clarify"):
                        msgs = (update or {}).get("messages") or []
                        if msgs:
                            last = msgs[-1]
                            content = getattr(last, "content", None) or ""
                            if content:
                                emit("chunk", content)
                    # report 节点：直接取 draft_report 作为 chunk 流出（不依赖节点线程的 emit）
                    if node == "report":
                        draft = (update or {}).get("draft_report") or ""
                        if draft:
                            emit("chunk", draft)
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
