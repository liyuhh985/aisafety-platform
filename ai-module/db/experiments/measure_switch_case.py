# -*- coding: utf-8 -*-
"""回答用户给的情况一 / 情况三：两轮都换成问「广告牌」，区别只在第 1 轮的模式。

  情况一：第 1 轮 = 问"井盖是不是隐患" → 答"不是"（模式：纯回答）
  情况三：第 1 轮 = "井盖不见了"（真隐患，模式：初步判断 + 追问）
两者第 2 轮都问：那人行道旁边摇摇欲坠的广告牌呢

量三样，分别对应三条不同的轴：
  ① 焦点：perceived_subcategory 有没有给出 facade_fall（"广告牌"自带物件词，属自足型）
  ② 污染：issues 里还有没有 manhole_damage（旧的那条），排第几
  ③ 产物：intent 稳不稳（决定进哪个节点）
另有 ④ 候选数：同一大类里有几条候选 —— 决定「候选唯一才兜底」这条规则生不生效

用法：python db/experiments/measure_switch_case.py [重复次数]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from core import dialogue_understanding as du  # noqa: E402
from core.hazard_taxonomy import SUBCATEGORY_TO_MAJOR  # noqa: E402

OLD = "manhole_damage"
T2 = "那人行道旁边摇摇欲坠的广告牌呢"

SETUPS = [
    ("情况一 判否(纯回答)", "路边那个新的井盖是不是隐患",
     "这不算隐患。新的井盖只要安装到位、没有破损或缺失，就属于正常市政设施。"),
    ("情况三 真隐患(初步+追问)", "路边那个井盖不见了，有人差点掉下去",
     "这是明确的隐患。井盖缺失属于市政设施损坏，行人尤其是夜间有坠落风险。"
     "我先记下来——这个井盖缺失大概是什么时候发现的？"),
]


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print("第 2 轮都是：%s" % T2)
    print("=" * 78)
    for label, t1, r1 in SETUPS:
        hist = [HumanMessage(content=t1), AIMessage(content=r1)]
        print()
        print("### %s" % label)
        print("    第 1 轮 = %s" % t1)
        focus_hit = 0
        for i in range(1, reps + 1):
            p = du.understand(hist + [HumanMessage(content=T2)], "", "")
            codes = [str((x or {}).get("subcategory_code") or "") for x in (p.get("issues") or [])]
            sub = p.get("perceived_subcategory") or ""
            maj = p.get("perceived_major") or ""
            in_major = [c for c in codes if SUBCATEGORY_TO_MAJOR.get(c) == maj] if maj else []
            old_at = codes.index(OLD) if OLD in codes else -1
            ok = sub == "facade_fall"
            focus_hit += 1 if ok else 0
            print("  run%d ok=%-5s intent=%-16s focus=%-18s major=%-10s issues=%-40s 旧类别@%s 同大类候选=%d"
                  % (i, bool(p.get("ok")), p.get("intent") or "-", sub or "-", maj or "-",
                     ",".join(codes) or "-", old_at, len(in_major)))
            sys.stdout.flush()
        print("    -> 焦点命中 facade_fall：%d/%d" % (focus_hit, reps))


if __name__ == "__main__":
    main()
