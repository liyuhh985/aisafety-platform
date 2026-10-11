# -*- coding: utf-8 -*-
"""追问命中率的方差测量：每例重复 3 次，报区间。

口径与 db/experiments/measure_missing_to_planner.py 的 after 臂一致：
  T1  真实规划器跑一遍原始 query → 小类 + 已抽到的槽（= 第 1 轮结束时的状态）
      该小类的 A 类缺失为空 → 没有可对比的追问目标，跳过（"空洞"）
  T2  同一段 messages + 同一段跟进语，带 missing/known_slots/subcategory_code 跑 REPS 次
  命中 = 问句归到的槽（复用 G1 的启发式）落在 A 类缺失里

为什么单独写一个：原脚本每例只跑一次，不能报区间（面试会被追问"这个数稳不稳"）。
落盘 db/eval_followup_hit_variance.txt；同时把每句问句打出来，供人工复核（启发式是弱判据）。
"""
import io
import os
import sys
import time

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "db"))

from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402

import db.experiments.g1_question_target as g1  # noqa: E402
from core.dialogue_understanding import understand  # noqa: E402
from core.hazard_taxonomy import SUBCATEGORY_LABELS  # noqa: E402
from core.slot_schemas import missing_decision_slots  # noqa: E402
from eval.eval_queries import QUERY_SET  # noqa: E402

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUT = os.path.join(os.getcwd(), "db", "eval_followup_hit_variance.txt")
FOLLOWUP = "就是这样，你还需要知道什么？"
PAIR_LIMIT = 12


def a_missing(sub, slots):
    return [s.key for s in missing_decision_slots(sub, slots or {})]


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    log = open(OUT, "w", encoding="utf-8", newline="\n")
    log.write("追问命中率：每例重复 %d 次的方差测量\n" % REPS)
    log.write("口径：after 臂（带 missing/known_slots/subcategory_code）；"
              "命中 = 问句归到的槽在 A 类缺失里（复用 db/experiments/g1_question_target.py 的启发式）。\n")
    log.write("跟进语固定为：%s\n\n" % FOLLOWUP)
    log.flush()

    t0 = time.time()
    rows = []
    fail = 0
    vacuous = 0
    for idx, item in enumerate(QUERY_SET, 1):
        query = item["query"]
        try:
            t1 = understand([HumanMessage(content=query)])
        except Exception as exc:
            fail += 1
            log.write("[T1 %d] 失败 %s: %s\n" % (idx, item.get("subcategory"), exc))
            log.flush()
            continue
        issues = t1.get("issues") or []
        if not issues:
            vacuous += 1
            continue
        sub = issues[0].get("subcategory_code") or ""
        slots = dict(issues[0].get("slots") or {})
        miss = a_missing(sub, slots)
        if not miss:
            vacuous += 1
            continue
        if len(rows) >= PAIR_LIMIT:
            continue
        ack = AIMessage(content=(t1.get("answer") or "").strip() or
                        "我先按「%s」来理解这个隐患。" % SUBCATEGORY_LABELS.get(sub, sub))
        msgs = [HumanMessage(content=query), ack, HumanMessage(content=FOLLOWUP)]
        samples = []
        for rep in range(1, REPS + 1):
            try:
                after = understand(list(msgs), missing=miss, known_slots=slots,
                                   subcategory_code=sub)
            except Exception as exc:
                samples.append((rep, "", "", False, "失败:%s" % exc))
                continue
            q = (after.get("question") or "").strip()
            key = g1.classify_question(q)
            samples.append((rep, q, key or "-", bool(key and key in miss), ""))
        rows.append((item.get("subcategory"), item.get("style"), sub, miss, samples))
        log.write("[T2 %d] %s/%s [%s] A类缺失=%s\n"
                  % (idx, item.get("subcategory"), item.get("style"), sub, miss))
        for rep, q, key, hit, err in samples:
            log.write("    r%d 归到=%-14s 命中=%-5s %s%s\n"
                      % (rep, key, hit, q or "(未问)", ("  " + err) if err else ""))
        log.flush()

    lines = []
    rounds = [[] for _ in range(REPS)]
    for _a, _b, _sub, _miss, samples in rows:
        for rep, _q, _k, hit, _err in samples:
            if 1 <= rep <= REPS:
                rounds[rep - 1].append(1 if hit else 0)
    lines.append("")
    lines.append("===== 汇总（耗时 %.0f 秒）=====" % (time.time() - t0))
    lines.append("QUERY_SET %d 条；T1 失败 %d；A 类缺失为空的「空洞」例 %d"
                 % (len(QUERY_SET), fail, vacuous))
    lines.append("可对比例 = %d（上限 %d），每例 %d 次采样" % (len(rows), PAIR_LIMIT, REPS))
    rates = []
    for i, vals in enumerate(rounds, 1):
        if not vals:
            continue
        rates.append(sum(vals) / len(vals))
        lines.append("  第 %d 轮：命中 %d/%d = %.3f" % (i, sum(vals), len(vals), rates[-1]))
    if rates:
        lines.append("区间：min=%.3f max=%.3f 极差=%.3f（总体 %.3f）"
                     % (min(rates), max(rates), max(rates) - min(rates),
                        sum(rates) / len(rates)))
    per_case = []
    for label, style, sub, miss, samples in rows:
        hits = sum(1 for _r, _q, _k, hit, _e in samples if hit)
        per_case.append((sub, style, hits, REPS))
    unstable = [c for c in per_case if 0 < c[2] < c[3]]
    lines.append("逐例稳定度：%d/%d 例在 %d 次采样里结果不一致%s"
                 % (len(unstable), len(per_case), REPS,
                    ("：" + "、".join("%s/%s %d/%d" % (c[0], c[1], c[2], c[3]) for c in unstable))
                    if unstable else ""))
    lines.append("")
    lines.append("===== 逐条 =====")
    for label, style, sub, miss, samples in rows:
        lines.append("- %s/%s A类缺失=%s" % (label, style, miss))
        for rep, q, key, hit, err in samples:
            lines.append("    r%d 归到=%s 命中=%s | %s%s"
                         % (rep, key, hit, q or "(未问)", ("  " + err) if err else ""))
    log.write("\n".join(lines) + "\n")
    sys.stdout.write("\n".join(lines) + "\n")
    log.close()


if __name__ == "__main__":
    main()
