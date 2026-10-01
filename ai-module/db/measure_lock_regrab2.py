# -*- coding: utf-8 -*-
"""量根因：会话里已经聊过隐患 A，用户下一句换了一个**别的**东西 B 时，
规划器输出的 issues 里会不会**同时**带上 A，以及 A 排在第几。

为什么直接调规划器而不跑整图：
  - 抢锁的机制是 `locked_subcategory = in_major[0]`（取 issues 里该大类的第一条）。
    只要规划器把 A 也输出进来且排在前面，任何"锁为空"的时刻都会锁错。
  - 整图那一圈（scope_guard / route / 各产物节点）与这个问题无关，只会让每次运行慢几十秒。
  - 「锁为空」这个前提取材自别的路径（回滚、或新会话带历史），不影响规划器看到什么：
    它读的是 messages（最近 12 条）+ 几个 system 段。

第 1 轮用**真图**跑一次拿到真实的助手回复（抢锁的诱因很可能就是那段回复里详细聊了 A），
之后只重复第 2 轮，每次一遍规划器调用。

用法：python db/measure_lock_regrab2.py [重复次数]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

import core.assistant_graph as ag  # noqa: E402
from core import dialogue_understanding as du  # noqa: E402

TURN1 = "楼道消防通道被纸箱占了"
# 第 2 轮：换一个**别的**东西问（都与 fire_lane_blocked 不同类）
TURN2S = [
    "小区门口那个井盖不见了，挺危险的",
    "楼下那盏路灯不亮了，晚上挺黑",
    "电梯困人了，有人还在里面",
]
CASE_OK = "=== mixed ===\n\n【结果1】[语义匹配] x\n  类别: 消防安全/消防通道占用\n"


def _stub():
    ag._slot_question_llm = lambda **k: {"question": "能再具体描述一下吗？", "target_slot": ""}
    ag._run_tool = lambda name, keyword, cancellation=None: CASE_OK
    ag._probe_top1_score = lambda *a, **k: None
    ag._report_llm = type("F", (), {"_call_llm_stream_events": staticmethod(
        lambda messages, cancellation=None: iter([("chunk", "（略）")]))})()
    ag._rewrite_llm = type("F", (), {"_call_llm": staticmethod(
        lambda messages, cancellation=None: {"content": "消防 通道"})})()


def real_turn1_reply():
    app = ag.build_graph()
    cfg = {"configurable": {"thread_id": "regrab-seed"}}
    for _m, _i in app.stream({"session_id": "s", "messages": [HumanMessage(content=TURN1)]},
                             cfg, stream_mode=["updates", "custom"]):
        pass
    v = app.get_state(cfg).values
    msgs = v.get("messages") or []
    reply = getattr(msgs[-1], "content", "") if msgs else ""
    return v.get("locked_subcategory") or "", reply, v.get("issues") or []


def main():
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    _stub()
    locked, reply, issues = real_turn1_reply()
    print("第 1 轮（真图）：locked=%s" % locked)
    print("  规划器给的 issues = %s" % [i.get("subcategory_code") for i in issues])
    print("  助手回复长度 = %d 字，前 90 字：%s" % (len(reply), reply[:90].replace("\n", " ")))
    print()

    history = [HumanMessage(content=TURN1), AIMessage(content=reply)]
    print("-" * 78)
    print("第 2 轮：只调规划器，看 issues 里有没有第 1 轮那个小类、排第几")
    print("-" * 78)
    for q2 in TURN2S:
        print("Q2 = %s" % q2)
        for i in range(repeats):
            plan = du.understand(history + [HumanMessage(content=q2)], "", "")
            codes = [str((x or {}).get("subcategory_code") or "")
                     for x in (plan.get("issues") or [])]
            at = codes.index(locked) if locked and locked in codes else -1
            print("   run%d  issues=%-52s old_at=%s  perceived_major=%s"
                  % (i + 1, ",".join(codes) or "-", at, plan.get("perceived_major")))
            sys.stdout.flush()
    print()
    print("-" * 78)
    print("判读：old_at=0 表示旧小类排在第一位 —— 只要此时锁是空的（回滚后 / 新会话带历史），")
    print("      它就会被锁上，用户问的新东西反而被忽略。")


if __name__ == "__main__":
    main()
