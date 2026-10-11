# -*- coding: utf-8 -*-
"""对照实验：同一句第 2 轮的话，**有**隐患历史 vs **没有**历史，规划器判出的小类会不会不同。

为什么要这个对照：
  measure_lock_regrab3 跑出 4/4"锁被旧类别抢走"，但那是因为第 2 轮 issues 里**只有一条**
  `manhole_damage` —— 规划器把"路面塌陷"判成了"井盖缺失"。这可能是两种原因里的一种：
    (a) 历史污染：上一轮在聊井盖，于是这一轮也按井盖理解   ← 抢锁的根因
    (b) 分类能力：它本来就不区分"路面塌陷"和"井盖缺失"     ← 与历史无关
  不设对照就无法区分。所以每个 Q2 跑两遍：带历史 / 不带历史。

用法：python db/experiments/measure_history_bleed.py [每个用例的重复次数]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

import core.assistant_graph as ag  # noqa: E402
from core import dialogue_understanding as du  # noqa: E402

TURN1 = "小区门口那个井盖不见了，晚上有人差点掉下去"
TURN2S = [
    "往前走那段路面塌下去一大块",
    "路边那盏路灯不亮了",
    "路口下水道堵了，积水排不出去",
]
CASE_OK = "=== mixed ===\n\n【结果1】[语义匹配] x\n  类别: 市政/井盖缺失\n"


def _stub():
    ag._slot_question_llm = lambda **k: {"question": "能再具体描述一下吗？", "target_slot": ""}
    ag._run_tool = lambda name, keyword, cancellation=None: CASE_OK
    ag._probe_top1_score = lambda *a, **k: None
    ag._report_llm = type("F", (), {"_call_llm_stream_events": staticmethod(
        lambda messages, cancellation=None: iter([("chunk", "（略）")]))})()
    ag._rewrite_llm = type("F", (), {"_call_llm": staticmethod(
        lambda messages, cancellation=None: {"content": "井盖 缺失"})})()


def _seed_reply():
    app = ag.build_graph()
    cfg = {"configurable": {"thread_id": "bleed-seed"}}
    for _m, _i in app.stream({"session_id": "s", "messages": [HumanMessage(content=TURN1)]},
                             cfg, stream_mode=["updates", "custom"]):
        pass
    msgs = app.get_state(cfg).values.get("messages") or []
    return getattr(msgs[-1], "content", "") if msgs else "", app.get_state(cfg).values


def _codes(plan):
    return ",".join(str((x or {}).get("subcategory_code") or "")
                    for x in (plan.get("issues") or [])) or "-"


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    _stub()
    reply, v = _seed_reply()
    print("第 1 轮（真图）：locked=%s" % (v.get("locked_subcategory") or ""))
    print("  助手回复前 80 字：%s" % reply[:80].replace("\n", " "))
    print()
    history = [HumanMessage(content=TURN1), AIMessage(content=reply)]
    diff = 0
    total = 0
    for q2 in TURN2S:
        print("Q2 = %s" % q2)
        base = []
        for i in range(reps):
            p = du.understand([HumanMessage(content=q2)], "", "")
            base.append(_codes(p))
        with_h = []
        for i in range(reps):
            p = du.understand(history + [HumanMessage(content=q2)], "", "")
            with_h.append(_codes(p))
        print("   无历史 : %s" % " | ".join(base))
        print("   带历史 : %s" % " | ".join(with_h))
        changed = any(b != h for b in base for h in with_h)
        print("   -> %s" % ("**历史改变了判断**" if changed else "一致（历史没影响）"))
        diff += 1 if changed else 0
        total += 1
        sys.stdout.flush()
    print("=" * 78)
    print("汇总：%d/%d 个用例里，有历史改变了规划器判出的小类" % (diff, total))
    print("（若为 0，则 measure_lock_regrab3 的 4/4 是分类能力问题，不是抢锁）")


if __name__ == "__main__":
    main()
