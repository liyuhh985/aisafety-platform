import pytest

from core.cancellation import StreamCancelled
from core.reranker import NoopReranker, safe_rerank, safe_rerank_outcome


class StubReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [candidates[1], candidates[0]][:final_k]


class BadIdReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [{"id": 999, "title": "unknown"}]


class DuplicateReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [candidates[0], candidates[0]]


class EmptyReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return []


class ErrorReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        raise RuntimeError("reranker unavailable")


class MixedMalformedReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [candidates[0], "not-a-candidate"]


class TamperedReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [{"id": 2, "title": "tampered", "rerank_score": 0.9}]


class NonFiniteScoreReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [{"id": 2, "title": "two", "rerank_score": float("nan")}]


class CancelledReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        raise StreamCancelled()


def candidates():
    return [
        {"id": 1, "title": "one"},
        {"id": 2, "title": "two"},
        {"id": 3, "title": "three"},
    ]


def test_noop_reranker_returns_first_final_k():
    result = NoopReranker().rerank("q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_accepts_valid_reordering():
    result = safe_rerank(StubReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [2, 1]


def test_safe_rerank_falls_back_on_unknown_id():
    result = safe_rerank(BadIdReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_falls_back_on_duplicate_id():
    result = safe_rerank(DuplicateReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_fills_remaining_slots_from_original_order():
    result = safe_rerank(NoopReranker(), "q", candidates(), 3)
    assert [item["id"] for item in result] == [1, 2, 3]


def test_safe_rerank_falls_back_on_empty_result():
    result = safe_rerank(EmptyReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_falls_back_on_exception():
    result = safe_rerank(ErrorReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_falls_back_on_mixed_non_dict_result():
    result = safe_rerank(MixedMalformedReranker(), "q", candidates(), 2)
    assert [item["id"] for item in result] == [1, 2]


def test_safe_rerank_propagates_cancellation():
    with pytest.raises(StreamCancelled):
        safe_rerank(CancelledReranker(), "q", candidates(), 2)

def test_safe_rerank_outcome_reports_valid_rerank():
    outcome = safe_rerank_outcome(StubReranker(), "q", candidates(), 2)
    assert [item["id"] for item in outcome["items"]] == [2, 1]
    assert outcome["used_reranker"] is True
    assert outcome["fallback_reason"] is None


def test_safe_rerank_outcome_reports_fallback_reason():
    outcome = safe_rerank_outcome(ErrorReranker(), "q", candidates(), 2)
    assert [item["id"] for item in outcome["items"]] == [1, 2]
    assert outcome["used_reranker"] is False
    assert "RuntimeError" in outcome["fallback_reason"]


def test_safe_rerank_reconstructs_candidate_fields_from_original():
    result = safe_rerank(TamperedReranker(), "q", candidates(), 1)
    assert result[0]["id"] == 2
    assert result[0]["title"] == "two"
    assert result[0]["rerank_score"] == 0.9


def test_safe_rerank_rejects_non_finite_score():
    outcome = safe_rerank_outcome(NonFiniteScoreReranker(), "q", candidates(), 2)
    assert [item["id"] for item in outcome["items"]] == [1, 2]
    assert outcome["used_reranker"] is False

class PartialReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [{"id": candidates[0]["id"], "rerank_score": 0.9}]


class UnhashableCandidateIdReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [{"id": candidates[1]["id"], "rerank_score": 0.9}]


class UnhashableResultIdReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        return [{"id": ["not-hashable"], "rerank_score": 0.9}]


def test_safe_rerank_treats_incomplete_result_as_fallback():
    outcome = safe_rerank_outcome(PartialReranker(), "q", candidates(), 2)

    assert [item["id"] for item in outcome["items"]] == [1, 2]
    assert outcome["used_reranker"] is False
    assert outcome["fallback_reason"] == "incomplete_result"
    assert outcome["reranked_count"] == 0


def test_safe_rerank_falls_back_for_unhashable_candidate_id():
    candidate_list = [
        {"id": ["not-hashable"], "title": "bad"},
        {"id": 2, "title": "two"},
    ]

    outcome = safe_rerank_outcome(
        UnhashableCandidateIdReranker(), "q", candidate_list, 1
    )

    assert [item["title"] for item in outcome["items"]] == ["bad"]
    assert outcome["used_reranker"] is False
    assert outcome["fallback_reason"] == "invalid_candidate_id"


def test_safe_rerank_falls_back_for_unhashable_ranked_id():
    outcome = safe_rerank_outcome(
        UnhashableResultIdReranker(), "q", candidates(), 2
    )

    assert [item["id"] for item in outcome["items"]] == [1, 2]
    assert outcome["used_reranker"] is False
    assert outcome["fallback_reason"] == "unknown_id"
