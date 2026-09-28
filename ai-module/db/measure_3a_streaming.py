# -*- coding: utf-8 -*-
"""阶段 3a 实测：应急指引 / 初步判断各流出几块、首块在第几个 token 之后到达。

只读测量：不连网（模型用假 token 流），不改生产代码。
前后对照的做法：同一输入分别跑「现在的实现」和「改回攒整篇的实现」（由外部变异脚本切换代码）。
用法（在 ai-module 下）：python db/measure_3a_streaming.py <标签>
"""
import io
import os
import sys

sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import core.assistant_graph as ag  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402

LABEL = sys.argv[1] if len(sys.argv) > 1 else "current"
TOKEN_SIZE = 3

# 119 在最后一句（线上火灾那条的实际措辞）
FIRE_REPLY_LATE_119 = (
    "请立刻趴低身体、弯腰沿墙根摸索，用湿布捂住口鼻，从没有烟的楼梯或通道向外撤离；"
    "如果下方通道已被浓烟封死，就退回到关严房门的房间，用湿衣物堵住门缝等待。"
    "同时马上拨打119说明所在楼层和被困位置，讲清人数，保持电话畅通以便救援人员联系你。"
    "切勿为拿物品耽误时间，也不要在浓烟中直立奔跑或贸然冲入烟雾，耐心等待消防救援到达。"
)
# 119 在第一句
FIRE_REPLY_EARLY_119 = (
    "请立刻低姿撤离到室外安全地带，并拨打 119 报警。"
    "沿楼梯向下走，不要乘坐电梯。"
    "到楼下后说明楼层和被困人数，等待救援人员。"
)
PRE_REPLY = (
    "楼下消防通道被杂物长期占用，这属于明确的违法行为，参考消防法第28条。"
    "目前仍需确认：占用物具体是什么，是废旧家具、生活垃圾还是私家车。"
    "建议先拍照留证，再向物业或辖区消防部门反映。"
)
PRE_STATE = {
    "messages": [],
    "issues": [{"major_code": "fire", "subcategory_code": "fire_lane_blocked",
                "slots": {"persistence": "长期"}, "missing": ["blocker"]}],
    "categories": ["fire_lane_blocked"],
    "category_results": {"fire_lane_blocked": {"regulation": "消防法第28条", "case": "萍乡案例"}},
    "missing": ["fire_lane_blocked_blocker"],
    "report_mode": "preliminary",
}


def split_tokens(text):
    return [text[i:i + TOKEN_SIZE] for i in range(0, len(text), TOKEN_SIZE)]


def fake_llm(pieces, marks, counter):
    def stream(messages, cancellation=None):
        for index, token in enumerate(pieces, 1):
            marks.append((index, len(counter)))
            yield ("chunk", token)
    return stream


OUT = []


def emit(line=""):
    OUT.append(line)


def run(func, sentences, state, label):
    # 句号也要跟着前一句走，才能复现真实的分句
    pieces = split_tokens("".join(sentences))
    marks, counter = [], []
    ag._report_llm = type("F", (), {
        "_call_llm_stream_events": staticmethod(fake_llm(pieces, marks, counter))})()
    ag.get_stream_writer = lambda: counter.append
    update = func(state)
    final_text = (update["messages"][-1].content if "messages" in update
                  else update["draft_report"])
    chunks = [str(item.get("chunk", "")) for item in counter]
    first_mark = next((index for index, count in marks if count > 0), None)
    emit("[%s]" % label)
    emit("  模型 token 数：%d（每 %d 字一个）" % (len(pieces), TOKEN_SIZE))
    emit("  流出块数：%d" % len(chunks))
    if first_mark is None:
        emit("  首块到达：全部 token 生成完之后")
    else:
        emit("  首块到达：第 %d 个 token 之后（共 %d 个）" % (first_mark - 1, len(pieces)))
    emit("  首块长度：%d 字（全篇 %d 字）" % (len(chunks[0]) if chunks else 0, len(final_text)))
    emit("  首次流出时全篇还差 %d 个 token 没生成"
          % (len(pieces) - (first_mark - 1 if first_mark else len(pieces))))
    emit("  拼接 == 落库文本：%s" % ("".join(chunks) == final_text))
    emit("  任何块不含问号：%s" % all("？" not in c and "?" not in c for c in chunks))
    emit("  任何行不以井号开头：%s" % all(
        not line.lstrip().startswith("#") for c in chunks for line in c.split("\n")))
    emit()


def danger_early(pieces_state):
    return ag.emergency_guidance(pieces_state)


DANGER_STATE = {"messages": [HumanMessage(content="楼道里全是浓烟，人都出不来")]}

run(lambda _s: ag.emergency_guidance(_s), [FIRE_REPLY_LATE_119], DANGER_STATE,
    "应急指引 fire（119 在最后一句，线上实际措辞）")
run(lambda _s: ag.emergency_guidance(_s), [FIRE_REPLY_EARLY_119], DANGER_STATE,
    "应急指引 fire（119 在第一句）")
run(lambda _s: ag.report(dict(_s)), [PRE_REPLY], PRE_STATE, "初步报告")

emit("标签：%s" % LABEL)
text = "\n".join(OUT)
print(text)
if "--append" in sys.argv:
    path = os.path.join("db", "eval_stream_guard.txt")
    with io.open(path, "a", encoding="utf-8", newline="") as handle:
        handle.write(text + "\n")
    print("已追加到 %s" % path)