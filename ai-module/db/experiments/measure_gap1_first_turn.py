# -*- coding: utf-8 -*-
"""缺口 1 实测量：第 1 轮问句 before/after（真模型，只读）。

before = understand 自己产出的问句（以前这就是最终问句）
after  = ask_slot_question 节点接管之后的问句
hit    = after 由模型自报 target_slot，机械判定是否落在 A 类缺失里；
         before 无结构化自报，只能人工判读（非盲）。
"""
import io, os, sys, json, time
sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langchain_core.messages import HumanMessage
import core.assistant_graph as ag
from core.slot_schemas import missing_decision_slots

CASES = [
    "我们小区消防通道长期被私家车占用",
    "楼道里的灭火器早就没压力了，那个水管的箱子也打不开",
    "路边放着几个大桶，也不知道装的什么，有股味儿",
    "楼下垃圾堆成山了，一直没人拉走",
    "商场自动扶梯超期未检，检验合格标志已过期一年",
]

lines = []
for i, text in enumerate(CASES, 1):
    t0 = time.time()
    header = "=" * 72
    lines.append(header)
    lines.append("[%d] 输入：%s" % (i, text))
    try:
        out = ag.understand({"messages": [HumanMessage(content=text)]})
    except Exception as exc:
        lines.append("  understand 失败：%r" % (exc,))
        continue
    code = out.get("locked_subcategory") or ""
    keys = [s.key for s in missing_decision_slots(code, (out.get("category_slots") or {}).get(code) or {})] if code else []
    before = out.get("clarification_question") or ""
    lines.append("  锁定小类：%s   大类：%s" % (code or "（无）", out.get("locked_major") or "（无）"))
    lines.append("  A 类缺失：%s" % (keys or "（无）"))
    lines.append("  本轮动作：%s   danger_veto=%s" % (out.get("next_action"), out.get("danger_veto")))
    lines.append("  before 问句：%s" % (before or "（没问）"))

    state = dict(out)
    state["messages"] = [HumanMessage(content=text)]
    lines.append("  节点是否分流：%s" % ag._should_ask_slot_question(state))
    if ag._should_ask_slot_question(state):
        cand = ag._slot_question_llm(
            missing=keys,
            known_slots=(out.get("category_slots") or {}).get(code) or {},
            subcategory_code=code, user_text=text) or {}
        cmd = ag.ask_slot_question(state)
        upd = cmd.update or {}
        after = upd.get("clarification_question") or ""
        lines.append("  模型自报 target_slot：%s" % (cand.get("target_slot") or "（无）"))
        lines.append("  after  问句：%s" % (after or "（没问）"))
        lines.append("  after  出处：%s" % upd.get("question_source"))
        lines.append("  after  命中 A 类缺失：%s" % ((cand.get("target_slot") or "") in keys))
    else:
        lines.append("  after  问句：%s（节点未分流，同上）" % (before or "（没问）"))
        lines.append("  after  出处：understand（未分流）")
    lines.append("  耗时：%.1fs" % (time.time() - t0))
    lines.append("")

report = "\n".join(lines)
print(report)
open(os.path.join("db", "eval_gap1_first_turn.txt"), "w", encoding="utf-8").write(report + "\n")
print("saved -> db/eval_gap1_first_turn.txt")
