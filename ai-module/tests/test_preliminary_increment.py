# -*- coding: utf-8 -*-
"""阶段 3 + 3b：报告进入对话历史 + 初步报告一次调用产出「判断 + 依据 + 一个追问」。

锁三件事：
  1. 断链修复：report 之后 messages 里能看到那份报告
     （下一轮的规划器据此才知道上一轮引了哪些法条、下了什么结论）；
  2. 决策 (b)：初步报告含「一个指向 A 类缺失槽的追问」，且初步报告一轮最多一个问句
     （完整报告零个问句 —— 用户明确要求完整报告里不许出现任何问句）；
  3. 边界：完整报告（信息齐全）不带追问；危险路径既不进报告也不追问。

诚实说明：文字层只能核对「三块在不在」（词面标记，弱），
「内容是否与上一轮实质重复」没有客观判据 —— 那部分靠提示词 + 人工抽查，
测量脚本 一次性实验脚本（私有归档） 只负责把重合度与法条对照打印出来。
"""
from langchain_core.messages import AIMessage, HumanMessage

import core.assistant_graph as ag
from core.stream_guard import question_limiter

# 检索结果必须是"看起来正常"的：否则会触发检索重试环去调改写模型（联网）。
CASE_OK = (
    "=== 混合检索结果: 「消防通道占用 杂物」(语义3+关键词3) ===\n"
    "\n【结果1】[语义匹配] 小区消防通道被杂物占用\n  类别: 消防安全/消防通道占用\n"
)

PLAN_INCOMPLETE = {
    "ok": True, "intent": "report_hazard", "answer": "", "question": "",
    "needs_search": True, "risk_level": "high",
    "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                "slots": {"persistence": "长期"}}],
    "categories": ["fire_lane_blocked"],
    "category_slots": {"fire_lane_blocked": {"persistence": "长期"}},
}
PLAN_COMPLETE = {
    **PLAN_INCOMPLETE,
    "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                "slots": {"blocker": "杂物", "persistence": "长期"}}],
    "category_slots": {"fire_lane_blocked": {"blocker": "杂物", "persistence": "长期"}},
}
# 固定问句：blocker = 被什么东西占用了？
MISSING_SLOTS = ["blocker"]


def _node_state(**over):
    state = {
        "messages": [],
        "locked_major": "fire",
        "locked_subcategory": "fire_lane_blocked",
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {"persistence": "长期"}, "missing": list(MISSING_SLOTS)}],
        "categories": ["fire_lane_blocked"],
        "category_slots": {"fire_lane_blocked": {"persistence": "长期"}},
        "category_results": {"fire_lane_blocked": {"regulation": "消防法第28条",
                                                   "case": "萍乡案例"}},
        "missing": ["fire_lane_blocked_" + s for s in MISSING_SLOTS],
        "report_mode": "preliminary",
    }
    state.update(over)
    return state


def _stub_models(monkeypatch, report_text):
    monkeypatch.setattr(ag, "_report_llm", type("F", (), {
        "_call_llm_stream_events": staticmethod(
            lambda messages, cancellation=None: iter([("chunk", report_text)]))})())
    monkeypatch.setattr(ag, "_rewrite_llm", type("F", (), {
        "_call_llm": staticmethod(
            lambda messages, cancellation=None: {"content": "消防通道占用 杂物"})})())


def _run_report_node(monkeypatch, state, tokens):
    """直接调 report 节点（不经图），返回 (update, 流出的 chunk 列表, 请求记录)。"""
    sent = []
    captured = []

    def fake_stream(messages, cancellation=None):
        captured.append(messages)
        for token in tokens:
            yield ("chunk", token)

    monkeypatch.setattr(ag, "_report_llm", type("F", (), {
        "_call_llm_stream_events": staticmethod(fake_stream)})())
    monkeypatch.setattr(ag, "get_stream_writer", lambda: sent.append)
    update = ag.report(state)
    return update, sent, captured


def _stream(app, payload, config):
    """跑完一轮（必须消费生成器，否则图根本不执行）。"""
    nodes, chunks = [], []
    for mode, item in app.stream(payload, config, stream_mode=["updates", "custom"]):
        if mode == "updates":
            nodes.extend(item.keys())
        elif isinstance(item, dict) and "chunk" in item:
            chunks.append(item["chunk"])
    return nodes, chunks, app.get_state(config).values


def _run_graph(monkeypatch, plan, report_text, user_text, thread, extra=()):
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(plan))
    monkeypatch.setattr(ag, "_run_tool", lambda name, keyword, cancellation=None: CASE_OK)
    monkeypatch.setattr(ag, "_probe_top1_score", lambda *a, **k: None)
    _stub_models(monkeypatch, report_text)
    app = ag.build_graph()
    config = {"configurable": {"thread_id": thread}}
    payload = {"session_id": "s", "messages": list(extra) + [HumanMessage(content=user_text)]}
    return _stream(app, payload, config)


# ---------------------------------------------------------------- 1. 断链修复

def test_preliminary_report_enters_the_conversation_history(monkeypatch):
    update, sent, _ = _run_report_node(
        monkeypatch, _node_state(),
        ["楼下消防通道被杂物长期占用，这属于违法行为。", "仍需确认占用物是什么。"])

    assert isinstance(update["messages"][-1], AIMessage)
    assert update["messages"][-1].content == update["draft_report"]
    assert "楼下消防通道被杂物长期占用" in update["messages"][-1].content
    # 流给前端的内容 = 落进历史的内容（含代码补上的那一句追问）
    assert "".join(item["chunk"] for item in sent) == update["draft_report"]


def test_full_report_enters_the_conversation_history(monkeypatch):
    state = _node_state(
        report_mode="full", missing=[],
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "杂物", "persistence": "长期"}, "missing": []}],
    )
    update, _sent, _ = _run_report_node(
        monkeypatch, state, ["### 一、触犯法规\n《消防法》第28条。\n"])

    assert isinstance(update["messages"][-1], AIMessage)
    assert update["messages"][-1].content == update["draft_report"]
    assert "《消防法》第28条" in update["messages"][-1].content


def test_the_next_turn_planner_sees_the_previous_report(monkeypatch):
    """第 2 轮的规划器请求里必须能看到第 1 轮的报告正文 —— 这是 3b 的全部意义。"""
    seen = []

    def fake_plan(messages, *args, **kwargs):
        seen.append("".join(getattr(m, "content", "") for m in messages))
        return dict(PLAN_COMPLETE)

    monkeypatch.setattr(ag, "_understand_plan", fake_plan)
    monkeypatch.setattr(ag, "_run_tool", lambda name, keyword, cancellation=None: CASE_OK)
    monkeypatch.setattr(ag, "_probe_top1_score", lambda *a, **k: None)
    _stub_models(monkeypatch, "第1轮的完整分析正文，引用了《消防法》第28条。")
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "increment-2turn"}}

    _nodes, _chunks, first = _stream(app, {
        "session_id": "s",
        "messages": [HumanMessage(content="楼下消防通道被杂物占了，帮我查法规和案例")],
    }, config)
    report_body = first["draft_report"]
    assert report_body and "第1轮的完整分析正文" in report_body
    assert first["messages"][-1].content == report_body

    _nodes2, _chunks2, second = _stream(app, {
        "session_id": "s",
        "messages": [HumanMessage(content="堆了半年了，一直没人管")],
    }, config)
    assert len(seen) >= 2
    assert report_body in seen[1], "第 2 轮的规划器看不到上一轮的报告"
    assert "《消防法》第28条" in seen[1]
    assert second["messages"][-1].content  # 第 2 轮仍然有回复


# ---------------------------------------------------------------- 2. 决策 (b)

def test_preliminary_report_appends_a_question_when_the_model_asks_none(monkeypatch):
    """模型一个字都没问 → 代码补上该小类的固定问句（仍指向 A 类缺失槽）。"""
    update, sent, _ = _run_report_node(
        monkeypatch, _node_state(),
        ["楼下消防通道被杂物占用，这属于违法行为。", "仍需确认占用物是什么。"])

    body = update["draft_report"]
    assert "？" in body or "?" in body
    assert "被什么东西占用了" in body          # fire_lane_blocked 的 blocker 固定问句
    assert body.count("？") == 1
    assert "".join(item["chunk"] for item in sent) == body   # 补的那句也流出去了


def test_preliminary_question_targets_a_decision_class_slot(monkeypatch):
    """追问只针对 A 类缺失；A 类不缺失时一个都不补（B/C 类不消耗用户耐心）。"""
    update, _sent, _ = _run_report_node(
        monkeypatch, _node_state(),
        ["楼下消防通道被杂物占用。"])
    assert "被什么东西占用了" in update["draft_report"]

    # A 类缺失为空（只剩报告级信息）→ 不补问句
    no_decision_missing = _node_state(missing=[], issues=[
        {"major_code": "fire", "subcategory_code": "fire_lane_blocked",
         "slots": {"blocker": "杂物"}, "missing": []}])
    update2, _s2, _ = _run_report_node(monkeypatch, no_decision_missing,
                                       ["楼下消防通道被杂物占用，这属于违法行为。"])
    assert "？" not in update2["draft_report"] and "?" not in update2["draft_report"]


def test_preliminary_keeps_exactly_one_question_when_the_model_asks_several(monkeypatch):
    """一轮最多一个问句：模型多问了，多出来的只去掉问号、不丢句子。"""
    update, _sent, _ = _run_report_node(
        monkeypatch, _node_state(),
        ["楼下通道被占。", "是被什么占用的？", "堆了多久了？", "建议先拍照留证。"])

    body = update["draft_report"]
    assert body.count("？") + body.count("?") == 1
    assert "是被什么占用的？" in body                 # 第一个问句保留
    assert "堆了多久了" in body                      # 第二个问句的内容不丢
    assert "堆了多久了？" not in body


def test_question_limiter_keeps_only_the_first_question():
    from core.stream_guard import guard_stream
    text = "楼下通道被占。是被什么占用的？堆了多久了？建议先拍照。"
    out = "".join(guard_stream([text], strip_headings=False, questions=question_limiter(1)))
    assert out.count("？") == 1
    assert "是被什么占用的？" in out
    assert "堆了多久了" in out and "堆了多久了？" not in out
    # 上限之外的问句是「去问号」，不是「丢整句」：三句内容都还在
    assert "建议先拍照。" in out


# ---------------------------------------------------------------- 3. 硬边界

def _full_state():
    return _node_state(
        report_mode="full", missing=[],
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "杂物", "persistence": "长期"}, "missing": []}],
    )


def test_full_report_forbids_any_question(monkeypatch):
    """完整报告里不许出现任何问句：模型自己写的问句一律只去问号、不丢整句。

    线上实测完整报告末尾混进了模型生成的问句，用户明确要求「完整报告里不许出现
    任何问句」—— 所以上限从 1 收紧到 0（初步报告那一档仍是 1，要带一个追问）。
    """
    tokens = ["### 一、触犯法规\n《消防法》第28条。",
              "仍需确认通道净宽，能实测一下吗？",
              "另外，物业收到过通知吗？"]
    update, sent, captured = _run_report_node(monkeypatch, _full_state(), tokens)
    body = update["draft_report"]

    assert "".join(item["chunk"] for item in sent) == body      # 拼接等于落库文本
    assert body.count("？") + body.count("?") == 0              # 一个问号都没有
    assert "能实测一下吗" in body and "物业收到过通知吗" in body   # 只去问号，句子保留
    assert "能实测一下吗？" not in body and "物业收到过通知吗？" not in body
    assert "最多只能提一个问句" not in captured[0][-1]["content"]


def test_full_report_strips_the_question_mark_from_a_model_question(monkeypatch):
    """新增回归：完整报告里「…是哪一家？」这种问句，问号被去掉、句子保留。"""
    tokens = ["### 一、触犯法规\n《消防法》第28条。\n",
              "这个消防栓的产权或者管理责任单位是哪一家？\n",
              "### 二、安全隐患\n消防栓被遮挡。"]
    update, _sent, _captured = _run_report_node(monkeypatch, _full_state(), tokens)
    body = update["draft_report"]

    assert "？" not in body and "?" not in body
    assert "这个消防栓的产权或者管理责任单位是哪一家" in body   # 句子保留，只去问号


def test_full_report_rules_forbid_questions_and_followup_wording():
    """新行为：完整报告的规则里既不许留「提一个问句」的口子，也不许出现「追问」字样。"""
    text = ag._report_rules("public", preliminary=False, branch=True, followup=True)
    assert "提一个问句" not in text
    assert "追问" not in text
    assert "不要提出任何问题" in text
    assert "不能写成问句" in text          # B 类那一项要写分情况判断，不许写成问句

    # 初步报告那一档不受影响：仍然带一个追问
    prelim = ag._report_rules("public", preliminary=True, branch=False, followup=True)
    assert "追问" in prelim
    assert "最多只能有一个问句" in prelim


def test_full_report_does_not_append_the_slot_question(monkeypatch):
    """模型一个问句都没提时，完整档也不补问句（兜底只属于初步档）。"""
    update, _sent, _captured = _run_report_node(
        monkeypatch, _full_state(), ["### 一、触犯法规\n《消防法》第28条。"])
    body = update["draft_report"]
    assert body.count("？") + body.count("?") == 0
    assert "被什么东西占用了" not in body


def test_preliminary_prompt_requires_increment_and_a_single_question(monkeypatch):
    _update, _sent, captured = _run_report_node(
        monkeypatch, _node_state(), ["正文。"])
    prompt = captured[0][-1]["content"]
    assert "最多只能有一个问句" in prompt
    assert "只输出增量" in prompt                    # 不是「换一种说法重讲」
    assert "###" not in prompt                       # 初步报告仍然不给小标题模板


def test_full_prompt_also_carries_the_increment_rule(monkeypatch):
    state = _node_state(
        report_mode="full", missing=[],
        issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                 "slots": {"blocker": "杂物", "persistence": "长期"}, "missing": []}],
    )
    _update, _sent, captured = _run_report_node(monkeypatch, state, ["正文。"])
    assert "只输出增量" in captured[0][-1]["content"]


def test_preliminary_coverage_checks_the_three_blocks():
    covered = ag.preliminary_coverage("初步看这属于占用消防通道；仍需确认堆了多久，能说说吗？")
    assert covered == {"judgment": True, "missing": True, "question": True}
    plain = ag.preliminary_coverage("通道被占了。")
    assert plain["question"] is False


def test_danger_path_never_asks_and_never_reports(monkeypatch):
    """危险场景：不进检索/报告/建单，产物里一个问号都没有（不追问、也不做安全确认）。"""
    monkeypatch.setattr(ag, "_understand_plan", lambda *a, **k: dict(PLAN_INCOMPLETE))
    _stub_models(monkeypatch, "请立刻低姿撤离到室外空旷处，用湿毛巾捂住口鼻，并拨打 119。")
    app = ag.build_graph()
    config = {"configurable": {"thread_id": "danger-no-ask"}}
    nodes, _chunks, values = _stream(app, {
        "session_id": "s", "messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]}, config)
    assert "emergency_guidance" in nodes
    for forbidden in ("search", "report", "task_gate"):
        assert forbidden not in nodes, forbidden
    answer = values["messages"][-1].content
    assert "119" in answer
    assert "？" not in answer and "?" not in answer