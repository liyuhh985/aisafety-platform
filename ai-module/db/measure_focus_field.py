# -*- coding: utf-8 -*-
"""量新字段 `perceived_subcategory`（「当前焦点」）够不够用。

背景：锁取的是 `in_major[0]`（issues 里该大类的第一条），实测会被历史拖拽
（db/measure_history_bleed.py：无历史判对 road_surface_collapse，带历史变成
manhole_damage,road_surface_collapse）。修法是加一个与 perceived_major 对称的字段，
直接把「这句话指向的那一件事是哪一个小类」问出来。

两类用例：
  S 自足型 —— 当前这句话自带类别信息，正确答案 = **新的**那一个
  R 指代型 —— 当前这句话没有类别信息，必须靠上下文解析（"那旁边那个呢"）
              这一类是用户特别指出的风险点：字段不能因为"我只看当前这句"而变空

每个用例跑两种条件：无历史 / 带历史。

用法：python db/measure_focus_field.py [每个用例的重复次数]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

import core.assistant_graph as ag  # noqa: E402
from core import dialogue_understanding as du  # noqa: E402

TURN1 = "小区门口那个井盖不见了，晚上有人差点掉下去"
OLD = "manhole_damage"

# (kind, turn2, 期望的 focus；R 类的期望是 None 表示"只要非空就算解析出来了")
CASES = [
    ("S", "往前走那段路面塌下去一大块", "road_surface_collapse"),
    ("S", "路边那盏路灯不亮了", "street_light_pole"),
    ("S", "路口下水道堵了，积水排不出去", "drainage_flood"),
    ("R", "那旁边那个呢", None),
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


def _seed():
    app = ag.build_graph()
    cfg = {"configurable": {"thread_id": "focus-seed"}}
    for _m, _i in app.stream({"session_id": "s", "messages": [HumanMessage(content=TURN1)]},
                             cfg, stream_mode=["updates", "custom"]):
        pass
    v = app.get_state(cfg).values
    msgs = v.get("messages") or []
    return getattr(msgs[-1], "content", "") if msgs else "", v.get("locked_subcategory") or ""


def _one(messages):
    plan = du.understand(messages, "", "")
    focus = plan.get("perceived_subcategory") or ""
    codes = [str((x or {}).get("subcategory_code") or "") for x in (plan.get("issues") or [])]
    return focus, codes, (plan.get("perceived_major") or "")


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    _stub()
    reply, locked = _seed()
    print("历史种子：第 1 轮真图 locked=%s，助手回复 %d 字" % (locked, len(reply)))
    hist = [HumanMessage(content=TURN1), AIMessage(content=reply)]
    tally = {"S_ok": 0, "S_n": 0, "R_ok": 0, "R_n": 0, "bleed": 0, "bleed_n": 0}
    for kind, q2, expect in CASES:
        print()
        print("[%s] Q2 = %s   期望 focus = %s" % (kind, q2, expect or "非空即可"))
        for cond, msgs in (("无历史", [HumanMessage(content=q2)]),
                           ("带历史", hist + [HumanMessage(content=q2)])):
            got = []
            for i in range(reps):
                focus, codes, pmaj = _one(msgs)
                at = codes.index(OLD) if OLD in codes else -1
                ok = (bool(focus) if expect is None else focus == expect)
                got.append((focus, codes, at, ok))
                if kind == "S":
                    tally["S_n"] += 1
                    tally["S_ok"] += 1 if ok else 0
                else:
                    tally["R_n"] += 1
                    tally["R_ok"] += 1 if ok else 0
                if cond == "带历史":
                    tally["bleed_n"] += 1
                    tally["bleed"] += 1 if at >= 0 else 0
                print("   %s run%d focus=%-22s %s  issues=%-44s 旧类别在第 %s 位"
                      % (cond, i + 1, focus or "-", "OK " if ok else "MISS",
                         ",".join(codes) or "-", at))
                sys.stdout.flush()
    print()
    print("=" * 78)
    print("S 自足型 focus 命中 : %d/%d" % (tally["S_ok"], tally["S_n"]))
    print("R 指代型 focus 非空 : %d/%d" % (tally["R_ok"], tally["R_n"]))
    print("带历史时 issues 里仍出现旧类别 : %d/%d" % (tally["bleed"], tally["bleed_n"]))


if __name__ == "__main__":
    main()
