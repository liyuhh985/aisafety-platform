# -*- coding: utf-8 -*-
"""阶段 5a 双向验收：从两次测量产物重算指标（不调模型，纯读文件）。

输入：db/eval_stage5a_baseline.txt、db/eval_stage5a_after.txt
输出：对比表（stdout）+ db/eval_stage5a_compare.txt

为什么另写一个：产物里已经存了正文，重算不值当再花 4 分钟调一次模型；
而且「B 类那一项有没有被写进正文」这个**内容级**指标要用 2-gram（3-gram 会漏，
实测「妨碍消防车通行」与「是否影响消防车或人员通行？」只共享 1 个 3-gram）。
"""
import io
import os
import re
import sys

sys.path.insert(0, os.getcwd())
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import core.assistant_graph as ag

CASES = {
    "A": ("完整", "fire_lane_blocked", "impact"),
    "B": ("完整", "manhole_damage", "traffic"),
    "C": ("初步", "fire_lane_blocked", "impact"),
    "D": ("初步", "fire_lane_blocked", "impact"),
}


def _ngrams(text, n):
    grams = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", str(text or "")):
        for i in range(len(run) - n + 1):
            grams.add(run[i:i + n])
    return grams


def b_mentioned(body, code, key):
    """B 类那一项有没有真的写进正文（2-gram 共享 ≥3，内容级检查）。"""
    hint = next((s.question for s in ag.get_slot_schema(code) if s.key == key), "")
    return len(_ngrams(hint, 2) & _ngrams(body, 2)) >= 3


def parse(path):
    rows = []
    lines = open(path, encoding="utf-8-sig").read().splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("用例 "):
            continue
        body = []
        if i + 1 < len(lines) and lines[i + 1].strip() == "---- 正文 ----":
            j = i + 2
            while j < len(lines) and not lines[j].startswith("用例 "):
                body.append(lines[j])
                j += 1
        rows.append({"row": line, "body": "\n".join(body).strip()})
    return rows


def summarize(path):
    out = []
    for item in parse(path):
        name = item["row"].split(" ")[1]
        tag, code, key = CASES[name]
        body = item["body"]
        blocks = ag.preliminary_coverage(body)
        out.append({
            "case": name, "tag": tag, "sample": item["row"].split("sample=")[1][0],
            "branches": body.count("若"),
            "chars": len(body),
            "sections": all(m in body for m in ("一、", "二、", "三、")),
            "blocks": blocks,
            "qsent": len(ag.question_sentences(body)),
            "redundancy": re.search(r"冗余=(\[[^\]]*\])", item["row"]).group(1),
            "b_mentioned": b_mentioned(body, code, key),
            "empty_talk": ag.empty_talk_hits(body),
        })
    return out


def line(label, rows, field):
    return "%-22s %s" % (label, [r[field] for r in rows])


report = []
for path, title in (("db/eval_stage5a_baseline.txt", "基线（改动前）"),
                    ("db/eval_stage5a_after.txt", "改动后")):
    rows = summarize(path)
    report.append("==== %s" % title)
    for r in rows:
        report.append(
            "  %s s%s | %s档 | 分支=%d | 字数=%d | 三段式=%s | 三块=%s/%s/%s | 问句=%d | "
            "冗余=%s | B类写进正文=%s | 空话=%s"
            % (r["case"], r["sample"], r["tag"], r["branches"], r["chars"], r["sections"],
               r["blocks"]["judgment"], r["blocks"]["missing"], r["blocks"]["question"],
               r["qsent"], r["redundancy"], r["b_mentioned"], r["empty_talk"]))
    full = [r for r in rows if r["tag"] == "完整"]
    prelim = [r for r in rows if r["tag"] == "初步"]
    report.append("  -- 汇总：样本 %d" % len(rows))
    report.append("     条件分支总数=%d（完整档 %d / 初步档 %d）"
                  % (sum(r["branches"] for r in rows),
                     sum(r["branches"] for r in full), sum(r["branches"] for r in prelim)))
    report.append("     总字数=%d" % sum(r["chars"] for r in rows))
    report.append("     冗余命中的采样数=%d/%d"
                  % (len([r for r in rows if r["redundancy"] != "[]"]), len(rows)))
    report.append("     完整档三段式齐全=%d/%d；初步档三块齐全=%d/%d"
                  % (len([r for r in full if r["sections"]]), len(full),
                     len([r for r in prelim if all(r["blocks"].values())]), len(prelim)))
    report.append("     B 类写进正文=%d/%d；问句总数=%d；空话=%d"
                  % (len([r for r in rows if r["b_mentioned"]]), len(rows),
                     sum(r["qsent"] for r in rows),
                     sum(len(r["empty_talk"]) for r in rows)))
    report.append("")

text = "\n".join(report)
print(text)
with open("db/eval_stage5a_compare.txt", "w", encoding="utf-8") as fh:
    fh.write(text + "\n")
print("summary -> db/eval_stage5a_compare.txt")
