# -*- coding: utf-8 -*-
"""应急指引的产出顺序：关键动作必须在第一句。

为什么需要这一条：首块要等「必含要点覆盖成立」才能放出去（兜底句必须是前缀，不变式不动），
所以首块的延迟完全取决于**模型把关键动作放在第几句**。约束措辞顺序比改兜底位置更省 ——
既拿到低延迟，又不拿安全换速度。

这里锁三件事：
  1. 提示词里确实有"第一句说全要点"的顺序约束，且带上该类型的开场动作为示范；
  2. 开场动作**本身**就覆盖该类型全部必含要点（以后谁改了要点或开场动作，这句会红）；
  3. 代码对"关键动作前置"的产出反应正确：首块 = 第一句，而不是攒到第二、三句。
"""
import io
import re
import sys

import pytest
from langchain_core.messages import HumanMessage

import core.assistant_graph as ag
from core.scope_policy import (
    EMERGENCY_GUIDANCE_TYPES,
    covers_emergency_points,
    emergency_guidance_fallback,
    emergency_guidance_lead,
    emergency_guidance_points,
    emergency_guidance_type,
)

CASE_TEXT = {
    "fire": "楼道里全是浓烟，人都出不来",
    "gas": "我家厨房燃气管道漏气，味道很大",
    "earthquake": "地震了，房子一直在晃",
    "electric": "有人触电了，现在倒在地上",
    "collapse": "围墙坍塌了，有人被压住",
}
TOKEN_SIZE = 3


def _capture_prompt(monkeypatch, text):
    captured = {}

    def fake(messages, cancellation=None):
        captured["prompt"] = messages[0]["content"]
        yield ("chunk", emergency_guidance_lead(emergency_guidance_type(text)))

    monkeypatch.setattr(ag, "_report_llm", type("F", (), {
        "_call_llm_stream_events": staticmethod(fake)})())
    monkeypatch.setattr(ag, "get_stream_writer", lambda _item: None)
    ag.emergency_guidance({"messages": [HumanMessage(content=text)]})
    return captured["prompt"]


# ---------- 1. 提示词里的顺序约束 ----------

@pytest.mark.parametrize("kind", sorted(CASE_TEXT))
def test_prompt_demands_the_key_actions_in_the_first_sentence(monkeypatch, kind):
    prompt = _capture_prompt(monkeypatch, CASE_TEXT[kind])
    assert "第一句" in prompt
    assert emergency_guidance_lead(kind) in prompt          # 该类型的开场动作作为示范
    assert "顺序要求" in prompt


def test_prompt_says_not_to_leave_the_key_actions_for_later(monkeypatch):
    prompt = _capture_prompt(monkeypatch, CASE_TEXT["fire"])
    assert "不要" in prompt and "留到后面" in prompt


def test_unknown_type_prompt_still_carries_a_lead_example(monkeypatch):
    """识别不出类型时也要有开场动作示范（否则这句约束落不到地上）。"""
    prompt = _capture_prompt(monkeypatch, "楼道里堆了很多纸箱")
    assert emergency_guidance_lead("") in prompt


# ---------- 2. 开场动作本身必须覆盖该类型全部要点 ----------

@pytest.mark.parametrize("kind", sorted(CASE_TEXT) + [""])
def test_the_lead_action_alone_covers_every_required_point(kind):
    """这条是"模型照着写就能在第一句达成覆盖"的**代码保证**。

    以后谁改了 points 或改了开场动作，只要两者不再对齐，这里立刻红 ——
    否则提示词里的示范句式会变成一句"看起来对、其实覆盖不了"的空话。
    """
    lead = emergency_guidance_lead(kind)
    assert lead
    assert covers_emergency_points(lead, kind), lead


@pytest.mark.parametrize("kind", sorted(EMERGENCY_GUIDANCE_TYPES))
def test_the_lead_action_is_not_the_fallback_sentence(kind):
    """开场动作是给模型的示范，兜底句是代码兜底 —— 两者不能是同一句，
    否则提示词等于让模型照抄模板（措辞就死了）。"""
    assert emergency_guidance_lead(kind) != emergency_guidance_fallback(kind)


def test_every_type_has_its_own_lead_action():
    leads = [emergency_guidance_lead(kind) for kind in EMERGENCY_GUIDANCE_TYPES]
    assert len(set(leads)) == len(leads)


# ---------- 3. 代码对"关键动作前置"的产出反应正确 ----------

def _lead_first_reply(kind):
    """按提示词要求写：第一句说全要点，后面两句展开。"""
    tail = {
        "fire": ("撤离时用湿毛巾捂住口鼻，沿墙根低姿移动。",
                 "不要为取回物品返回室内，也不要乘坐电梯。"),
        "gas": ("开窗后不要开灯、不要打火，也别在现场打电话。",
                "到室外空气流通处再联系燃气公司抢修。"),
        "earthquake": ("晃动时先就地躲避，别急着往楼下跑。",
                       "余震期间远离窗户、吊挂物和外墙。"),
        "electric": ("断电前不要用手去拉触电的人。",
                     "等专业救援到场前，保持伤者平躺并注意保暖。"),
        "collapse": ("不要自行搬动被压住的构件，以免二次伤害。",
                     "在安全区域等待专业人员到场施救。"),
    }[kind]
    return [emergency_guidance_lead(kind) + "。", tail[0], tail[1]]


def _split(text):
    return [text[i:i + TOKEN_SIZE] for i in range(0, len(text), TOKEN_SIZE)]


@pytest.mark.parametrize("kind", sorted(CASE_TEXT))
def test_the_first_chunk_is_exactly_the_first_sentence(monkeypatch, kind):
    """关键动作前置时，首块 = 第一句（不是攒两三句），且此后逐句流出。"""
    sentences = _lead_first_reply(kind)
    pieces = _split("".join(sentences))
    sent, marks, produced = [], [], []

    def fake(messages, cancellation=None):
        for index, token in enumerate(pieces, 1):
            marks.append((index, len(sent)))
            produced.append(token)
            yield ("chunk", token)

    monkeypatch.setattr(ag, "_report_llm", type("F", (), {
        "_call_llm_stream_events": staticmethod(fake)})())
    monkeypatch.setattr(ag, "get_stream_writer", lambda: sent.append)
    update = ag.emergency_guidance({"messages": [HumanMessage(content=CASE_TEXT[kind])]})

    chunks = [item["chunk"] for item in sent]
    assert chunks[0] == sentences[0], chunks          # 首块就是第一句
    assert len(chunks) == len(sentences)              # 之后逐句流出
    assert "".join(chunks) == update["messages"][-1].content

    first_at = next(index for index, count in marks if count > 0)
    sentence_one_tokens = len(_split(sentences[0]))
    assert first_at - 1 == sentence_one_tokens, (first_at - 1, sentence_one_tokens)


@pytest.mark.parametrize("kind", sorted(CASE_TEXT))
def test_the_first_chunk_alone_already_carries_every_required_point(monkeypatch, kind):
    """首块放出时就已覆盖必含要点 —— 用户拿到第一块就能看到该做什么。

    这条由"攒到覆盖为止"的放行规则保证；配合上面的顺序约束，
    覆盖点就落在第一句，而不是最后一段。
    """
    sentences = _lead_first_reply(kind)
    pieces = _split("".join(sentences))
    sent = []

    def fake(messages, cancellation=None):
        for token in pieces:
            yield ("chunk", token)

    monkeypatch.setattr(ag, "_report_llm", type("F", (), {
        "_call_llm_stream_events": staticmethod(fake)})())
    monkeypatch.setattr(ag, "get_stream_writer", lambda: sent.append)
    update = ag.emergency_guidance({"messages": [HumanMessage(content=CASE_TEXT[kind])]})

    chunks = [item["chunk"] for item in sent]
    assert covers_emergency_points(chunks[0], kind), chunks[0]
    assert len(chunks[0]) < len(update["messages"][-1].content)
    assert not any("？" in chunk or "?" in chunk for chunk in chunks)


def test_a_lead_ordered_reply_no_longer_needs_the_fallback(monkeypatch):
    """关键动作前置 → 覆盖在首句成立 → 兜底句不会被前置（既不冗余也不慢）。"""
    sentences = _lead_first_reply("fire")
    pieces = _split("".join(sentences))
    sent = []

    def fake(messages, cancellation=None):
        for token in pieces:
            yield ("chunk", token)

    monkeypatch.setattr(ag, "_report_llm", type("F", (), {
        "_call_llm_stream_events": staticmethod(fake)})())
    monkeypatch.setattr(ag, "get_stream_writer", lambda: sent.append)
    content = ag.emergency_guidance(
        {"messages": [HumanMessage(content=CASE_TEXT["fire"])]})["messages"][-1].content
    assert not content.startswith(emergency_guidance_fallback("fire"))


def test_points_are_still_all_given_to_the_model(monkeypatch):
    """顺序约束不能挤掉"必须覆盖什么" —— 要点清单必须还在提示词里。"""
    prompt = _capture_prompt(monkeypatch, CASE_TEXT["gas"])
    for group in emergency_guidance_points("gas"):
        for word in group:
            if word in prompt:
                break
        else:
            raise AssertionError("要点组没进提示词：%r" % (group,))