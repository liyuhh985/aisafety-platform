"""最小 RAG/Agent 评估：检索命中率 + 报告关键词检查。

运行：python eval_rag.py
"""
import sys
import time

from tools.hybrid_search import searcher

EVAL_SET = [
    {
        "query": "电动车入户充电引发火灾",
        "expected_category": "消防安全",
        "required_keywords": ["电瓶车", "充电", "火灾"],
    },
    {
        "query": "建筑工地脚手架坍塌坠落",
        "expected_category": "建筑施工",
        "required_keywords": ["脚手架", "坍塌"],
    },
    {
        "query": "燃气管道泄漏爆燃",
        "expected_category": "燃气安全",
        "required_keywords": ["燃气", "爆燃"],
    },
    {
        "query": "电梯井口防护缺失工人坠落身亡",
        "expected_category": "建筑施工",
        "required_keywords": ["电梯", "坠落"],
    },
    {
        "query": "液化气罐泄漏闪爆",
        "expected_category": "燃气安全",
        "required_keywords": ["液化气", "闪爆"],
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


HARD_EVAL_SET = [
    {
        "query": "电驴推上楼充电，半夜起火",
        "expected_category": "消防安全",
        "note": "同义改写：电驴=电瓶车/电动自行车",
    },
    {
        "query": "小区楼道堆放易燃杂物引发火情",
        "expected_category": "消防安全",
        "note": "模糊查询：未出现火灾设备词",
    },
    {
        "query": "工人在电梯井内踩空摔落",
        "expected_category": "建筑施工",
        "note": "跨类别混淆：电梯相关但属于建筑施工",
    },
    {
        "query": "地铁施工导致燃气管道破损",
        "expected_category": "燃气安全",
        "note": "长尾场景：施工+燃气组合",
    },
]


def run_hard_eval() -> None:
    hits = 0
    total = len(HARD_EVAL_SET)
    print("\n===== 困难查询评估（同义改写/模糊/跨类别）=====")
    for item in HARD_EVAL_SET:
        query = item["query"]
        expected = item["expected_category"]
        started = time.perf_counter()
        try:
            text = searcher.hybrid_search(query, "tb_hazard_case", vector_k=3, keyword_k=3)
        except Exception as exc:
            print(f"[FAIL] {query} -> 异常: {type(exc).__name__}")
            continue
        elapsed = (time.perf_counter() - started) * 1000
        hit = expected in text
        if hit:
            hits += 1
        print(f"[{'PASS' if hit else 'FAIL'}] {query} | 期望={expected} | 命中={hit} | {elapsed:.0f}ms | {item['note']}")
    print(f"困难查询命中率 = {hits}/{total} = {hits / total:.2%}")

def main() -> None:
    hits = 0
    total = len(EVAL_SET)
    print("===== 检索命中评估（tb_hazard_case）=====")
    for item in EVAL_SET:
        query = item["query"]
        expected = item["expected_category"]
        started = time.perf_counter()
        try:
            text = searcher.hybrid_search(query, "tb_hazard_case", vector_k=3, keyword_k=3)
        except Exception as exc:
            print(f"[FAIL] {query} -> 异常: {type(exc).__name__}")
            continue
        elapsed = (time.perf_counter() - started) * 1000
        hit = expected in text
        if hit:
            hits += 1
        print(f"[{'PASS' if hit else 'FAIL'}] {query} | 期望类别={expected} | 命中={hit} | {elapsed:.0f}ms")

    hit_rate = hits / total if total else 0
    print(f"\n命中率 = {hits}/{total} = {hit_rate:.2%}")

    run_hard_eval()
    print("\n===== 报告关键词检查（框架演示）=====")
    sample_report = (
        "经现场勘察，该隐患为电动自行车入户充电引发火灾，"
        "属于消防安全隐患，建议清理楼道充电行为。"
    )
    result = check_report(sample_report, ["充电", "消防安全"], forbidden=["建筑施工"])
    print(f"required_missing={result['missing']} forbidden_hit={result['hallucinated']} pass={result['pass']}")


if __name__ == "__main__":
    sys.exit(main())