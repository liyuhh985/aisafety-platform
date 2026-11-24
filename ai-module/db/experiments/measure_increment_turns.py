# -*- coding: utf-8 -*-
"""阶段 3b 实测：两轮真实对话里，第 2 轮是否还在重讲第 1 轮的分析、法规是否一致。

为什么这样构造：
  断链是「上一轮的报告没进 messages」。所以要证明修好了，必须做**受控对照**：
    甲（反事实 = 修复前）：第 2 轮的上下文只有用户说过的两句话（没有报告正文）；
    乙（修复后）：第 2 轮的上下文 = 用户两句话 + 第 1 轮的报告正文。
  两个 arm 只差"报告在不在历史里"这一个变量，其他全一样（同一段 u1、同一段 u2、
  同一个模型、同一份检索）。

诚实说明（别当硬指标读）：
  - 每格只跑 1 次，**没有方差数据**；
  - 重合度是字符 bigram 的 Jaccard，它把"用词相似"当"内容重复"，
    反过来"换个说法重讲同一份分析"它抓不到 —— 所以原文一并落盘，人工复核必须做；
  - 甲是**构造出来的反事实**，不是线上跑过的历史（线上旧版本无法回放）。

输出：db/eval_increment_turns.txt
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.getcwd())

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

import core.assistant_graph as ag  # noqa: E402
from eval.eval_increment import (citation_report, duplicated_sentence_ratio,  # noqa: E402
                            overlap_ratio, regulation_citations)

U1 = "楼下消防通道被杂物占了，帮我查一下法规和案例"
U2 = "堆了半年多了，物业一直没清理，我上周也打过电话"

OUT = os.path.join("db", "eval_increment_turns.txt")
lines = []


def log(text=""):
    print(text)
    lines.append(str(text))


def run_turn(thread, messages):
    app = ag.build_graph()
    config = {"configurable": {"thread_id": thread}}
    nodes, chunks = [], []
    for mode, item in app.stream({"session_id": thread, "messages": list(messages)},
                                config, stream_mode=["updates", "custom"]):
        if mode == "updates":
            nodes.extend(item.keys())
        elif isinstance(item, dict) and "chunk" in item:
            chunks.append(item["chunk"])
    return nodes, "".join(chunks), app.get_state(config).values


def main():
    log("=" * 78)
    log("阶段 3b 实测：第 2 轮是否还在重讲第 1 轮 / 法规是否一致（每格 1 次，无方差）")
    log("=" * 78)
    log("u1 = %s" % U1)
    log("u2 = %s" % U2)

    # ---------- 第 1 轮（真实规划器 + 真实检索 + 真实模型） ----------
    log("\n### 第 1 轮 ###")
    nodes1, _chunks1, v1 = run_turn("increment-real-1", [HumanMessage(content=U1)])
    r1 = v1.get("draft_report") or ""
    log("nodes       : %s" % sorted(set(nodes1)))
    log("locked      : %s / %s" % (v1.get("locked_major"), v1.get("locked_subcategory")))
    log("report_mode : %s" % v1.get("report_mode"))
    log("missing(A)  : %s" % (v1.get("missing") or []))
    log("messages 末条是 AIMessage: %s" % (type(v1["messages"][-1]).__name__))
    log("报告进了 messages      : %s" % (v1["messages"][-1].content == r1))
    log("--- 第 1 轮报告原文 ---")
    log(r1 or "（第 1 轮没有产出报告）")

    _results = (v1.get("category_results") or {}).get(v1.get("locked_subcategory")) or {}
    # 上下文 = 法规块 + 案例块：案例标题里也会出现书名号（实测《责令限期整改通知书》就出自案例块）
    regulation = (_results.get("regulation") or "") + "\n" + (_results.get("case") or "")

    # ---------- 第 2 轮：两个 arm 只差"报告在不在历史里" ----------
    log("\n### 第 2 轮 · 甲（反事实：报告不在历史里，= 修复前）###")
    nodes_a, text_a, va = run_turn("increment-real-armA", [
        HumanMessage(content=U1), HumanMessage(content=U2)])
    r2a = va.get("draft_report") or text_a
    log("nodes       : %s" % sorted(set(nodes_a)))
    log("report_mode : %s" % va.get("report_mode"))
    log("--- 第 2 轮回复原文（甲）---")
    log(r2a or "（没有回复）")

    log("\n### 第 2 轮 · 乙（修复后：报告在历史里）###")
    nodes_b, text_b, vb = run_turn("increment-real-armB", [
        HumanMessage(content=U1), AIMessage(content=r1), HumanMessage(content=U2)])
    r2b = vb.get("draft_report") or text_b
    log("nodes       : %s" % sorted(set(nodes_b)))
    log("report_mode : %s" % vb.get("report_mode"))
    log("--- 第 2 轮回复原文（乙）---")
    log(r2b or "（没有回复）")

    # ---------- 对照 ----------
    log("\n" + "=" * 78)
    log("对照结果")
    log("=" * 78)
    log("重合度 overlap(第1轮, 第2轮)：甲 = %.3f   乙 = %.3f" % (
        overlap_ratio(r1, r2a), overlap_ratio(r1, r2b)))
    log("（越低越像增量。这是字符 bigram Jaccard，脆指标，必须配原文人工复核）")
    log("")
    log("逐句重复率（第 2 轮有几句话在重讲第 1 轮，阈值 0.5，越高越像重复）：")
    for name, text in (("甲", r2a), ("乙", r2b)):
        stat = duplicated_sentence_ratio(r1, text)
        log("  %s：%d/%d 句 = %.2f" % (name, stat["duplicated"], stat["total"], stat["ratio"]))
        for hit in stat["hits"]:
            log("      [%.2f] %s" % (hit["best"], hit["sentence"][:60]))

    for name, text in (("甲", r2a), ("乙", r2b)):
        report = citation_report(r1, text)
        log("\n法规引用对照（%s）：" % name)
        log("  第1轮引用 : %s" % (report["first"] or "（无）"))
        log("  第2轮引用 : %s" % (report["second"] or "（无）"))
        log("  两轮共同  : %s" % (report["shared"] or "（无）"))
        log("  只在第1轮: %s" % (report["only_first"] or "（无）"))
        log("  只在第2轮: %s" % (report["only_second"] or "（无）"))
        missing_from_context = [
            c for c in regulation_citations(text)
            if c.split("》")[0].lstrip("《") not in str(regulation)
        ]
        log("  第2轮引了但检索结果里没有的：%s" % (missing_from_context or "（无）"))

    log("\n【人工复核提示】第二半（法条不矛盾）比第一半（不重复）重要：")
    log("  看乙的第 2 轮有没有出现与第 1 轮不同的法条/不一致结论，以及是否还在整段重讲。")

    os.makedirs("db", exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    log("\n已写入 %s" % OUT)


if __name__ == "__main__":
    main()