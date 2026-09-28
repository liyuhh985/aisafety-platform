# -*- coding: utf-8 -*-
"""阶段 3a：流式约束执行器。

验收对应关系：
  1. 应急指引 / 初步判断恢复多块流出，且首块早于整篇生成完（test_*_streams_*）
  2. 两个报告产物同一条规则：至多一个问句（多出来的只去问号、不丢句）、
     初步判断任意行不以 # 开头
  3. 句末符被 token 边界切开（test_*_split_across_tokens*）
  4. 问号在句中 / 单独成句 → 整句丢掉，后续句子照常放出
  5. 覆盖核对仍然生效（test_*_fallback_*）
外加：执行器的语义必须和改动前的正则实现逐字一致（test_matches_the_previous_regex_*）。
"""
import re

import pytest
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag
import core.stream_guard as sg
from core.scope_policy import covers_emergency_points, emergency_guidance_fallback

DANGER_FIRE = "楼道里全是浓烟，人都出不来"


def _tracked(tokens, pulled):
    """记录「生成器实际被拉走了几个 token」——用来证明首块不必等整篇。"""
    for token in tokens:
        pulled.append(token)
        yield token


# ---------- 改动前的实现：留作回归参照，执行器必须和它逐字一致 ----------
_LEGACY_SPLIT = re.compile(r"(?<=[。！!；;？?\n])")
_LEGACY_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]*", re.MULTILINE)


def _legacy_strip_questions(text):
    kept = []
    for sentence in _LEGACY_SPLIT.split(str(text or "")):
        if any(mark in sentence for mark in ("？", "?")):
            continue
        kept.append(sentence)
    return "".join(kept).replace("？", "").replace("?", "").strip()


def _legacy_strip_headings(text):
    return _LEGACY_HEADING.sub("", str(text or "")).strip()


# ---------- 1. 句级放行：一句到齐就放，不必等整篇 ----------

def test_a_full_stop_split_across_tokens_does_not_hold_the_first_chunk():
    pulled = []
    stream = sg.guard_stream(_tracked(["请撤离到室外并拨打 119。", "\n", "第二段话。"], pulled))
    assert next(stream) == "请撤离到室外并拨打 119。"
    assert pulled == ["请撤离到室外并拨打 119。"]          # 后面的 token 根本还没被拉走
    assert list(stream) == ["\n", "第二段话。"]


def test_a_question_mark_split_across_tokens_still_drops_the_whole_sentence():
    """问号在下一个 token 里也必须等它到齐再判 —— 不能「看着目前没有就发」。"""
    pulled = []
    stream = sg.guard_stream(_tracked(
        ["需要我帮你建一条任务", "吗？", "请立刻撤离并拨打 119。"], pulled))
    assert next(stream) == "请立刻撤离并拨打 119。"
    assert pulled == ["需要我帮你建一条任务", "吗？", "请立刻撤离并拨打 119。"]
    pytest.raises(StopIteration, next, stream)


def test_a_partial_sentence_is_not_released_before_its_end():
    pulled = []
    stream = sg.guard_stream(_tracked(["请立刻撤离到室外", "并拨打 119 报警。"], pulled))
    assert next(stream) == "请立刻撤离到室外并拨打 119 报警。"


def test_a_trailing_fragment_without_any_sentence_end_is_flushed_at_close():
    assert list(sg.guard_stream(["请立刻撤离到室外，拨打 119"])) == ["请立刻撤离到室外，拨打 119"]


def test_an_empty_token_does_not_release_anything():
    assert list(sg.guard_stream(["", "请撤离。", ""])) == ["请撤离。"]


# ---------- 2. 问号：整句丢掉（drop）/ 只去字符（strip）/ 原样（keep） ----------

def test_question_sentence_is_dropped_and_the_next_sentence_still_goes_out():
    out = list(sg.guard_stream(["这样对吗？", "请照做。"]))
    assert out == ["请照做。"]
    assert "这样对吗" not in "".join(out)


def test_no_released_chunk_ever_contains_a_question_mark():
    tokens = [
        "请立刻撤离到室外。",
        "你知道该往哪跑吗？",
        "记住 119?再想一遍。",
        "照做就行。",
    ]
    chunks = list(sg.guard_stream(tokens))
    assert chunks, "至少要有句子放出来"
    for chunk in chunks:
        assert "？" not in chunk and "?" not in chunk, chunk


def test_strip_policy_keeps_the_sentence_and_only_removes_the_mark():
    out = sg.enforce("这样对吗？请照做。", strip_headings=False, questions=sg.QUESTION_STRIP)
    assert out == "这样对吗请照做。"
    assert "？" not in out and "?" not in out


def test_keep_policy_leaves_questions_alone():
    text = "需要确认：被什么东西占用了？"
    assert sg.enforce(text, strip_headings=False, questions=sg.QUESTION_KEEP) == text


def test_an_unknown_question_policy_is_rejected():
    with pytest.raises(ValueError):
        list(sg.guard_stream(["请撤离。"], questions="whatever"))


# ---------- 3. 行级：行首井号必须被剥掉（且不必等整行） ----------

def test_heading_split_across_tokens_is_stripped_from_every_line():
    chunks = list(sg.guard_stream(
        ["#", "## 一、初步", "判断\n", "楼下通道被占。", "\n", "### 二、仍需确认\n", "还要知道被什么占。"],
        questions=sg.QUESTION_KEEP))
    for chunk in chunks:
        for line in chunk.split("\n"):
            assert not line.lstrip().startswith("#"), chunk
    joined = "".join(chunks)
    assert "一、初步判断" in joined and "二、仍需确认" in joined     # 只削井号，内容不动


def test_heading_prefix_is_stripped_even_when_the_headings_are_split():
    chunks = list(sg.guard_stream(["###", " ", "一、判断\n", "正文。"], questions=sg.QUESTION_KEEP))
    assert "".join(chunks) == "一、判断\n正文。"


def test_a_hash_that_is_not_at_a_line_start_is_left_alone():
    assert "".join(sg.guard_stream(["价格 #3 元。"], questions=sg.QUESTION_KEEP)) == "价格 #3 元。"


# ---------- 4. 执行器 vs 改动前的正则实现（逐字一致） ----------

CORPUS = [
    "",
    "请立刻撤离到室外并拨打 119 报警。",
    "### 一、初步判断\n楼下通道被占。\n### 二、仍需确认\n被什么占的。",
    "这样对吗？请照做。",
    "你在几楼？",
    "？。",
    "需要确认：被什么占用？\n建议尽快处理。",
    "   ### 缩进标题\n正文。",
    "第一行\r\n### 标题\r\n正文。",
    "#",
    "####### 七个井号",
    "正文\n\n\n结尾没有标点",
]


def test_a_multi_token_stream_matches_the_previous_regex_question_filter():
    """token 边界不能改变判定结果 —— 提前放行会把该丢的内容漏出去。"""
    tokens = ["需要我帮你建一条任务", "吗？", "请立刻撤离到室外并拨打 119。"]
    assert "".join(sg.guard_stream(tokens)) == _legacy_strip_questions("".join(tokens))


def test_a_multi_token_stream_matches_the_previous_regex_heading_filter():
    tokens = ["#", "## 一、初步", "判断\n", "正文。"]
    assert "".join(sg.guard_stream(tokens, questions=sg.QUESTION_KEEP)) == \
        _legacy_strip_headings("".join(tokens))


@pytest.mark.parametrize("text", CORPUS)
def test_matches_the_previous_regex_question_filter(text):
    assert sg.enforce(text, strip_headings=False, questions=sg.QUESTION_DROP).strip() == \
        _legacy_strip_questions(text)


@pytest.mark.parametrize("text", CORPUS)
def test_matches_the_previous_regex_heading_filter(text):
    assert sg.enforce(text, strip_headings=True, questions=sg.QUESTION_KEEP).strip() == \
        _legacy_strip_headings(text)


# ---------- 5. 节点集成：应急指引 ----------

def _run_guidance(monkeypatch, model_tokens):
    sent = []

    def fake_stream(messages, cancellation=None):
        for token in model_tokens(sent):
            yield ("chunk", token)

    monkeypatch.setattr(ag, "_report_llm", type("F", (), {
        "_call_llm_stream_events": staticmethod(fake_stream)})())
    monkeypatch.setattr(ag, "get_stream_writer", lambda: sent.append)
    update = ag.emergency_guidance(
        {"messages": [HumanMessage(content=DANGER_FIRE)]})
    return update["messages"][-1].content, sent


def test_emergency_guidance_streams_sentence_by_sentence(monkeypatch):
    tokens = [
        "请立刻低姿撤离到室外安全地带，并拨打 119 报警。",
        "不要为取回物品返回室内。",
        "到楼下等待救援人员。",
    ]
    content, sent = _run_guidance(monkeypatch, lambda _sent: list(tokens))
    chunks = [item["chunk"] for item in sent]
    assert len(chunks) > 1, chunks
    assert chunks[0] != content and len(chunks[0]) < len(content)
    assert "".join(chunks) == content
    for chunk in chunks:
        assert "？" not in chunk and "?" not in chunk


def test_emergency_guidance_first_chunk_arrives_before_the_model_finishes(monkeypatch):
    def tokens(sent):
        yield "请立刻低姿撤离到室外安全地带，并拨打 119 报警。"
        assert sent, "第二句还没生成，第一句就该已经流给前端了"
        yield "不要为取回物品返回室内。"

    _run_guidance(monkeypatch, tokens)


def test_emergency_guidance_drops_a_question_arriving_in_a_later_token(monkeypatch):
    tokens = [
        "请立刻撤离到室外并拨打 119 报警。",
        "需要我帮你建一条任务",
        "吗？",
    ]
    content, sent = _run_guidance(monkeypatch, lambda _sent: list(tokens))
    joined = "".join(item["chunk"] for item in sent)
    assert "需要我帮你建" not in joined and "？" not in joined
    assert "119" in joined
    assert joined == content


def test_emergency_guidance_fallback_is_still_prepended_when_nothing_covers(monkeypatch):
    """覆盖核对和去问号是咬合的两个机制：丢句丢到不覆盖 → 前置该类型兜底句。"""
    content, sent = _run_guidance(monkeypatch, lambda _sent: ["你在几楼？", "尽快处理。"])
    assert content.startswith(emergency_guidance_fallback("fire"))
    assert covers_emergency_points(content, "fire")
    chunks = [item["chunk"] for item in sent]
    assert chunks == [content], "没覆盖时全程不放行，最后一次性流出" 
    for chunk in chunks:
        assert "？" not in chunk and "?" not in chunk


def test_emergency_guidance_with_no_model_output_still_says_something(monkeypatch):
    content, sent = _run_guidance(monkeypatch, lambda _sent: [])
    assert content == emergency_guidance_fallback("fire")
    assert "119" in content


# ---------- 6. 节点集成：报告（初步 / 完整走同一条流式规则） ----------

def _preliminary_state(**overrides):
    state = {
        "messages": [],
        "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                    "slots": {"persistence": "长期"}, "missing": ["blocker"]}],
        "categories": ["fire_lane_blocked"],
        "category_results": {"fire_lane_blocked": {"regulation": "消防法第28条",
                                                   "case": "萍乡案例"}},
        "missing": ["fire_lane_blocked_blocker"],
        "report_mode": "preliminary",
    }
    state.update(overrides)
    return state


# 完整报告的覆盖：没有 A 类缺失 → _is_preliminary 为假，走文档那一档
FULL_OVERRIDES = dict(
    report_mode="full",
    issues=[{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
             "slots": {"blocker": "杂物", "persistence": "长期"}, "missing": []}],
    missing=[],
)


def _run_report(monkeypatch, model_tokens, **state_overrides):
    sent = []

    def fake_stream(messages, cancellation=None):
        for token in model_tokens(sent):
            yield ("chunk", token)

    monkeypatch.setattr(ag, "_report_llm", type("F", (), {
        "_call_llm_stream_events": staticmethod(fake_stream)})())
    monkeypatch.setattr(ag, "get_stream_writer", lambda: sent.append)
    update = ag.report(_preliminary_state(**state_overrides))
    return update["draft_report"], sent


def test_preliminary_report_streams_sentence_by_sentence(monkeypatch):
    tokens = [
        "楼下消防通道被杂物长期占用，这属于明确的违法行为。",
        "目前仍需确认：占用物具体是什么。",
        "建议先拍照留证再向物业反映。",
    ]
    draft, sent = _run_report(monkeypatch, lambda _sent: list(tokens))
    chunks = [item["chunk"] for item in sent]
    assert len(chunks) > 1, chunks
    assert chunks[0] != draft and len(chunks[0]) < len(draft)
    assert "".join(chunks) == draft


def test_preliminary_report_first_chunk_arrives_before_the_model_finishes(monkeypatch):
    def tokens(sent):
        yield "楼下消防通道被杂物长期占用。"
        assert sent, "第二句还没生成，第一句就该已经流给前端了"
        yield "建议先拍照留证。"

    _run_report(monkeypatch, tokens)


def test_preliminary_report_headings_never_reach_the_client(monkeypatch):
    tokens = ["### 一、初步", "判断\n", "楼下通道被占。", "\n", "### 二、仍需确认\n", "被什么占的。"]
    draft, sent = _run_report(monkeypatch, lambda _sent: list(tokens))
    assert "###" not in draft
    for item in sent:
        for line in str(item["chunk"]).split("\n"):
            assert not line.lstrip().startswith("#"), item


# 旧不变式「初步报告里一个问号都没有」**已作废**（决策 b）：初步报告必须含一个追问，
# 否则用户永远不知道自己漏了什么。新不变式把两个产物统一成同一条规则：**至多一个问句**，
# 上限之外多出来的问句只去问号、不丢整句（报告里那段是内容，丢整句等于制造误判）。
@pytest.mark.parametrize("overrides", [None, FULL_OVERRIDES], ids=["preliminary", "full"])
def test_report_chunks_carry_at_most_one_question(monkeypatch, overrides):
    tokens = ["楼下通道被占。", "仍需确认：被什么东西占用了？", "堆了多久了？", "建议先拍照留证。"]
    draft, sent = _run_report(monkeypatch, lambda _sent: list(tokens), **(overrides or {}))
    body = "".join(str(item["chunk"]) for item in sent)

    assert body == draft                              # 拼接等于落库文本
    assert body.count("？") + body.count("?") == 1     # 至多一个问句
    assert "仍需确认" in draft and "被什么东西占用" in draft
    assert "堆了多久了" in draft                       # 第二个问句只去问号，内容还在
    assert "堆了多久了？" not in draft
    assert "建议先拍照留证。" in draft


# 旧不变式「完整报告仍是逐 token 原样流出」**已作废**（决策 2）：问号是句级特征，
# 必须在流上按句判定，而项目原则是「同一个约束不要两套判定」—— 所以完整报告也走同一套
# 逐句执行器（不再为它单开一条 token 粒度剥问号的旁路）。保住的不变式：
# 三段式标题照原样出去、任意 chunk 拼接等于落库文本、首块不必等整篇生成完。
def test_full_report_streams_sentence_by_sentence_and_keeps_headings(monkeypatch):
    def tokens(sent):
        yield "### 一、触犯法规\n"
        assert sent, "第二句还没生成，第一句就该已经流给前端了"
        yield "消防法第28条。\n### 二、安全隐患\n通道被占。"

    draft, sent = _run_report(monkeypatch, tokens, **FULL_OVERRIDES)
    chunks = [item["chunk"] for item in sent]

    assert len(chunks) > 1                             # 逐句，不再是一个 token 一块
    assert "".join(chunks) == draft                     # 拼接等于落库文本
    assert chunks[0] == "### 一、触犯法规\n"            # 标题原样保留（不剥）
    assert "### 一、触犯法规" in draft and "### 二、安全隐患" in draft