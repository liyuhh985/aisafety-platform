# -*- coding: utf-8 -*-
"""抢锁的**决定性**测量：新旧隐患同属一个大类时，锁会不会被旧的那个抢走。

前两版实验的教训：
  v1 用「商场指示牌」造"被拒的锁" —— 真实规划器按提示词要求 issues 直接留空，造不出来，A/B 无差异。
  v2 量了 issues 里旧小类的**位置** —— 但那是**原始顺序**，而锁取的是 `in_major[0]`，
     已经按 `major_code == locked_major` 过滤过。旧隐患属于**别的**大类时抢不走锁（v2 里
     fire_lane_blocked 排在 municipal 的 manhole 前面，却不会赢）。

所以只看一种情形：旧、新两个小类**同属一个大类**。本脚本用 井盖/道路（municipal）：
  第 1 轮 manhole_damage（井盖不见）→ 锁上
  人为把锁清空（模拟"锁为空"：回滚后 / 新会话带历史）
  第 2 轮 road_surface_collapse（路面塌陷）→ 看最终锁到哪个

这把锁清空是**人为**的，原因：本实验要隔离的是"规划器在有空锁 + 有隐患历史时怎么选"，
不是"锁是怎么没的"。锁没了的路径（回滚 / 新会话）与规划器看到什么无关 ——
它只读 messages（最近 12 条）+ 几个 system 段。

用法：python db/experiments/measure_lock_regrab3.py [重复次数]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langchain_core.messages import HumanMessage  # noqa: E402

import core.assistant_graph as ag  # noqa: E402

TURN1 = "小区门口那个井盖不见了，晚上有人差点掉下去"
TURN2 = "往前走那段路面塌下去一大块"
CASE_OK = "=== mixed ===\n\n【结果1】[语义匹配] x\n  类别: 市政/井盖缺失\n"

CLEARED = {"locked_major": "", "locked_subcategory": "", "categories": [],
           "issues": [], "missing": [], "category_slots": {}}


def _stub():
    ag._slot_question_llm = lambda **k: {"question": "能再具体描述一下吗？", "target_slot": ""}
    ag._run_tool = lambda name, keyword, cancellation=None: CASE_OK
    ag._probe_top1_score = lambda *a, **k: None
    ag._report_llm = type("F", (), {"_call_llm_stream_events": staticmethod(
        lambda messages, cancellation=None: iter([("chunk", "（略）")]))})()
    ag._rewrite_llm = type("F", (), {"_call_llm": staticmethod(
        lambda messages, cancellation=None: {"content": "井盖 缺失"})})()


def _turn(app, cfg, text):
    und = {}
    for mode, item in app.stream({"session_id": "s", "messages": [HumanMessage(content=text)]},
                                 cfg, stream_mode=["updates", "custom"]):
        if mode == "updates":
            for node, update in item.items():
                if node == "understand":
                    und = update or {}
    return und, app.get_state(cfg).values


def main():
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    _stub()
    print("第 1 轮 = %s" % TURN1)
    print("第 2 轮 = %s" % TURN2)
    print("=" * 78)
    stole = 0
    for i in range(1, repeats + 1):
        app = ag.build_graph()
        cfg = {"configurable": {"thread_id": "regrab3-%d" % i}}
        u1, v1 = _turn(app, cfg, TURN1)
        old = u1.get("locked_subcategory") or ""
        t1_issues = [str((x or {}).get("subcategory_code") or "") for x in (u1.get("issues") or [])]

        # 人为清空锁（模拟"锁为空"），保留 messages 不动
        app.update_state(cfg, dict(CLEARED))

        u2, v2 = _turn(app, cfg, TURN2)
        t2_issues = [(str((x or {}).get("subcategory_code") or ""),
                      str((x or {}).get("major_code") or "")) for x in (u2.get("issues") or [])]
        new_locked = u2.get("locked_subcategory") or ""
        hij = bool(old) and new_locked == old
        stole += 1 if hij else 0
        print("run%d  T1 issues=%-24s locked=%-20s" % (i, ",".join(t1_issues) or "-", old))
        print("      T2 issues=%-46s -> locked=%-20s %s"
              % (",".join("%s(%s)" % c for c in t2_issues) or "-", new_locked,
                 "<<< 被旧类别抢走" if hij else ""))
        sys.stdout.flush()
    print("=" * 78)
    print("汇总：%d/%d 次，锁被**上一轮那个小类**抢走（用户问的新东西被忽略）" % (stole, repeats))


if __name__ == "__main__":
    main()
