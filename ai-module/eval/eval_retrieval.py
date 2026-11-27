"""检索评测（生产路径口径）：金标准 = 库内真实 case id。

这一版把"喂给检索的东西"改成与生产一致：

    查询 → core.assistant_graph._pick_keyword(小类, 槽位) → 同一个串
          既当向量查询、又当关键词输入（生产 hybrid_search 就是这么传的）

排名重建直接调 `HybridSearcher._merge_results`（生产用的同一段代码），
不再在评测里复写一份，避免两边漂移。

三种情形：

    槽位空              —— 首轮还没有槽位值，串里只有小类标签
    槽位有值            —— 键用与 db/eval_retrieval_baseline.txt 对齐的老 9-slug 键（可比）
    槽位有值(schema键)  —— 键改用 core.slot_schemas 里该小类的第一个槽位键（现实情形）

后两种用的是**同一组取值**，只有键不同。老实现只读 9 个硬编码 slug，所以
`槽位有值` 那份能和基线文件逐条对上；`槽位有值(schema键)` 没有对应的老基线
（老实现读不到那些键），只报绝对值、并和同一次运行里的 `槽位空` 对比。

用法：
    python eval/eval_retrieval.py
输出同时打印到 stdout 与 db/eval_retrieval_output.txt

注意：SLOT_VALUES 是**合成 fixture**，不是规划器真实输出。真实槽位分布未知，
所以"槽位有值"两组只能说明关键词分支"给定可用槽位时能做到什么"，不代表线上均值。
"""
import io
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _AI_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pymysql

from db_config import DB_CONFIG
from eval.eval_metrics import (
    hit_at_k,
    first_relevant_rank,
    major_hit_at_k,
    mean,
    mrr,
    precision_at_k,
    recall_at_k,
)
from eval.eval_queries import (
    NEGATIVE_SET,
    QUERY_SET,
    all_subcategories,
    category_label,
    covered_subcategories,
)
from core.assistant_graph import _pick_keyword
from core.hazard_taxonomy import MAJOR_LABEL_TO_CODE
from core.slot_schemas import get_slot_schema
from tools.hybrid_search import (
    RETRIEVAL_MIN_SCORE as MIN_SCORE,
    _tokenize_keyword,
    searcher,
)

TABLE = "tb_hazard_case"
VECTOR_K = 3
KEYWORD_K = 3
WINDOW = max(VECTOR_K, KEYWORD_K) + 2

SCENARIO_EMPTY = "槽位空"
SCENARIO_LEGACY = "槽位有值"
SCENARIO_SCHEMA = "槽位有值(schema键)"
SCENARIOS = (SCENARIO_EMPTY, SCENARIO_LEGACY, SCENARIO_SCHEMA)

# 29 个小类的代表性槽位值（v2a 合并后独立基线）。
SLOT_VALUES = {
    "road_occupancy": "货架",
    "vehicle_occupancy": "违停",
    "blind_path_occupied": "电动车",
    "traffic_facility_damage": "信号灯",
    "manhole_damage": "移位",
    "road_surface_collapse": "塌陷",
    "drainage_flood": "积水",
    "street_light_pole": "不亮",
    "fire_lane_blocked": "私家车",
    "fire_equipment_fault": "消火栓无水",
    "dangerous_building": "裂缝倾斜",
    "falling_object": "外墙脱落",
    "illegal_structure": "搭建",
    "exposed_wire": "裸露",
    "distribution_box_fault": "配电箱",
    "illegal_wiring": "接线",
    "gas_leak": "漏气",
    "gas_pipe_aging": "老化",
    "no_barrier": "围挡",
    "no_warning": "警示牌",
    "scaffold_guard": "临边防护",
    "deep_pit": "基坑",
    "temporary_power": "临时用电",
    "elevator_trapped": "困人",
    "elevator_stopped": "异响",
    "elevator_inspection": "检验过期",
    "garbage_pile": "长期堆积",
    "sewage_odor": "异味",
    "other": "来源不明",
}

# 基线那次用的键（来自 _pick_keyword 老实现硬编码的 9 个 slug）。
SLOT_FIXTURE_KEYS = {
    "road_occupancy": "behavior",
    "vehicle_occupancy": "behavior",
    "blind_path_occupied": "behavior",
    "traffic_facility_damage": "defect",
    "manhole_damage": "defect",
    "road_surface_collapse": "defect",
    "drainage_flood": "defect",
    "street_light_pole": "defect",
    "fire_lane_blocked": "blocker",
    "fire_equipment_fault": "facility_type",
    "dangerous_building": "structure",
    "falling_object": "source",
    "illegal_structure": "defect",
    "exposed_wire": "source",
    "distribution_box_fault": "source",
    "illegal_wiring": "defect",
    "gas_leak": "source",
    "gas_pipe_aging": "source",
    "no_barrier": "defect",
    "no_warning": "defect",
    "scaffold_guard": "defect",
    "deep_pit": "defect",
    "temporary_power": "source",
    "elevator_trapped": "condition",
    "elevator_stopped": "condition",
    "elevator_inspection": "condition",
    "garbage_pile": "condition",
    "sewage_odor": "defect",
    "other": "defect",
}

OUTPUT_FILE = os.path.join(_AI_ROOT, "db",
                           "eval_retrieval_output.txt")

_lines = []


def emit(text=""):
    print(text)
    _lines.append(text)


def load_gold_ids() -> dict:
    """小类标签 -> 该小类全部 case id 集合。"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT category, id FROM " + TABLE)
            gold = {}
            for category, case_id in cur.fetchall():
                gold.setdefault(category.strip(), set()).add(int(case_id))
            return gold
    finally:
        conn.close()


def slots_for(subcategory: str, scenario: str) -> dict:
    """情形 → 槽位 dict（两种"有值"情形共用同一个取值，只有键不同）。"""
    if scenario == SCENARIO_EMPTY:
        return {}
    value = SLOT_VALUES[subcategory]
    if scenario == SCENARIO_LEGACY:
        return {SLOT_FIXTURE_KEYS[subcategory]: value}
    return {get_slot_schema(subcategory)[0].key: value}


def production_keyword(subcategory: str, scenario: str) -> str:
    """复现生产：小类 + 槽位 → 一个既喂向量又喂关键词的串。"""
    return _pick_keyword(subcategory, slots_for(subcategory, scenario))


def ranked_items(keyword: str, attempts: int = 2) -> dict:
    """走生产路径取回排名窗口。

    `keyword` 同时作为向量查询与关键词输入 —— 与 hybrid_search 的传参方式一致；
    合并去重直接用 HybridSearcher._merge_results。
    超时/网络错误不计为判错，单独计数（retries 记重试次数）。
    """
    last_error = None
    for attempt in range(attempts):
        try:
            keyword_results = searcher.keyword_search(keyword, TABLE, limit=KEYWORD_K)
            vector_results = searcher.vector_search(keyword, TABLE, top_k=VECTOR_K)
            merged = searcher._merge_results(keyword_results, vector_results,
                                             VECTOR_K, KEYWORD_K)
            return {"items": merged, "error": None, "retries": attempt,
                    "keyword_hits": len(keyword_results)}
        except Exception as exc:
            last_error = type(exc).__name__
            time.sleep(0.5)
    return {"items": [], "error": last_error or "UnknownError", "retries": attempts,
            "keyword_hits": 0}


def major_of(category: str) -> str:
    label = (category or "").split("/")[0].strip()
    return MAJOR_LABEL_TO_CODE.get(label, "")


def run_group(title: str, queries, scenario: str) -> dict:
    emit("\n" + "-" * 78)
    emit(title + "  共 " + str(len(queries)) + " 条")
    emit("-" * 78)

    records = []
    for item in queries:
        keyword = production_keyword(item["subcategory"], scenario)
        label = category_label(item["major"], item["subcategory"])
        gold = GOLD.get(label, set())
        outcome = ranked_items(keyword)
        items = outcome["items"]
        error = outcome["error"]
        ranked_ids = [int(x["id"]) for x in items if x.get("id") is not None]
        ranked_majors = [major_of(x.get("category", "")) for x in items]
        scores = [x["match_score"] for x in items if x.get("match_score") is not None]
        top_score = max(scores) if scores else None

        record = {
            "query": item["query"],
            "keyword": keyword,
            "keyword_hits": outcome["keyword_hits"],
            "retries": outcome["retries"],
            "label": label,
            "gold": gold,
            "major": item["major"],
            "style": item["style"],
            "subcategory": item["subcategory"],
            "ranked_ids": ranked_ids,
            "returned": len(ranked_ids),
            "error": error,
            "top_score": top_score,
        }
        if error is None:
            record["first_rank"] = first_relevant_rank(ranked_ids, gold)
            record["hit"] = hit_at_k(ranked_ids, gold, WINDOW)
            record["mrr"] = mrr(ranked_ids, gold)
            record["p5"] = precision_at_k(ranked_ids, gold, WINDOW)
            record["recall"], record["ceiling"] = recall_at_k(ranked_ids, gold, WINDOW)
            record["major_hit"] = major_hit_at_k(ranked_majors, item["major"], WINDOW)
        records.append(record)

        if error is not None:
            emit("[ERR ] " + label + " | 检索失败 " + error + " | " + keyword[:30])
            continue
        rank_text = str(record["first_rank"]) if record["first_rank"] else "-"
        flag = "OK  " if record["hit"] else ("大类 " if record["major_hit"] else "MISS")
        emit(
            "[" + flag + "] " + label.ljust(22)
            + " 排名=" + rank_text.ljust(2)
            + " P@5=" + ("%.2f" % record["p5"])
            + " R@5=" + ("%.2f" % record["recall"]) + "/" + ("%.2f" % record["ceiling"])
            + " 返回=" + str(record["returned"])
            + " 关键词命中=" + str(record["keyword_hits"])
            + " 检索串=" + keyword[:26]
        )

    ok = [r for r in records if r["error"] is None]
    summary = {
        "title": title,
        "scenario": scenario,
        "count": len(records),
        "returned": mean([r["returned"] for r in ok]),
        "p_ret": mean([
            (sum(1 for x in r["ranked_ids"] if x in r["gold"]) / r["returned"])
            for r in ok if r["returned"]
        ]),
        "errors": len(records) - len(ok),
        "retries": sum(r["retries"] for r in records),
        "keyword_used": sum(1 for r in ok if r["keyword_hits"] > 0),
        "hit": mean([1.0 if r["hit"] else 0.0 for r in ok]),
        "mrr": mean([r["mrr"] for r in ok]),
        "p5": mean([r["p5"] for r in ok]),
        "recall": mean([r["recall"] for r in ok]),
        "ceiling": mean([r["ceiling"] for r in ok]),
        "major_hit": mean([1.0 if r["major_hit"] else 0.0 for r in ok]),
    }
    emit(
        "小计: n=" + str(len(ok))
        + " Hit@5=" + ("%.3f" % summary["hit"])
        + " MRR=" + ("%.3f" % summary["mrr"])
        + " P@5=" + ("%.3f" % summary["p5"])
        + " R@5=" + ("%.3f" % summary["recall"]) + "(上限 " + ("%.3f" % summary["ceiling"]) + ")"
        + " 大类Hit@5=" + ("%.3f" % summary["major_hit"])
        + " | 平均返回=" + ("%.1f" % summary["returned"])
        + " 纯度P@ret=" + ("%.3f" % summary["p_ret"])
        + " 关键词分支有命中=" + str(summary["keyword_used"]) + "/" + str(len(ok))
        + (" | 检索异常 " + str(summary["errors"]) if summary["errors"] else "")
        + (" | 重试 " + str(summary["retries"]) + " 次" if summary["retries"] else "")
    )
    emit("      正样本 top1 语义分数: " + _score_line([
        r["top_score"] for r in ok if r.get("top_score") is not None
    ]))
    return summary


def run_negative(queries) -> dict:
    """负样本：越界查询在生产里会被范围护栏挡在检索之前，这里直接喂原句。

    所以这组衡量的是"如果关键词分支拿到一句非隐患的日常话，会不会自己捞出东西"。
    """
    emit("\n" + "-" * 78)
    emit("负样本：真无关查询  共 " + str(len(queries)) + " 条（期望返回空）")
    emit("-" * 78)
    empty = 0
    scores = []
    errors = 0
    for item in queries:
        outcome = ranked_items(item["query"])
        items = outcome["items"]
        if outcome["error"] is not None:
            errors += 1
            emit("[ERR ] " + item["query"] + " | " + outcome["error"])
            continue
        ranked_ids = [x.get("id") for x in items]
        item_scores = [x["match_score"] for x in items if x.get("match_score") is not None]
        top_score = max(item_scores) if item_scores else None
        if top_score is not None:
            scores.append(top_score)
        if not ranked_ids:
            empty += 1
        top1 = items[0] if items else None
        detail = "无结果"
        if top1:
            detail = "id=" + str(top1.get("id")) + " 类别=" + str(top1.get("category")) \
                + " " + str(top1.get("title", ""))[:20]
        emit(
            "["
            + ("EMPTY" if not ranked_ids else "HIT  ")
            + "] " + item["query"].ljust(20)
            + " 返回=" + str(len(ranked_ids))
            + " top1分数=" + ("%.4f" % top_score if top_score is not None else "n/a")
            + " | " + detail + " | " + item["note"]
        )
    rate = empty / len(queries) if queries else 0.0
    emit(
        "小计: EmptyRate=" + str(empty) + "/" + str(len(queries))
        + " = " + ("%.2f" % rate)
        + (" | 检索异常 " + str(errors) if errors else "")
    )
    if scores:
        emit("      负样本 top1 语义分数: " + _score_line(scores))
    return {"empty_rate": rate, "scores": scores}


def _score_line(scores) -> str:
    scores = sorted(scores)
    if not scores:
        return "无数据"
    middle = scores[len(scores) // 2]
    p10 = scores[max(0, int(len(scores) * 0.1) - 1)]
    return (
        "n=" + str(len(scores))
        + " min=" + ("%.4f" % scores[0])
        + " p10=" + ("%.4f" % p10)
        + " 中位=" + ("%.4f" % middle)
        + " max=" + ("%.4f" % scores[-1])
    )


def no_keyword_tokens(scenario: str) -> list:
    """该情形下"检索串切不出关键词 token"的小类（关键词分支会退回纯向量）。"""
    result = []
    for major, sub in sorted(all_subcategories()):
        if not _tokenize_keyword(production_keyword(sub, scenario)):
            result.append(sub)
    return result


def invisible_fixtures(scenario: str) -> list:
    """槽位值没能进入检索串的小类 —— 说明该小类的槽位键不是 _pick_keyword 会读的那个。"""
    result = []
    for major, sub in sorted(all_subcategories()):
        if production_keyword(sub, scenario) == production_keyword(sub, SCENARIO_EMPTY):
            result.append(sub)
    return result


GOLD = {}


def main() -> int:
    global GOLD

    missing = sorted(all_subcategories() - covered_subcategories())
    if missing:
        emit("自查失败：以下小类没有查询覆盖 -> " + str(missing))
        return 1

    fixture_missing = sorted(
        sub for _, sub in all_subcategories() if sub not in SLOT_VALUES)
    if fixture_missing:
        emit("自查失败：以下小类没有槽位 fixture -> " + str(fixture_missing))
        return 1

    GOLD = load_gold_ids()
    empty_labels = [
        category_label(major, sub)
        for major, sub in sorted(all_subcategories())
        if not GOLD.get(category_label(major, sub))
    ]
    if empty_labels:
        emit("自查失败：以下小类在库里没有任何案例 -> " + str(empty_labels))
        return 1

    emit("=" * 78)
    emit("检索评测（生产路径口径）  金标准 = tb_hazard_case 真实 id")
    emit("检索串 = _pick_keyword(小类, 槽位)，同一个串既喂向量又喂关键词（与生产一致）")
    emit("窗口 top-" + str(WINDOW) + "（语义" + str(VECTOR_K) + " + 关键词" + str(KEYWORD_K)
         + " 合并去重后截断；顺序＝向量在前、关键词补尾，调 HybridSearcher._merge_results）")
    emit("库内案例 " + str(sum(len(v) for v in GOLD.values())) + " 条；查询 "
         + str(len(QUERY_SET)) + " 条；自查 "
         + str(len(all_subcategories())) + "/"
         + str(len(all_subcategories())) + " 覆盖 ✅")
    emit("=" * 78)

    started = time.time()
    summaries = {}
    for scenario in SCENARIOS:
        emit("\n" + "#" * 78)
        emit("# 情形：" + scenario)
        emit("#" * 78)
        explicit = run_group("A 组：直白描述",
                             [q for q in QUERY_SET if q["style"] == "explicit"], scenario)
        colloquial = run_group("B 组：口语/同义改写",
                               [q for q in QUERY_SET if q["style"] == "colloquial"], scenario)
        summaries[scenario] = {"groups": [explicit, colloquial]}
    negative = run_negative(NEGATIVE_SET)
    elapsed = time.time() - started

    emit("\n" + "=" * 78)
    emit("汇总表（每种情形一行；A/B 已合并）")
    emit("=" * 78)
    emit("| 情形 | 条数 | Hit@5 | MRR | P@5 | P@ret | R@5 | R@5设计上限 | 大类Hit@5 "
         "| 平均返回 | 关键词分支有命中 |")
    emit("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for scenario in SCENARIOS:
        groups = summaries[scenario]["groups"]
        merged = {
            "hit": mean([s["hit"] for s in groups]),
            "mrr": mean([s["mrr"] for s in groups]),
            "p5": mean([s["p5"] for s in groups]),
            "p_ret": mean([s["p_ret"] for s in groups]),
            "recall": mean([s["recall"] for s in groups]),
            "ceiling": mean([s["ceiling"] for s in groups]),
            "major_hit": mean([s["major_hit"] for s in groups]),
            "returned": mean([s["returned"] for s in groups]),
        }
        keyword_used = sum(s["keyword_used"] for s in groups)
        count = sum(s["count"] for s in groups)
        emit("| " + scenario + " | " + str(count) + " | "
             + ("%.3f" % merged["hit"]) + " | " + ("%.3f" % merged["mrr"]) + " | "
             + ("%.3f" % merged["p5"]) + " | " + ("%.3f" % merged["p_ret"]) + " | "
             + ("%.3f" % merged["recall"]) + " | " + ("%.3f" % merged["ceiling"]) + " | "
             + ("%.3f" % merged["major_hit"]) + " | "
             + ("%.1f" % merged["returned"]) + " | "
             + str(keyword_used) + "/" + str(count) + " |")

    emit("")
    emit("各组拆解（同一情形内 A/B 分开）")
    for scenario in SCENARIOS:
        for group in summaries[scenario]["groups"]:
            emit("  " + scenario + " / " + group["title"] + " : "
                 + "Hit@5=" + ("%.3f" % group["hit"])
                 + " MRR=" + ("%.3f" % group["mrr"])
                 + " P@5=" + ("%.3f" % group["p5"])
                 + " P@ret=" + ("%.3f" % group["p_ret"])
                 + " R@5=" + ("%.3f" % group["recall"])
                 + " 大类Hit@5=" + ("%.3f" % group["major_hit"])
                 + " 平均返回=" + ("%.1f" % group["returned"])
                 + " 关键词分支有命中=" + str(group["keyword_used"]) + "/" + str(group["count"]))

    emit("")
    emit("诊断清单")
    for scenario in SCENARIOS:
        degenerate = no_keyword_tokens(scenario)
        emit("  [" + scenario + "] 切不出关键词 token 的小类 " + str(len(degenerate))
             + " 个：" + ("、".join(degenerate) if degenerate else "（无）"))
        if scenario != SCENARIO_EMPTY:
            invisible = invisible_fixtures(scenario)
            emit("  [" + scenario + "] 槽位值没进检索串的小类 " + str(len(invisible))
                 + " 个：" + ("、".join(invisible) if invisible else "（无）"))
    emit("  说明：槽位空只有标签一个 token，本来就会全部命中 category；")
    emit("        「槽位值没进检索串」= 该小类的槽位键不是 _pick_keyword 会读的那个键。")

    emit("")
    emit("负样本 EmptyRate=" + ("%.2f" % negative["empty_rate"])
         + "（RETRIEVAL_MIN_SCORE=" + ("%.2f" % MIN_SCORE) + " 生效后；阈值前实测为 0.00）")
    emit("R@5 设计上限 = min(5, 小类条数) / 小类条数 的平均值，满分不是 1.0，读数字时必须减掉上限。")
    emit("口径提醒：本文件的「槽位空」「槽位有值」两行可以和 db/eval_retrieval_baseline.txt 逐条对照；")
    emit("          「槽位有值(schema键)」没有老基线（老实现读不到那些键），只报绝对值。")
    emit("          每例只跑 1 次，没有方差数据。")
    emit("耗时 " + ("%.1f" % elapsed) + " 秒。")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as handle:
        handle.write("\n".join(_lines))
    print("\n[已写入] " + OUTPUT_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
