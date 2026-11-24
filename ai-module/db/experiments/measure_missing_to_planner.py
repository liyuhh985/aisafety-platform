# -*- coding: utf-8 -*-
"""阶段 2 对照测量：把 missing 喂进规划器，问句命中率有没有变化。

设计（受控 A/B）：
  T1  用真实规划器跑一遍原始 query -> 得到小类 + 已抽到的槽（= 第 1 轮结束时的状态）
      A 类缺失为空 -> 该例"空洞"，没有可对比的追问目标，跳过
  T2  同一段 messages（用户原话 + 助手回执 + 用户跟进），跑两次：
        对照（before）：不带 missing 上下文  == 改动前的行为
        处理（after） ：带 missing/known_slots/subcategory_code
      两次只有"注入块"这一个差别。
  判定：问句归到哪个槽（复用 G1 的启发式 classify_question）；命中的槽在 A 类缺失里 = 命中。

每例只跑一次，无方差数据。逐条落盘，单条失败只记录。
"""
import io
import os
import sys
import time
import traceback

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "db"))

from langchain_core.messages import AIMessage, HumanMessage

import db.experiments.g1_question_target as g1
from core.dialogue_understanding import understand
from core.hazard_taxonomy import SUBCATEGORY_LABELS
from core.slot_schemas import missing_decision_slots
from eval.eval_queries import QUERY_SET

OUT = os.path.join(os.getcwd(), "db", "eval_missing_to_planner.txt")
FOLLOWUP = "就是这样，你还需要知道什么？"
PAIR_LIMIT = 12


def a_missing(sub, slots):
    return [s.key for s in missing_decision_slots(sub, slots or {})]


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    log = open(OUT, "w", encoding="utf-8")
    log.write("阶段 2 对照：missing 注入规划器前后，追问命中率（每例只跑 1 次，无方差数据）\n")
    log.write("口径：问句归类复用 db/experiments/g1_question_target.py 的启发式；命中 = 归到的槽在 A 类缺失里。\n")
    log.write("跟进语固定为：%s\n\n" % FOLLOWUP)
    log.flush()

    t0 = time.time()
    stage = {"ok": 0, "fail": 0, "vacuous": 0, "pairs": 0}
    rows = []
    for idx, item in enumerate(QUERY_SET, 1):
        query = item["query"]
        try:
            t1 = understand([HumanMessage(content=query)])
        except Exception as exc:
            stage["fail"] += 1
            log.write("[T1 %d] 失败 %s: %s\n" % (idx, item.get("subcategory"), exc))
            log.flush()
            continue
        stage["ok"] += 1
        issues = t1.get("issues") or []
        if not issues:
            stage["vacuous"] += 1
            continue
        sub = issues[0].get("subcategory_code") or ""
        slots = dict(issues[0].get("slots") or {})
        miss = a_missing(sub, slots)
        if not miss:
            stage["vacuous"] += 1
            log.write("[T1 %d] 空洞（A 类已齐） %s slots=%s\n" % (idx, sub, slots))
            log.flush()
            continue
        log.write("[T1 %d] 可对比 %s slots=%s A类缺失=%s\n" % (idx, sub, slots, miss))
        log.flush()
        if stage["pairs"] >= PAIR_LIMIT:
            continue

        ack = AIMessage(content=(t1.get("answer") or "").strip() or
                        "我先按「%s」来理解这个隐患。" % SUBCATEGORY_LABELS.get(sub, sub))
        msgs = [HumanMessage(content=query), ack, HumanMessage(content=FOLLOWUP)]
        try:
            before = understand(list(msgs))
            after = understand(list(msgs), missing=miss, known_slots=slots, subcategory_code=sub)
        except Exception:
            log.write("[T2 %d] 失败\n%s\n" % (idx, traceback.format_exc()))
            log.flush()
            continue
        qb = (before.get("question") or "").strip()
        qa = (after.get("question") or "").strip()
        kb, ka = g1.classify_question(qb), g1.classify_question(qa)
        hit_b, hit_a = bool(kb and kb in miss), bool(ka and ka in miss)
        stage["pairs"] += 1
        rows.append((item.get("subcategory"), item.get("style"), sub, miss, qb, kb, hit_b, qa, ka, hit_a))
        log.write(
            "[T2 %d] %s/%s [%s] A类缺失=%s\n"
            "    对照 before: 归到=%-14s 命中=%s  问句=%s\n"
            "    处理 after : 归到=%-14s 命中=%s  问句=%s\n" % (
                idx, item.get("subcategory"), item.get("style"), sub, miss,
                kb or "-", hit_b, qb or "(未问)", ka or "-", hit_a, qa or "(未问)"))
        log.flush()

    hb = sum(1 for r in rows if r[6])
    ha = sum(1 for r in rows if r[9])
    lines = ["", "===== 汇总（耗时 %.0f 秒）=====" % (time.time() - t0),
             "QUERY_SET 共 %d 条；T1 成功 %d，失败 %d" % (len(QUERY_SET), stage["ok"], stage["fail"]),
             "A 类缺失为空的「空洞」例 = %d（这些例没有可对比的追问目标）" % stage["vacuous"],
             "可对比成对样本 = %d（上限 %d）" % (stage["pairs"], PAIR_LIMIT),
             "",
             "对照 before 命中 = %d/%d = %.3f" % (hb, len(rows), hb / len(rows) if rows else 0.0),
             "处理 after  命中 = %d/%d = %.3f" % (ha, len(rows), ha / len(rows) if rows else 0.0),
             "其中 before 未问（黑洞）=%d，after 未问 = %d" % (
                 sum(1 for r in rows if not r[4]), sum(1 for r in rows if not r[7])),
             "",
             "===== 逐条 ====="]
    for r in rows:
        lines.append("- %s/%s A类缺失=%s\n    before 归到=%s 命中=%s | %s\n    after  归到=%s 命中=%s | %s" % (
            r[0], r[1], r[3], r[5] or "-", r[6], r[4] or "(未问)", r[8] or "-", r[9], r[7] or "(未问)"))
    log.write("\n".join(lines) + "\n")
    log.close()
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
