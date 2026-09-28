# -*- coding: utf-8 -*-
"""缺口 1 补充样本：专挑"更像会缺 A 类槽"的第 1 轮输入。"""
import io, os, sys, time
sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langchain_core.messages import HumanMessage
import core.assistant_graph as ag
from core.slot_schemas import missing_decision_slots

CASES = [
    "工地上没有围挡，也没人管",
    "有人被困在电梯里了",
    "公共厕所旁边的路灯不亮了",
    "小区外墙的墙皮一直往下掉",
    "路边有个井盖不见了",
    "路上被人堆了建筑垃圾，车都过不去",
    "楼道里的消火栓坏了",
    "配电箱的门开着，电线露在外面",
]

lines = []
for i, text in enumerate(CASES, 1):
    t0 = time.time()
    lines.append("=" * 72)
    lines.append("[B%d] 输入：%s" % (i, text))
    try:
        out = ag.understand({"messages": [HumanMessage(content=text)]})
    except Exception as exc:
        lines.append("  understand 失败：%r" % (exc,))
        continue
    code = out.get("locked_subcategory") or ""
    keys = [s.key for s in missing_decision_slots(code, (out.get("category_slots") or {}).get(code) or {})] if code else []
    before = out.get("clarification_question") or ""
    lines.append("  锁定小类：%s" % (code or "（无）"))
    lines.append("  A 类缺失：%s" % (keys or "（无）"))
    lines.append("  本轮动作：%s   danger_veto=%s" % (out.get("next_action"), out.get("danger_veto")))
    lines.append("  before 问句：%s" % (before or "（没问）"))
    state = dict(out)
    state["messages"] = [HumanMessage(content=text)]
    divert = ag._should_ask_slot_question(state)
    lines.append("  节点是否分流：%s" % divert)
    if divert:
        cand = ag._slot_question_llm(
            missing=keys,
            known_slots=(out.get("category_slots") or {}).get(code) or {},
            subcategory_code=code, user_text=text) or {}
        upd = ag.ask_slot_question(state).update or {}
        after = upd.get("clarification_question") or ""
        lines.append("  模型自报 target_slot：%s" % (cand.get("target_slot") or "（无）"))
        lines.append("  after  问句：%s" % (after or "（没问）"))
        lines.append("  after  出处：%s" % upd.get("question_source"))
        lines.append("  after  命中 A 类缺失：%s" % ((cand.get("target_slot") or "") in keys))
    else:
        lines.append("  after  问句：%s（未分流）" % (before or "（没问）"))
    lines.append("  耗时：%.1fs" % (time.time() - t0))

report = "\n".join(lines)
print(report)
open(os.path.join("db", "eval_gap1_first_turn_batch2.txt"), "w", encoding="utf-8").write(report + "\n")
print("saved -> db/eval_gap1_first_turn_batch2.txt")
