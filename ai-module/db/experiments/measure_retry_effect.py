# -*- coding: utf-8 -*-
"""对照测量：8 个触发点的「触发前 top1 → 重试后 top1」。

全过程走生产函数，不改任何生产文件：
    _pick_keyword → hybrid_search（拿文本）→ evaluate_retrieval（判定 + 探针）
    → rewrite_query（**真实模型**改写检索串）→ 用新检索串重查 → 对比 top1

触发点来自 db/eval_retry_trigger.txt（阶段 1 的测量）。
用法：cd ai-module; python db/experiments/measure_retry_effect.py
"""
import io
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from langchain_core.messages import HumanMessage

from core.assistant_graph import (
    WEAK_SCORE,
    evaluate_retrieval,
    rewrite_query,
    retrieval_quality,
)
from core.hazard_taxonomy import normalize_taxonomy
from core.case_relevance import filter_by_major
from eval.eval_queries import QUERY_SET
from eval.eval_retrieval import SCENARIO_EMPTY, SCENARIO_SCHEMA, production_keyword, slots_for
from tools.hybrid_search import searcher

FIELD_TABLE = {"case": "tb_hazard_case", "regulation": "tb_regulation"}
TRIGGERS = [
    ("槽位空", "illegal_structure", "case"),
    ("槽位空", "scaffold_guard", "case"),
    ("槽位空", "other", "case"),
    ("槽位空", "other", "regulation"),
    ("槽位空", "illegal_wiring", "regulation"),
    (SCENARIO_SCHEMA, "scaffold_guard", "case"),
    (SCENARIO_SCHEMA, "other", "case"),
    (SCENARIO_SCHEMA, "other", "regulation"),
]
SCENARIO_CODE = {"槽位空": SCENARIO_EMPTY, SCENARIO_SCHEMA: SCENARIO_SCHEMA}

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "eval_retry_effect.txt")
_LINES = []


def emit(text=""):
    print(text)
    _LINES.append(str(text))


def user_text_for(subcategory: str) -> str:
    for item in QUERY_SET:
        if item.get("subcategory") == subcategory:
            return item.get("query") or ""
    return subcategory


def top1(keyword: str, table: str):
    rows = searcher.vector_search(keyword, table, top_k=1)
    if not rows:
        return None, 0
    return rows[0].get("match_score"), len(rows)


def count_blocks(text: str) -> int:
    return len(re.findall(r"【(?:结果|法规)\d+】", text or ""))


def run_case(scenario_label, subcategory, field):
    table = FIELD_TABLE[field]
    scenario = SCENARIO_CODE[scenario_label]
    keyword = production_keyword(subcategory, scenario)
    slots = slots_for(subcategory, scenario)
    before_text = searcher.hybrid_search(keyword, table)
    before_score, _ = top1(keyword, table)
    before_blocks = count_blocks(before_text)
    pair = normalize_taxonomy(subcategory)
    major = pair[0] if pair else ""
    state = {
        "categories": [subcategory],
        "category_slots": {subcategory: slots},
        "issues": [{"major_code": major, "subcategory_code": subcategory}],
        "locked_major": major,
        "premises_scope": "public",
        "messages": [HumanMessage(content=user_text_for(subcategory))],
        "category_results": {subcategory: {field: before_text}},
    }
    started = time.monotonic()
    command = evaluate_retrieval(state)
    verdict = getattr(command, "goto", None)
    reason = (getattr(command, "update", {}) or {}).get("retrieval_retry_reason", "")
    row = {
        "case": "%s | %s | %s" % (scenario_label, subcategory, table),
        "reason": reason,
        "goto": verdict,
        "before_keyword": keyword,
        "before_score": before_score,
        "before_blocks": before_blocks,
        "before_quality": retrieval_quality(before_text),
        "after_keyword": "",
        "after_score": None,
        "after_blocks": 0,
        "after_quality": "",
        "seconds": 0.0,
    }
    if verdict == "rewrite_query":
        state_after = dict(state)
        for key, value in (getattr(command, "update", {}) or {}).items():
            state_after[key] = value
        rewritten = rewrite_query(state_after)
        new_keyword = (getattr(rewritten, "update", {}) or {}).get(
            "retrieval_keyword_override", {}).get(subcategory, "")
        if new_keyword:
            after_text = searcher.hybrid_search(new_keyword, table)
            after_score, _ = top1(new_keyword, table)
            row.update({
                "after_keyword": new_keyword,
                "after_score": after_score,
                "after_blocks": count_blocks(after_text),
                "after_quality": retrieval_quality(after_text),
            })
    row["seconds"] = time.monotonic() - started
    return row


def main():
    emit("=== 检索重试环对照测量（WEAK=%.2f）===" % WEAK_SCORE)
    emit("触发点来自 db/eval_retry_trigger.txt；重试用真实模型改写检索串")
    emit()
    rows = []
    for scenario_label, subcategory, field in TRIGGERS:
        try:
            row = run_case(scenario_label, subcategory, field)
        except Exception as exc:
            emit("  [ERR] %s | %s | %s -> %s: %s" % (
                scenario_label, subcategory, field, type(exc).__name__, exc))
            continue
        rows.append(row)
        emit("[%s] %s" % (row["goto"], row["case"]))
        emit("    原因     : %s" % row["reason"])
        emit("    触发前   : 检索串=%r top1=%s 结果块=%d 质量=%s" % (
            row["before_keyword"], _fmt(row["before_score"]), row["before_blocks"],
            row["before_quality"]))
        if row["goto"] == "rewrite_query":
            emit("    改写后   : 检索串=%r top1=%s 结果块=%d 质量=%s" % (
                row["after_keyword"], _fmt(row["after_score"]), row["after_blocks"],
                row["after_quality"]))
            emit("    变化     : top1 %s → %s | 结果块 %d → %d" % (
                _fmt(row["before_score"]), _fmt(row["after_score"]),
                row["before_blocks"], row["after_blocks"]))
        emit("    耗时     : %.1fs" % row["seconds"])
        emit()
    emit_summary(rows)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(_LINES) + "\n")
    emit("原始输出已写入 db/eval_retry_effect.txt")


def _fmt(value):
    return "无" if value is None else "%.4f" % float(value)


def emit_summary(rows):
    triggered = [r for r in rows if r["goto"] == "rewrite_query"]
    emit("=== 汇总 ===")
    emit("触发点 %d 个，其中在代码路径里重新触发 %d 个" % (len(rows), len(triggered)))
    improved = [r for r in triggered if (
        r["after_blocks"] > r["before_blocks"]
        or (r["after_score"] or 0.0) > (r["before_score"] or 0.0))]
    emit("重试后有改善 %d 个 / %d" % (len(improved), len(triggered)))
    mean_before = sum(r["before_score"] or 0.0 for r in triggered) / len(triggered) if triggered else 0.0
    mean_after = sum(r["after_score"] or 0.0 for r in triggered) / len(triggered) if triggered else 0.0
    emit("top1 均值（无命中记 0）：%.4f → %.4f" % (mean_before, mean_after))
    # “完全没结果”的口径是**向量分支 0 命中**（top1 为无），
    # 不是“文本里一个块也没有”——关键词分支可能仍然拿回几条
    empty_before = [r for r in triggered if r["before_score"] is None]
    rescued = [r for r in empty_before if r["after_score"] is not None]
    emit("触发前向量分支 0 命中（top1 为无）：%d 个，重试后拿到向量命中：%d 个"
         % (len(empty_before), len(rescued)))
    for row in empty_before:
        emit("    %s : 结果块 %d → %d | top1 无 → %s | 新检索串=%r" % (
            row["case"], row["before_blocks"], row["after_blocks"],
            _fmt(row["after_score"]), row["after_keyword"]))


if __name__ == "__main__":
    main()
