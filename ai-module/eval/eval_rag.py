"""RAG 检索与报告评估：命中率 / MRR / Recall@k / 负样本 / 失败样本分析。

运行：
  python eval/eval_rag.py            # 检索评估 + 报告评估（读取已缓存报告）
  python eval/eval_rag.py --report   # 报告评估：调用 Report Agent 真实生成后缓存
"""
import argparse
import hashlib
import os
import sys
import time

import json
import pymysql

_HERE = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _AI_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL
from core.agent import Agent
from core.report_context import build_report_context
from db_config import DB_CONFIG
from tools.hybrid_search import searcher

# 期望类别已更新为两级规范体系，支持按大类或细分类灵活评估
TABLE = "tb_hazard_case"
VECTOR_K = 3
KEYWORD_K = 3
REPORT_EVAL_DIR = os.path.join(_AI_ROOT, "db", "eval_reports")

EVAL_SET = [
    {
        "query": "电动车入户充电引发火灾",
        "expected_category": "消防安全/消防通道占用",
        "required_keywords": ["电瓶车", "充电", "火灾"],
    },
    {
        "query": "建筑工地脚手架坍塌坠落",
        "expected_category": "施工安全/脚手架/临边防护",
        "required_keywords": ["脚手架", "坍塌"],
    },
    {
        "query": "燃气管道泄漏爆燃",
        "expected_category": "电气与燃气/燃气泄漏",
        "required_keywords": ["燃气", "爆燃"],
    },
    {
        "query": "电梯井口防护缺失工人坠落身亡",
        "expected_category": "施工安全/脚手架/临边防护",
        "required_keywords": ["电梯", "坠落"],
    },
    {
        "query": "液化气罐泄漏闪爆",
        "expected_category": "电气与燃气/燃气泄漏",
        "required_keywords": ["液化气", "闪爆"],
    },
    {
        "query": "人行道盲道被共享单车和摊位完全堵死",
        "expected_category": "交通与通行/盲道占用",
        "required_keywords": ["盲道", "占用"],
    },
    {
        "query": "暴雨夜雨水井盖缺失移位行人涉水坠井",
        "expected_category": "市政设施/井盖缺失/破损",
        "required_keywords": ["井盖", "坠井"],
    },
    {
        "query": "下穿隧道暴雨严重积水轿车被淹",
        "expected_category": "市政设施/排水/积水",
        "required_keywords": ["隧道", "积水"],
    },
    {
        "query": "高层大厦外立面大理石瓷砖脱落砸坏车辆",
        "expected_category": "建筑安全/外立面脱落",
        "required_keywords": ["外立面", "脱落"],
    },
    {
        "query": "高空抛掷红酒瓶砸碎汽车挡风玻璃",
        "expected_category": "建筑安全/高空坠物",
        "required_keywords": ["高空", "抛物"],
    },
    {
        "query": "客运电梯故障急停困人超过半小时救援超时",
        "expected_category": "电梯与特种设备/电梯困人",
        "required_keywords": ["电梯", "困人"],
    },
    {
        "query": "深基坑支护桩严重位移开裂边坡滑移",
        "expected_category": "施工安全/深基坑风险",
        "required_keywords": ["基坑", "支护"],
    },
    {
        "query": "工厂私设暗管向市政管网偷排重金属酸洗废水",
        "expected_category": "环境与其他/污水/异味",
        "required_keywords": ["暗管", "偷排"],
    },
]

HARD_EVAL_SET = [
    {
        "query": "电驴推上楼充电，半夜起火",
        "expected_category": "消防安全/消防通道占用",
        "note": "同义改写：电驴=电瓶车/电动自行车",
    },
    {
        "query": "小区楼道堆放易燃杂物引发火情",
        "expected_category": "消防安全/消防通道占用",
        "note": "模糊查询：未出现火灾设备词",
    },
    {
        "query": "工人在电梯井内踩空摔落",
        "expected_category": "施工安全/脚手架/临边防护",
        "note": "跨类别混淆：电梯相关但属于建筑施工",
    },
    {
        "query": "地铁施工导致燃气管道破损",
        "expected_category": "施工安全/深基坑风险",
        "note": "长尾场景：施工+燃气组合",
    },
]

NEGATIVE_SET = [
    {"query": "今天上海天气怎么样", "note": "无关领域：天气"},
    {"query": "红烧肉怎么做好吃", "note": "无关领域：美食"},
    {"query": "帮我写一首关于秋天的诗", "note": "无关领域：文学创作"},
    {"query": "推荐一部适合周末看的电影", "note": "无关领域：影评"},
    {"query": "Python 列表如何去重", "note": "无关领域：编程"},
]

REPORT_EVAL_SET = [
    {
        "query": "电动车入户充电引发火灾",
        "required_keywords": ["充电", "火灾", "整改", "类似案例"],
        "forbidden": ["燃气", "电梯"],
        "golden_context": {
            "vision": {"hazard_category": "消防安全", "severity": "高",
                       "description": "电动车入户充电引发火灾"},
            "cases": ("类似案例：重庆29楼电瓶车入户充电致2名邻居死亡；"
                      "湖北枣阳楼栋大厅电动车充电起火烧伤租户。"),
            "policy": "政策依据：《高层民用建筑消防安全管理规定》禁止电动自行车入户停放充电。",
            "regulations": "法规依据：《中华人民共和国消防法》第六十四条。",
        },
    },
    {
        "query": "建筑工地脚手架坍塌坠落",
        "required_keywords": ["脚手架", "坠落", "整改", "类似案例"],
        "forbidden": ["燃气", "电梯"],
        "golden_context": {
            "vision": {"hazard_category": "建筑施工", "severity": "高",
                       "description": "建筑工地脚手架坍塌坠落"},
            "cases": ("类似案例：深江铁路地面坍塌重大事故致13死；"
                      "本溪工业厂房违规拆除坍塌致3死。"),
            "policy": "政策依据：《建筑施工高处作业安全技术规范》要求设置防护网与临边防护。",
            "regulations": "法规依据：《建设工程安全生产管理条例》第二十六条。",
        },
    },
]


def check_report(report: str, required: list[str], forbidden: list[str] | None = None) -> dict:
    """关键词级报告检查：漏项检测 + 幻觉标记检测。"""
    missing = [k for k in required if k not in report]
    hallucinated = [k for k in (forbidden or []) if k in report]
    return {
        "missing": missing,
        "hallucinated": hallucinated,
        "pass": not missing and not hallucinated,
    }


def _category_total(category: str) -> int:
    """某类别在案例库中的总条数（作为召回率的“全部相关文档数”）。"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE category LIKE %s", (f"%{category}%",))
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def _ranked_results(query: str, vector_k: int = VECTOR_K, keyword_k: int = KEYWORD_K) -> list[dict]:
    """复用生产检索分支，按生产合并顺序重建排名：关键词在前、向量补充、按 id 去重。

    生产 hybrid_search() 格式化时最多展示 max(vector_k, keyword_k) + 2 条，
    这里同样截断，保证 MRR/Recall@k 衡量的是 LLM 真正能看到的窗口。
    """
    keyword_results = searcher.keyword_search(query, TABLE, limit=keyword_k)
    vector_results = searcher.vector_search(query, TABLE, top_k=vector_k)

    seen = set()
    merged = []
    for r in keyword_results:
        rid = r["id"]
        if rid not in seen:
            seen.add(rid)
            item = dict(r)
            item["match_type"] = "关键词"
            merged.append(item)
    for r in vector_results:
        rid = r.get("id")
        if rid is not None and rid not in seen:
            seen.add(rid)
            item = dict(r)
            item["match_type"] = "语义"
            merged.append(item)
    return merged[:max(vector_k, keyword_k) + 2]


def _is_relevant(item: dict, category: str) -> bool:
    item_cat = (item.get("category") or "").strip()
    return item_cat == category or (category in item_cat) or (item_cat in category)


def _evaluate_query(query: str, expected_category: str) -> dict:
    started = time.perf_counter()
    try:
        ranked = _ranked_results(query)
    except Exception as exc:
        return {
            "query": query,
            "expected": expected_category,
            "error": f"{type(exc).__name__}: {exc}",
            "ranked": [], "first_rank": None, "mrr": 0.0,
            "recall3": 0.0, "recall_full": 0.0, "hit": False, "elapsed_ms": 0.0,
        }
    elapsed_ms = (time.perf_counter() - started) * 1000
    total_relevant = _category_total(expected_category)

    first_rank = None
    for rank, item in enumerate(ranked, 1):
        if _is_relevant(item, expected_category):
            first_rank = rank
            break
    mrr = 1.0 / first_rank if first_rank else 0.0

    relevant_top3 = sum(1 for item in ranked[:3] if _is_relevant(item, expected_category))
    relevant_all = sum(1 for item in ranked if _is_relevant(item, expected_category))
    recall3 = relevant_top3 / total_relevant if total_relevant else 0.0
    recall_full = relevant_all / total_relevant if total_relevant else 0.0

    return {
        "query": query,
        "expected": expected_category,
        "ranked": ranked,
        "first_rank": first_rank,
        "mrr": mrr,
        "recall3": recall3,
        "recall_full": recall_full,
        "hit": first_rank is not None,
        "elapsed_ms": elapsed_ms,
    }


def _run_retrieval_set(title: str, items: list[dict]) -> list[dict]:
    print(f"\n===== {title} =====")
    results = []
    for item in items:
        res = _evaluate_query(item["query"], item["expected_category"])
        results.append(res)
        if "error" in res:
            print(f"[FAIL] {res['query']} -> {res['error']}")
            continue
        note = f" | {item['note']}" if item.get("note") else ""
        print(
            f"[{'PASS' if res['hit'] else 'FAIL'}] {res['query']} | 期望={res['expected']} | "
            f"首个相关排名={res['first_rank']} | MRR={res['mrr']:.3f} | "
            f"Recall@3={res['recall3']:.3f} | Recall@all={res['recall_full']:.3f} | "
            f"{res['elapsed_ms']:.0f}ms{note}"
        )
        for i, item2 in enumerate(res["ranked"], 1):
            print(f"    {i}. id={item2['id']} 类别={item2.get('category')} "
                  f"[{item2['match_type']}] {item2.get('title', '')}")

    valid = [r for r in results if "error" not in r]
    if valid:
        n = len(valid)
        print(
            f"\n汇总: 命中率={sum(r['hit'] for r in valid)}/{n} | "
            f"MRR={sum(r['mrr'] for r in valid) / n:.3f} | "
            f"Recall@3={sum(r['recall3'] for r in valid) / n:.3f} | "
            f"Recall@all={sum(r['recall_full'] for r in valid) / n:.3f}"
        )
    return results


def run_negative_eval() -> None:
    print("\n===== 负样本评估（无关查询，期望关键词 0 命中）=====")
    passed = 0
    for item in NEGATIVE_SET:
        query = item["query"]
        ranked = _ranked_results(query)
        keyword_hits = sum(1 for r in ranked if r["match_type"] == "关键词")
        top1 = ranked[0] if ranked else None
        top1_info = (f"id={top1['id']} 类别={top1.get('category')} "
                     f"「{top1.get('title', '')}」") if top1 else "无结果"
        ok = keyword_hits == 0
        passed += int(ok)
        print(
            f"[{'PASS' if ok else 'FAIL'}] {query} | 关键词命中={keyword_hits} | "
            f"返回条数={len(ranked)} | Top1: {top1_info} | {item['note']}"
        )
        for i, r in enumerate(ranked[:3], 1):
            print(f"    {i}. id={r['id']} 类别={r.get('category')} "
                  f"[{r['match_type']}] {r.get('title', '')}")
    print(
        f"\n汇总: 关键词拒绝率={passed}/{len(NEGATIVE_SET)} | "
        f"注意: 向量检索对无关查询仍返回 {VECTOR_K} 条（无顶层相关度门槛），"
        f"生产环境应加相似度阈值或低置信提示"
    )

def run_failure_analysis(all_results: list[dict]) -> None:
    print("\n===== 失败样本分析 =====")
    failed = [r for r in all_results if "error" not in r and not r["hit"]]
    if not failed:
        print("无失败样本：所有查询的第一个相关文档都进入了返回列表，未见漏检。")
        return
    for r in failed:
        print(f"[FAIL] {r['query']} | 期望类别={r['expected']} | 首个相关排名={r['first_rank']}")
        for i, item in enumerate(r["ranked"], 1):
            print(f"    {i}. id={item['id']} 类别={item.get('category')} "
                  f"[{item['match_type']}] {item.get('title', '')}")


def _report_cache_path(query: str) -> str:
    digest = hashlib.md5(query.encode("utf-8")).hexdigest()[:10]
    return os.path.join(REPORT_EVAL_DIR, f"{digest}.txt")


REPORT_SYSTEM_PROMPT = "你是城市安全隐患分析报告撰写专家。只输出 Markdown 报告，不要输出工具调用。"


def _generate_report(query: str, golden_context: dict) -> str:
    """用固定检索上下文生成报告：隔离“检索质量”，只评估报告生成质量。"""
    report_agent = Agent(
        name="report", system_prompt=REPORT_SYSTEM_PROMPT, tools=[],
        base_url=MIMO_BASE_URL, api_key=MIMO_API_KEY, model=MIMO_MODEL,
    )
    prompt = build_report_context(query, golden_context)
    prompt += (
        "\n\n请基于以上所有信息生成一份完整的安全隐患分析报告。"
        "\n报告中的「类似案例」章节必须引用上面提供的真实案例（含城市、伤亡、判决结果），不要自行编造。"
    )
    report = report_agent.run(prompt)
    os.makedirs(REPORT_EVAL_DIR, exist_ok=True)
    with open(_report_cache_path(query), "w", encoding="utf-8") as f:
        f.write(report)
    return report


def run_report_eval(regenerate: bool = False) -> None:
    print("\n===== 报告评估：关键要点覆盖 =====")
    print("说明：检索结果固定为 golden_context，单独评估 Report Agent；LLM-as-judge 为演进方向。")
    for item in REPORT_EVAL_SET:
        query = item["query"]
        path = _report_cache_path(query)
        cached = os.path.exists(path) and not regenerate
        if cached:
            with open(path, "r", encoding="utf-8") as f:
                report = f.read()
        else:
            report = _generate_report(query, item["golden_context"])
        result = check_report(report, item["required_keywords"], item.get("forbidden"))
        print(
            f"[{'PASS' if result['pass'] else 'FAIL'}] {query} | 报告长度={len(report)}字 | "
            f"缓存={'是' if cached else '否'}"
        )
        print(f"    缺漏要点: {result['missing'] or '无'} | 幻觉标记: {result['hallucinated'] or '无'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 检索与报告评估")
    parser.add_argument("--report", action="store_true", help="重新生成并评估报告（调用 LLM）")
    args = parser.parse_args()

    basic_results = _run_retrieval_set("基础查询评估（tb_hazard_case）", EVAL_SET)
    hard_results = _run_retrieval_set("困难查询评估（同义改写/模糊/跨类别）", HARD_EVAL_SET)
    run_negative_eval()
    run_failure_analysis(basic_results + hard_results)
    run_report_eval(regenerate=args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())