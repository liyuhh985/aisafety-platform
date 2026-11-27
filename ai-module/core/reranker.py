# -*- coding: utf-8 -*-
"""Reranker interface and safe fallback wrapper for retrieval experiments."""

import math
from typing import Protocol

from config import RERANK_TIMEOUT_SECONDS
from core.cancellation import StreamCancelled


class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[dict], final_k: int,
               cancellation=None, timeout_seconds: float = RERANK_TIMEOUT_SECONDS) -> list[dict]:
        """Return candidates in reranked order."""
        ...


class NoopReranker:
    def rerank(self, query: str, candidates: list[dict], final_k: int,
               cancellation=None, timeout_seconds: float = RERANK_TIMEOUT_SECONDS) -> list[dict]:
        return list(candidates[:max(0, int(final_k))])


def _fallback(candidates: list[dict], final_k: int, reason: str) -> dict:
    return {
        "items": candidates[:final_k],
        "used_reranker": False,
        "fallback_reason": reason,
        "reranked_count": 0,
        "filled_from_original": min(final_k, len(candidates)),
    }


def _valid_score(item: dict) -> bool:
    score = item.get("rerank_score")
    return (not isinstance(score, bool)
            and isinstance(score, (int, float))
            and math.isfinite(float(score)))


def _hashable_id(value) -> bool:
    if value is None:
        return False
    try:
        hash(value)
    except Exception:
        return False
    return True


def safe_rerank_outcome(reranker, query: str, candidates: list[dict], final_k: int,
                        cancellation=None, timeout_seconds: float = RERANK_TIMEOUT_SECONDS,
                        require_score: bool = False) -> dict:
    """Run a reranker and return validated items plus fallback diagnostics."""
    candidates = list(candidates or [])
    final_k = max(0, int(final_k))
    if not candidates or final_k == 0:
        return _fallback(candidates, final_k, "no_candidates")

    try:
        ranked = reranker.rerank(
            query,
            candidates,
            final_k,
            cancellation=cancellation,
            timeout_seconds=timeout_seconds,
        )
    except StreamCancelled:
        raise
    except Exception as exc:
        return _fallback(candidates, final_k, f"exception:{type(exc).__name__}")

    if not isinstance(ranked, list):
        return _fallback(candidates, final_k, "non_list_result")
    if not ranked:
        return _fallback(candidates, final_k, "empty_result")

    candidates_by_id = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if item_id is None:
            continue
        if not _hashable_id(item_id):
            return _fallback(candidates, final_k, "invalid_candidate_id")
        candidates_by_id[item_id] = item
    if not candidates_by_id:
        return _fallback(candidates, final_k, "no_valid_candidate_ids")

    expected_count = min(final_k, len(candidates_by_id))
    selected = []
    selected_ids = set()
    for item in ranked:
        if not isinstance(item, dict):
            return _fallback(candidates, final_k, "malformed_candidate")
        item_id = item.get("id")
        if not _hashable_id(item_id):
            return _fallback(candidates, final_k, "unknown_id")
        if item_id not in candidates_by_id:
            return _fallback(candidates, final_k, "unknown_id")
        if item_id in selected_ids:
            return _fallback(candidates, final_k, "duplicate_id")
        if "rerank_score" in item or require_score:
            if not _valid_score(item):
                return _fallback(candidates, final_k, "invalid_score")
        original = dict(candidates_by_id[item_id])
        if "rerank_score" in item:
            original["rerank_score"] = float(item["rerank_score"])
        selected.append(original)
        selected_ids.add(item_id)
        if len(selected) >= final_k:
            break

    if len(selected) < expected_count:
        return _fallback(candidates, final_k, "incomplete_result")

    reranked_count = len(selected)
    for item in candidates:
        if len(selected) >= final_k:
            break
        item_id = item.get("id") if isinstance(item, dict) else None
        if _hashable_id(item_id):
            if item_id in selected_ids:
                continue
            selected_ids.add(item_id)
        selected.append(item)

    return {
        "items": selected,
        "used_reranker": reranked_count > 0,
        "fallback_reason": None,
        "reranked_count": reranked_count,
        "filled_from_original": max(0, len(selected) - reranked_count),
    }


def safe_rerank(reranker, query: str, candidates: list[dict], final_k: int,
                cancellation=None, timeout_seconds: float = RERANK_TIMEOUT_SECONDS) -> list[dict]:
    """Run a reranker, validating output and falling back to original order."""
    return safe_rerank_outcome(
        reranker,
        query,
        candidates,
        final_k,
        cancellation=cancellation,
        timeout_seconds=timeout_seconds,
    )["items"]
