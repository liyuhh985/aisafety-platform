# -*- coding: utf-8 -*-
"""应急指引「开场动作前置」的真模型测量：改动前提示词 vs 改动后提示词。

为什么必须用真模型：假 token 流的回复是固定文本，提示词改动对它没有任何影响。
这里的量的是「模型把关键动作放在第几句」，也就是首块延迟的真正决定因素。

只读：只调模型，不改生产代码。用法（在 ai-module 下）：python db/measure_emergency_lead.py [--append]
"""
import io
import math
import os
import sys
import time

sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import core.assistant_graph as ag  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from core.scope_policy import (  # noqa: E402
    covers_emergency_points,
    emergency_guidance_lead,
    emergency_guidance_points,
    emergency_guidance_type,
)
from core.stream_guard import QUESTION_DROP, guard_stream  # noqa: E402

TOKEN_SIZE = 3
CASES = [
    ("fire", "楼道里全是浓烟，人都出不来"),
    ("gas", "我家厨房燃气管道漏气，味道很大"),
    ("earthquake", "地震了，房子一直在晃"),
    ("electric", "有人触电了，现在倒在地上"),
    ("collapse", "围墙坍塌了，有人被压住"),
]


def old_prompt(user_text, kind):
    """改动前的提示词（按改动前的代码逐字重建，可用 git diff 核对）。"""
    point_text = "；".join("/".join(group) for group in emergency_guidance_points(kind))
    return (
        "用户可能正在遭遇即时危险。请用 3~4 句自然、镇定的中文给出现场安全处理指引。\n"
        "必须覆盖这些要点（每条都要说到，措辞自己组织，不要照抄要点里的词）："
        + point_text + "\n"
        "禁止提出任何问题或反问，禁止询问是否创建任务，禁止输出 Markdown 标题，"
        "不要引用法规和案例。\n"
        "用户原话：" + user_text
    )


def new_prompt(user_text, kind):
    """改动后的提示词：直接从节点里抓（跑一次假模型，不连网）。"""
    captured = {}

    def fake(messages, cancellation=None):
        captured["prompt"] = messages[0]["content"]
        yield ("chunk", emergency_guidance_lead(kind))

    original = ag._report_llm
    ag._report_llm = type("F", (), {"_call_llm_stream_events": staticmethod(fake)})()
    ag.get_stream_writer = lambda _item: None
    try:
        ag.emergency_guidance({"messages": [HumanMessage(content=user_text)]})
    finally:
        ag._report_llm = original
    return captured["prompt"]


def real_reply(prompt):
    parts = []
    for kind_of_event, text in ag._report_llm._call_llm_stream_events(
            [{"role": "user", "content": prompt}], cancellation=None):
        if kind_of_event == "chunk":
            parts.append(text)
    return "".join(parts)


def analyze(reply, kind):
    """三套实现的块数与首块 token 位置（句子切分用生产同一套执行器）。"""
    pieces = list(guard_stream([reply], questions=QUESTION_DROP))
    total_tokens = max(1, math.ceil(len(reply) / TOKEN_SIZE))
    ends, cursor = [], 0
    for piece in pieces:
        start = reply.find(piece, cursor)
        if start < 0:
            start = cursor
        cursor = start + len(piece)
        ends.append(cursor)
    tokens_at = [math.ceil(end / TOKEN_SIZE) for end in ends]
    first_cover = None
    for index in range(len(pieces)):
        if covers_emergency_points("".join(pieces[:index + 1]), kind):
            first_cover = index
            break
    source = {
        "buffered": (1, total_tokens),
        "current": (1 + (len(pieces) - 1 - first_cover), tokens_at[first_cover])
        if first_cover is not None else (1, total_tokens),
        "append": (len(pieces), tokens_at[0] if tokens_at else total_tokens),
    }
    return {
        "sentences": len(pieces),
        "first_cover": None if first_cover is None else first_cover + 1,
        "total_tokens": total_tokens,
        "first_sentence": pieces[0] if pieces else "",
        "source": source,
    }


OUT = []


def emit(line=""):
    OUT.append(line)


for kind, user_text in CASES:
    for label, prompt in (("改前提示词", old_prompt(user_text, kind)),
                          ("改后提示词", new_prompt(user_text, kind))):
        started = time.time()
        try:
            reply = real_reply(prompt)
            error = ""
        except Exception as exc:                                     # noqa: BLE001
            reply, error = "", "%s: %s" % (type(exc).__name__, exc)
        elapsed = time.time() - started
        emit("[%s / %s]（%d 秒）" % (kind, label, round(elapsed)))
        if error:
            emit("  调用失败：%s" % error)
            emit()
            continue
        info = analyze(reply, kind)
        info["lead_copied"] = emergency_guidance_lead(kind) in reply
        emit("  句数：%d    覆盖第一次成立：第 %s 句    总 token：%d"
             % (info["sentences"], info["first_cover"] or "未成立", info["total_tokens"]))
        emit("  第一句：%s" % info["first_sentence"])
        emit("  首块 token 位置：改前 %d ｜ 改后 %d ｜ 备选 %d"
             % (info["source"]["buffered"][1], info["source"]["current"][1],
                info["source"]["append"][1]))
        emit("  示范句被逐字照抄：%s"
             % ("是" if info["lead_copied"] else "否（措辞仍是模型自己的）"))
        emit("  块数：改前 %d ｜ 改后 %d ｜ 备选 %d"
             % (info["source"]["buffered"][0], info["source"]["current"][0],
                info["source"]["append"][0]))
        emit()

emit("（真模型测量：模型 = %s）" % ag.MIMO_MODEL)
text = "\n".join(OUT)
print(text)
if "--append" in sys.argv:
    with io.open(os.path.join("db", "eval_stream_guard.txt"), "a", encoding="utf-8", newline="") as handle:
        handle.write("\n===== 真模型：开场动作前置（提示词改动前 vs 后）=====\n" + text + "\n")
    print("已追加到 db/eval_stream_guard.txt")