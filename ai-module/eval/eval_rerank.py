# -*- coding: utf-8 -*-
"""Read-only comparison of baseline, filtered candidates, and reranking."""

import json
import os
import sys
import time
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_AI_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _AI_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import (
    RERANK_API_KEY,
    RERANK_BASE_URL,
    RERANK_CANDIDATE_K,
    RERANK_ENABLED,
    RERANK_FINAL_K,
    RERANK_MODEL,
    RERANK_TIMEOUT_SECONDS,
)
from core.assistant_graph import _pick_keyword
from core.dialogue_understanding import understand as planner_understand
from core.reranker import NoopReranker, safe_rerank_outcome
from core.reranker_http import HTTPReranker
from core.skill_registry import get_skill_registry
from core.skill_router import route_llm_with_agent, route_skills
from tools.assistant_tools import ASSISTANT_TOOLS
from eval.eval_metrics import hit_at_k, mrr, precision_at_k, recall_at_k
from eval.eval_queries import NEGATIVE_SET, QUERY_SET, category_label
from tools.hybrid_search import searcher


_skill_registry = get_skill_registry(
    Path(_AI_ROOT) / "skills",
    {tool.name for tool in ASSISTANT_TOOLS},
)
_route_skills = route_skills
_planner_understand = planner_understand


def evaluate_ranked(ranked_ids, gold_ids, k=5):
    if k <= 0:
        raise ValueError("k must be positive")
    gold = set(gold_ids or [])
    first = None
    for index, item_id in enumerate(ranked_ids or [], 1):
        if item_id in gold:
            first = index
            break
    recall, ceiling = recall_at_k(ranked_ids or [], gold, k)
    return {
        "top1": bool(ranked_ids and ranked_ids[0] in gold),
        "hit": hit_at_k(ranked_ids or [], gold, k),
        "first_rank": first,
        "mrr": mrr(ranked_ids or [], gold),
        "p_at_5": precision_at_k(ranked_ids or [], gold, k),
        "recall_at_5": recall,
        "ceil_at_5": ceiling,
        "top": list(ranked_ids or [])[:k],
    }


def gate_result(baseline, rerank, reranker_enabled=True):
    reasons = []
    if not reranker_enabled:
        reasons.append("reranker is disabled; Noop mode is not model performance")
    if not rerank.get("production_prediction_ok", False):
        reasons.append("production prediction incomplete or failed")
    if rerank["hit_at_5"] < 1.0:
        reasons.append("Hit@5 fell below 1.000")
    if rerank["mrr"] < baseline["mrr"] + 0.025:
        reasons.append("MRR improvement below 0.025")
    if rerank["top1_hits"] < baseline["top1_hits"] + 5:
        reasons.append("Top-1 hits below baseline + 5")
    if int(rerank.get("top1_regressions", 0)) != 0:
        reasons.append("Top-1 regression detected")
    if reranker_enabled:
        attempts = int(rerank.get("rerank_attempts", 0))
        successes = int(rerank.get("rerank_successes", 0))
        fallbacks = int(rerank.get("rerank_fallbacks", 0))
        expected_attempts = int(rerank.get("expected_rerank_attempts", 0))
        if attempts <= 0 or successes < attempts:
            reasons.append("reranker successful responses below attempts")
        if expected_attempts and attempts != expected_attempts:
            reasons.append("reranker attempts do not match positive query count")
        if fallbacks != 0:
            reasons.append("reranker fallback count must be 0")
    if rerank.get("rerank_p95_ms", 999999) > 350:
        reasons.append("rerank P95 exceeds 350ms")
    if rerank.get("added_p95_ms", 999999) > 500:
        reasons.append("end-to-end added P95 exceeds 500ms")
    if rerank.get("empty_rate", 0.0) < 1.0:
        reasons.append("negative EmptyRate dropped below 1.00")
    return {"passed": not reasons, "reason": "; ".join(reasons)}


def predict_production(query):
    """Predict hazard major/subcategory with the production planner path.

    Gold labels are never accepted as inputs. The raw user query is the only
    semantic input; gold is used later by the evaluator for scoring only.
    """
    route = _route_skills(
        text=query,
        metadata_catalog=_skill_registry.metadata_catalog(),
        selected_major_codes=[],
        locked_majors=[],
        vision_categories=[],
        route_llm=route_llm_with_agent,
    )
    active = list(route.get("active_skills") or [])
    bodies = {}
    for code in active:
        try:
            bodies[code] = _skill_registry.load_body(code)
        except Exception:
            bodies.pop(code, None)
    try:
        plan = _planner_understand(
            [{"role": "user", "content": query}],
            "",
            "",
            active_skill_codes=active,
            skill_bodies=bodies,
        )
    except Exception:
        plan = {}
    plan = plan if isinstance(plan, dict) else {}
    issues = [item for item in (plan.get("issues") or []) if isinstance(item, dict)]
    primary = next(
        (item for item in issues if str(item.get("major_code") or "").strip()),
        {},
    )
    predicted_major = str(
        primary.get("major_code") or plan.get("perceived_major") or ""
    ).strip()
    predicted_subcategory = str(
        primary.get("subcategory_code") or plan.get("perceived_subcategory") or ""
    ).strip()
    slots = dict(primary.get("slots") or {})
    premises_scope = str(plan.get("premises_scope") or "public")
    keyword = (
        _pick_keyword(predicted_subcategory, slots, premises_scope)
        if predicted_subcategory else str(query)
    )
    majors = []
    subcategories = []
    for item in issues:
        major = str(item.get("major_code") or "").strip()
        subcategory = str(item.get("subcategory_code") or "").strip()
        if major and major not in majors:
            majors.append(major)
        if subcategory and subcategory not in subcategories:
            subcategories.append(subcategory)
    return {
        "query": str(query),
        "planner_ok": bool(plan.get("ok")),
        "skill_route_source": route.get("source", "fallback"),
        "active_skills": active,
        "predicted_major": predicted_major,
        "predicted_subcategory": predicted_subcategory,
        "predicted_majors": majors,
        "predicted_subcategories": subcategories,
        "predicted_slots": slots,
        "premises_scope": premises_scope,
        "keyword": keyword,
        "keyword_source": "production_pick_keyword" if predicted_subcategory else "raw_query",
    }


def _reranker():
    if not RERANK_ENABLED:
        return NoopReranker()
    return HTTPReranker(
        base_url=RERANK_BASE_URL,
        api_key=RERANK_API_KEY,
        model=RERANK_MODEL,
    )


def _ids(items):
    return [int(item["id"]) for item in items if item.get("id") is not None]


def _record(items, gold, retrieval_ms, rerank_ms=0.0,
            rerank_outcome=None, candidate_count=None, gold_in_candidates=None):
    metrics = evaluate_ranked(_ids(items), gold, RERANK_FINAL_K)
    if gold_in_candidates is None:
        gold_in_candidates = bool(set(_ids(items)) & set(gold))
    metrics.update({
        "latency_ms": retrieval_ms + rerank_ms,
        "retrieval_latency_ms": retrieval_ms,
        "rerank_latency_ms": rerank_ms,
        "candidate_count": (
            int(candidate_count) if candidate_count is not None else len(items)
        ),
        "gold_in_candidates": bool(gold_in_candidates),
        "rerank_attempted": rerank_outcome is not None,
        "rerank_success": bool(rerank_outcome and rerank_outcome["used_reranker"]),
        "rerank_fallback_reason": (
            rerank_outcome["fallback_reason"] if rerank_outcome else None
        ),
        "rerank_reranked_count": (
            rerank_outcome["reranked_count"] if rerank_outcome else 0
        ),
        "rerank_filled_from_original": (
            rerank_outcome["filled_from_original"] if rerank_outcome else 0
        ),
    })
    return metrics


def _collect_baseline(keyword, gold):
    retrieval_started = time.perf_counter()
    items = searcher.retrieve_candidates(
        keyword, "tb_hazard_case", vector_k=3, keyword_k=3
    )
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000.0
    return _record(items, gold, retrieval_ms)


def _collect_candidate_pair(keyword, gold, major_code, reranker):
    retrieval_started = time.perf_counter()
    if major_code:
        items = searcher.retrieve_rerank_candidates(
            keyword, "tb_hazard_case",
            major_code=major_code,
            vector_k=RERANK_CANDIDATE_K,
            keyword_k=RERANK_CANDIDATE_K,
        )
    else:
        # Negative queries have no hazard major; upstream scope guard blocks them.
        items = searcher.retrieve_candidates(
            keyword, "tb_hazard_case", vector_k=3, keyword_k=3
        )
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000.0
    candidate_count = len(items)
    gold_in_candidates = bool(set(_ids(items)) & set(gold))
    candidate_record = _record(
        items, gold, retrieval_ms, candidate_count=candidate_count,
        gold_in_candidates=gold_in_candidates,
    )

    rerank_started = time.perf_counter()
    rerank_outcome = safe_rerank_outcome(
        reranker, keyword, items, RERANK_FINAL_K,
        timeout_seconds=RERANK_TIMEOUT_SECONDS,
        require_score=RERANK_ENABLED,
    )
    rerank_ms = (time.perf_counter() - rerank_started) * 1000.0
    rerank_record = _record(
        rerank_outcome["items"], gold, retrieval_ms, rerank_ms,
        rerank_outcome=rerank_outcome, candidate_count=candidate_count,
        gold_in_candidates=gold_in_candidates,
    )
    return candidate_record, rerank_record


def summarize_records(rows, negative_empty=0, negative_total=0):
    if not rows:
        return {
            "hit_at_5": 0.0,
            "mrr": 0.0,
            "top1_hits": 0,
            "p_at_5": 0.0,
            "recall_at_5": 0.0,
            "empty_rate": negative_empty / max(1, negative_total),
            "avg_candidate_count": 0.0,
            "gold_in_candidates_rate": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "retrieval_p50_ms": 0.0,
            "retrieval_p95_ms": 0.0,
            "rerank_p50_ms": 0.0,
            "rerank_p95_ms": 0.0,
            "rerank_attempts": 0,
            "rerank_successes": 0,
            "rerank_fallbacks": 0,
            "rerank_fallback_reasons": {},
        }
    count = len(rows)
    latencies = [row.get("latency_ms", 0.0) for row in rows]
    retrieval_latencies = [
        row.get("retrieval_latency_ms", row.get("latency_ms", 0.0))
        for row in rows
    ]
    rerank_latencies = [row.get("rerank_latency_ms", 0.0) for row in rows]
    fallback_reasons = {}
    for row in rows:
        reason = row.get("rerank_fallback_reason")
        if reason:
            fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
    return {
        "hit_at_5": sum(1.0 for row in rows if row["hit"]) / count,
        "mrr": sum(row["mrr"] for row in rows) / count,
        "top1_hits": sum(1 for row in rows if row["top1"]),
        "p_at_5": sum(row["p_at_5"] for row in rows) / count,
        "recall_at_5": sum(row["recall_at_5"] for row in rows) / count,
        "empty_rate": negative_empty / max(1, negative_total),
        "avg_candidate_count": sum(row.get("candidate_count", 0) for row in rows) / count,
        "gold_in_candidates_rate": sum(1 for row in rows if row.get("gold_in_candidates")) / count,
        "p50_ms": _p50(latencies),
        "p95_ms": _p95(latencies),
        "retrieval_p50_ms": _p50(retrieval_latencies),
        "retrieval_p95_ms": _p95(retrieval_latencies),
        "rerank_p50_ms": _p50(rerank_latencies),
        "rerank_p95_ms": _p95(rerank_latencies),
        "rerank_attempts": sum(1 for row in rows if row.get("rerank_attempted")),
        "rerank_successes": sum(1 for row in rows if row.get("rerank_success")),
        "rerank_fallbacks": sum(
            1 for row in rows
            if row.get("rerank_attempted") and not row.get("rerank_success")
        ),
        "rerank_fallback_reasons": fallback_reasons,
    }


def _failure_samples(rows):
    return [
        {
            "query": row["query"],
            "label": row["label"],
            "style": row["style"],
            "first_rank": row["first_rank"],
            "hit": row["hit"],
            "candidate_count": row.get("candidate_count", 0),
            "gold_in_candidates": row.get("gold_in_candidates", False),
            "top": row["top"],
            "rerank_fallback_reason": row.get("rerank_fallback_reason"),
        }
        for row in rows
        if not row["top1"]
    ]


def _percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def _p50(values):
    return _percentile(values, 0.50)


def _p95(values):
    return _percentile(values, 0.95)


def main():
    from eval.eval_retrieval import load_gold_ids
    if RERANK_FINAL_K != 5:
        raise ValueError("rerank production gate requires RERANK_FINAL_K=5")
    gold_by_label = load_gold_ids()
    modes = ("baseline", "candidates", "rerank")
    records = {mode: [] for mode in modes}
    negatives = {mode: 0 for mode in modes}
    predictions = []
    reranker = _reranker()

    for item in QUERY_SET:
        prediction = predict_production(item["query"])
        predictions.append(prediction)
        keyword = prediction["keyword"]
        label = category_label(item["major"], item["subcategory"])
        gold = gold_by_label.get(label, set())
        baseline_row = _collect_baseline(keyword, gold)
        candidate_row, rerank_row = _collect_candidate_pair(
            keyword, gold, prediction["predicted_major"], reranker
        )
        for mode, row in (
            ("baseline", baseline_row),
            ("candidates", candidate_row),
            ("rerank", rerank_row),
        ):
            row.update({
                "query": item["query"],
                "label": label,
                "style": item["style"],
                "gold_major": item["major"],
                "gold_subcategory": item["subcategory"],
                "prediction": prediction,
                "predicted_major_match": prediction["predicted_major"] == item["major"],
                "predicted_subcategory_match": prediction["predicted_subcategory"] == item["subcategory"],
            })
            records[mode].append(row)

    for item in NEGATIVE_SET:
        prediction = predict_production(item["query"])
        predictions.append(prediction)
        keyword = prediction["keyword"]
        baseline_row = _collect_baseline(keyword, set())
        candidate_row, rerank_row = _collect_candidate_pair(
            keyword, set(), prediction["predicted_major"], reranker
        )
        for mode, row in (
            ("baseline", baseline_row),
            ("candidates", candidate_row),
            ("rerank", rerank_row),
        ):
            row.update({
                "query": item["query"],
                "prediction": prediction,
            })
            if not row["top"]:
                negatives[mode] += 1

    summaries = {
        mode: summarize_records(records[mode], negatives[mode], len(NEGATIVE_SET))
        for mode in modes
    }
    summaries["rerank"]["top1_moves"] = sum(
        1 for baseline_row, rerank_row in zip(records["baseline"], records["rerank"])
        if not baseline_row["top1"] and rerank_row["top1"]
    )
    summaries["rerank"]["top1_regressions"] = sum(
        1 for baseline_row, rerank_row in zip(records["baseline"], records["rerank"])
        if baseline_row["top1"] and not rerank_row["top1"]
    )
    summaries["candidates"]["added_p95_ms"] = _p95([
        row["latency_ms"] - baseline_row["latency_ms"]
        for baseline_row, row in zip(records["baseline"], records["candidates"])
    ])
    summaries["rerank"]["added_p95_ms"] = _p95([
        row["latency_ms"] - baseline_row["latency_ms"]
        for baseline_row, row in zip(records["baseline"], records["rerank"])
    ])
    positive_predictions = [
        row["prediction"] for row in records["baseline"]
    ]
    prediction_attempts = len(predictions)
    prediction_successes = sum(1 for row in predictions if row["planner_ok"])
    missing_major = sum(1 for row in positive_predictions if not row["predicted_major"])
    missing_subcategory = sum(
        1 for row in positive_predictions if not row["predicted_subcategory"]
    )
    major_mismatch = sum(
        1 for row, gold_row in zip(positive_predictions, QUERY_SET)
        if row["predicted_major"] != gold_row["major"]
    )
    subcategory_mismatch = sum(
        1 for row, gold_row in zip(positive_predictions, QUERY_SET)
        if row["predicted_subcategory"] != gold_row["subcategory"]
    )
    summaries["rerank"]["expected_rerank_attempts"] = len(QUERY_SET)
    summaries["rerank"]["production_prediction_ok"] = bool(
        prediction_successes == prediction_attempts
        and missing_major == 0
        and missing_subcategory == 0
    )

    gate = gate_result(
        summaries["baseline"],
        summaries["rerank"],
        reranker_enabled=RERANK_ENABLED,
    )
    rerank_summary = summaries["rerank"]
    if not RERANK_ENABLED:
        effective_model_mode = "noop"
    elif (rerank_summary["rerank_attempts"] > 0
          and rerank_summary["rerank_successes"] == rerank_summary["rerank_attempts"]):
        effective_model_mode = "http"
    else:
        effective_model_mode = "fallback"
    payload = {
        "date": "2026-11-27",
        "rerank_enabled": RERANK_ENABLED,
        "model_mode": "http" if RERANK_ENABLED else "noop",
        "effective_model_mode": effective_model_mode,
        "oracle_major_filter": False,
        "prediction_mode": "production_planner",
        "gate_policy": {
            "hit_at_5_min": 1.0,
            "mrr_absolute_improvement_min": 0.025,
            "top1_hits_min_delta": 5,
            "top1_regressions_max": 0,
            "rerank_p95_ms_max": 350.0,
            "end_to_end_added_p95_ms_max": 500.0,
            "negative_empty_rate_min": 1.0,
            "rerank_fallbacks_max": 0,
        },
        "prediction_summary": {
            "attempts": prediction_attempts,
            "successes": prediction_successes,
            "missing_major": missing_major,
            "missing_subcategory": missing_subcategory,
            "major_mismatch": major_mismatch,
            "subcategory_mismatch": subcategory_mismatch,
            "ok": summaries["rerank"]["production_prediction_ok"],
        },
        "candidate_policy": {
            "baseline": "vector_k=3, keyword_k=3, existing merge",
            "candidates": "vector_k=5, keyword_k=5, predicted major filter, id dedupe, no source-priority truncation",
            "final_k": RERANK_FINAL_K,
        },
        "predictions": predictions,
        "candidate_k": RERANK_CANDIDATE_K,
        "final_k": RERANK_FINAL_K,
        "model": RERANK_MODEL,
        "counts": {
            "case_count": sum(len(ids) for ids in gold_by_label.values()),
            "query_count": len(QUERY_SET),
            "negative_count": len(NEGATIVE_SET),
        },
        "summaries": summaries,
        "failure_samples": {
            mode: _failure_samples(records[mode])
            for mode in modes
        },
        "gate": gate,
    }
    out = Path(_AI_ROOT) / "db" / "eval_rerank_output.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
