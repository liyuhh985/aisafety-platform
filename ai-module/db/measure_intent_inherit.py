# -*- coding: utf-8 -*-
"""量用户给的场景：第 1 轮问"是不是隐患"且被判否，第 2 轮用省略句换一件事（"那 X 呢"）。

单看第 2 轮那句话判不出"要哪个产物" —— "X 呢"是省略句，省略的部分在第 1 轮。
所以第 2 轮的 intent 必须靠语境补全。这里量：
  - intent 稳不稳（会不会飘成 report_hazard，于是给报告而用户只是想问是不是）
  - perceived_subcategory 有没有给出焦点
  - scope

只调规划器，不跑整图 —— 要量的是"模型怎么理解这句话"。

用法：python db/measure_intent_inherit.py [重复次数]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

from core import dialogue_understanding as du  # noqa: E402

TURN1 = "路边那个新的井盖是不是隐患"
REPLY1 = ("这不算隐患。新的井盖只要安装到位、没有破损或缺失，就属于正常市政设施，"
          "不需要按安全隐患处理。")
TURN2 = "那人行道旁边摇摇欲坠的广告牌呢"


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    hist = [HumanMessage(content=TURN1), AIMessage(content=REPLY1)]
    print("第 1 轮 = %s  -> 答：不是隐患" % TURN1)
    print("第 2 轮 = %s" % TURN2)
    print("=" * 78)
    counts = {}
    for i in range(1, reps + 1):
        p = du.understand(hist + [HumanMessage(content=TURN2)], "", "")
        intent = p.get("intent") or "-"
        counts[intent] = counts.get(intent, 0) + 1
        codes = [str((x or {}).get("subcategory_code") or "") for x in (p.get("issues") or [])]
        print("run%d  ok=%-5s intent=%-18s perceived_sub=%-22s major=%-14s scope=%-12s issues=%s"
              % (i, bool(p.get("ok")), intent, p.get("perceived_subcategory") or "-",
                 p.get("perceived_major") or "-", p.get("scope") or "-",
                 ",".join(codes) or "-"))
        sys.stdout.flush()
    print("=" * 78)
    print("intent 分布：%s" % counts)
    print("对照：第 1 轮那种「是不是隐患」的问法，按现有节点设计应当进「纯回答」节点；")
    print("      如果第 2 轮飘成 report_hazard，就会出报告 —— 与用户意图不符。")


if __name__ == "__main__":
    main()
