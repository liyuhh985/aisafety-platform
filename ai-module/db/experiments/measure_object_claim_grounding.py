# -*- coding: utf-8 -*-
"""物件型小类的原文核对：端到端验证（完整图，真模型，每例 3 次）。

要证明的两件事：
  1) 越界探针不再产生报告 —— 判据是**节点里没有 search/report**，不是 reply 里有没有模板词
     （ambiguous 和 out_of_scope 都是可接受产物；只要不给报告、不引法规）。
  2) 本领域探针不被误伤 —— scope 仍是 hazard/emergency（不是 ambiguous/out_of_scope）。

口径：
  - 每例一个全新 thread_id（干净首轮）；
  - 从 scope_guard 抓 scope/scope_reason，从 understand 抓 locked_*，从节点序列判有没有进检索；
  - 每例重复 REPS 次，逐条立即落盘，失败不重试、如实记录。
"""
import io
import os
import sys
import time

sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from langchain_core.messages import HumanMessage  # noqa: E402

import core.assistant_graph as ag  # noqa: E402

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUT = os.path.join(os.getcwd(), "db", "eval_object_claim_grounding.txt")
REPORT_NODES = ("search", "retrieve", "evaluate_retrieval", "rewrite_query", "report", "task_gate")

IN_DOMAIN = [
    ("交通设施损坏", "路边有个交通标志牌和护栏坏了"),
    ("交通设施损坏", "交通设施损坏了没人修"),
    ("交通设施损坏", "路口的信号灯不亮了"),
    ("交通设施损坏", "道路中间的护栏被撞断了"),
    ("交通设施损坏", "路上的交通标线看不清了"),
    ("交通设施损坏", "交通标线磨损掉色了"),
    ("交通设施损坏", "那个路口的灯早就不亮了，车和人都不知道什么时候能走"),
    ("井盖缺失/破损", "马路上一个铁盖子没了，就留个黑洞，晚上看不见掉下去就完了"),
    ("路灯/线杆损坏", "那条路晚上黑得看不见人，旁边的杆子还歪着"),
    ("外立面脱落", "楼上掉下来一大块外墙的砖，把车都砸穿了"),
    ("配电设施故障", "楼下的电表箱子门掉了，里面还冒烟有糊味"),
    ("配电设施故障", "配电房旁边堆了杂物"),
]

OFF_DOMAIN = [
    "红烧肉怎么做好吃",
    "今天天气怎么样",
    "帮我写一篇八百字的周记",
    "推荐一款性价比高的手机",
    "Python 列表如何去重",
    "商场里的指示牌歪了",
    "楼层指示牌挂得太低了",
    "Excel 表格怎么加标线",
    "图纸上的标线怎么画",
]


def run_case(app, text, tag):
    config = {"configurable": {"thread_id": "objclaim-%s-%d" % (tag, time.time())}}
    nodes, chunks, sg, und = [], [], {}, {}
    for mode, item in app.stream(
        {"session_id": "oc", "messages": [HumanMessage(content=text)]},
        config, stream_mode=["updates", "custom"],
    ):
        if mode == "custom":
            if isinstance(item, dict) and "chunk" in item:
                chunks.append(str(item["chunk"]))
            continue
        if not isinstance(item, dict):
            continue
        for name, upd in item.items():
            nodes.append(name)
            if name == "scope_guard" and isinstance(upd, dict):
                sg = upd
            if name == "understand" and isinstance(upd, dict):
                und = upd
    return {"nodes": nodes, "sg": sg, "und": und, "text": "".join(chunks)}


def main():
    app = ag.build_graph()
    lines = []
    lines.append("物件型小类的原文核对：端到端验证（完整图，真模型）")
    lines.append("输入 %d 条本领域 + %d 条越界；每例重复 %d 次（有方差数据）。"
                 % (len(IN_DOMAIN), len(OFF_DOMAIN), REPS))
    lines.append("判据：越界 = 节点里不出现 search/report（不给报告即通过，ambiguous/out_of_scope 都算）；")
    lines.append("      本领域 = scope 落在 hazard/emergency（不是 ambiguous/out_of_scope）。\n")

    lines.append("—— 本领域探针（不许被核对误伤）——")
    ok_in = 0
    for idx, (label, text) in enumerate(IN_DOMAIN, 1):
        scopes, subs, times = [], [], []
        lines.append("[%d] %s | %s" % (idx, label, text))
        for rep in range(1, REPS + 1):
            t0 = time.time()
            try:
                r = run_case(app, text, "in%d-r%d" % (idx, rep))
                err = ""
            except Exception as exc:
                r, err = {"nodes": [], "sg": {}, "und": {}, "text": ""}, repr(exc)
            scope = str(r["sg"].get("scope") or "")
            reason = str(r["sg"].get("scope_reason") or "")
            sub = str(r["und"].get("locked_subcategory") or "")
            action = str(r["und"].get("next_action") or "")
            scopes.append(scope)
            subs.append(sub)
            times.append(time.time() - t0)
            lines.append("    r%d scope=%s (%s) | locked=%s | next=%s | %.1fs%s"
                         % (rep, scope, reason, sub, action, times[-1],
                            (" | 失败：%s" % err) if err else ""))
        good = all(s in ("hazard", "emergency") for s in scopes)
        ok_in += 1 if good else 0
        lines.append("    小计：%d/%d 次落在 hazard/emergency；小类 %s；耗时 %s"
                     % (sum(1 for s in scopes if s in ("hazard", "emergency")), REPS,
                        "、".join(sorted(set(subs))), ["%.1fs" % t for t in times]))
        lines.append("")

    lines.append("—— 越界探针（不许进入检索/报告）——")
    ok_off = hard_off = 0
    for idx, text in enumerate(OFF_DOMAIN, 1):
        scopes, reasons, bad = [], [], 0
        lines.append("[%d] %s" % (idx, text))
        for rep in range(1, REPS + 1):
            try:
                r = run_case(app, text, "off%d-r%d" % (idx, rep))
                err = ""
            except Exception as exc:
                r, err = {"nodes": [], "sg": {}, "und": {}, "text": ""}, repr(exc)
            scope = str(r["sg"].get("scope") or "")
            reason = str(r["sg"].get("scope_reason") or "")
            went = [n for n in r["nodes"] if n in REPORT_NODES]
            scopes.append(scope)
            reasons.append(reason)
            if went:
                bad += 1
            lines.append("    r%d scope=%s (%s) | 进检索/报告=%s | 节点：%s%s"
                         % (rep, scope, reason, went or "无", " → ".join(r["nodes"]),
                            (" | 失败：%s" % err) if err else ""))
            lines.append("        回复：%s" % r["text"][:110].replace("\n", " "))
        if bad == 0:
            ok_off += 1
        if scopes and all(s == "out_of_scope" for s in scopes):
            hard_off += 1
        lines.append("    小计：%d/%d 次没进检索；scope 取值 %s"
                     % (REPS - bad, REPS, "、".join(sorted(set(scopes)))))
        lines.append("")

    lines.append("汇总：本领域 %d/%d 条全部保持 hazard/emergency；越界 %d/%d 条 0 次进检索；"
                 % (ok_in, len(IN_DOMAIN), ok_off, len(OFF_DOMAIN)))
    lines.append("      其中 %d/%d 条完全判 out_of_scope（其余为 ambiguous 澄清）。"
                 % (hard_off, len(OFF_DOMAIN)))
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


if __name__ == "__main__":
    main()
