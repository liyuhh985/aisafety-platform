# -*- coding: utf-8 -*-
"""探针：只看规划器对这一句话输出了什么（scope / issues / perceived_major）。

不改任何东西，只打印。用于定位「规划器漏放」是发生在
  ① 规划器自己判 hazard ② 还是模型判 out_of_scope、但 decide_scope 先看 issues。
"""
import io, json, os, sys, time
sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langchain_core.messages import HumanMessage
import core.dialogue_understanding as du
from core.scope_policy import decide_scope

CASES = [
    ("漏放", "商场里的指示牌歪了"),
    ("漏放", "楼层指示牌挂得太低了"),
    ("对照-本领域", "路口的信号灯不亮了"),
    ("对照-越界", "红烧肉怎么做好吃"),
    ("对照-越界", "Excel 表格怎么加标线"),
]

for i, (tag, text) in enumerate(CASES):
    for rep in range(1, 4):
        t0 = time.time()
        try:
            raw = du.understand([HumanMessage(content=text)])
        except Exception as exc:
            print("%s | r%d | 调用失败 %s" % (tag, rep, exc))
            continue
        dt = time.time() - t0
        plan = du.parse_plan(raw) if isinstance(raw, str) else (raw or {})
        scope = decide_scope(plan, text, "probe-%d-%d" % (i, rep))
        print("=" * 70)
        print("%s | r%d | %.1fs | %s" % (tag, rep, dt, text))
        print("  planner.scope=%r conf=%s perceived_major=%r intent=%r" % (
            plan.get("scope"), plan.get("scope_confidence"),
            plan.get("perceived_major"), plan.get("intent")))
        print("  issues=%s" % json.dumps(plan.get("issues") or [], ensure_ascii=False))
        print("  decide_scope -> %r (%s)" % (scope.get("scope"), scope.get("reason")))
