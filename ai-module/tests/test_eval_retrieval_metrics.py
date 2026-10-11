"""评测指标纯函数单测：不联网、不读库。"""
import pytest

from eval.eval_metrics import (
    first_relevant_rank,
    hit_at_k,
    major_hit_at_k,
    mean,
    mrr,
    precision_at_k,
    recall_at_k,
    spread,
)


def test_hit_at_k_true_when_gold_in_window():
    assert hit_at_k([9, 3, 7], {7, 8}, k=5) is True


def test_hit_at_k_false_when_gold_absent():
    assert hit_at_k([9, 3, 7], {100}, k=5) is False


def test_hit_at_k_respects_cutoff():
    assert hit_at_k([9, 3, 7], {7}, k=2) is False
    assert hit_at_k([9, 3, 7], {7}, k=3) is True


def test_hit_at_k_false_for_empty_gold():
    assert hit_at_k([1, 2], set(), k=5) is False


def test_hit_at_k_false_for_zero_k():
    assert hit_at_k([1, 2], {1}, k=0) is False


def test_first_relevant_rank_uses_one_based_ranking():
    assert first_relevant_rank([5, 6, 7], {6, 7}) == 2
    assert first_relevant_rank([5, 6], {99}) is None


def test_mrr_is_reciprocal_of_first_rank():
    assert mrr([5, 6, 7], {5}) == 1.0
    assert mrr([5, 6, 7], {6}) == pytest.approx(0.5)
    assert mrr([5, 6, 7], {99}) == 0.0


def test_precision_denominator_is_k_not_result_count():
    # 只返回 2 条且都相关，P@5 仍是 2/5，不是 1.0
    assert precision_at_k([1, 2], {1, 2}, k=5) == pytest.approx(0.4)


def test_precision_counts_only_gold():
    assert precision_at_k([1, 9, 2, 8, 3], {1, 2, 3}, k=5) == pytest.approx(0.6)


def test_recall_reports_ceiling():
    value, ceiling = recall_at_k([1, 2, 3, 4, 5], set(range(1, 16)), k=3)
    assert value == pytest.approx(3 / 15)
    assert ceiling == pytest.approx(3 / 15)


def test_recall_ceiling_caps_at_gold_size():
    value, ceiling = recall_at_k([1, 2, 3], {1, 2}, k=5)
    assert value == pytest.approx(1.0)
    assert ceiling == pytest.approx(1.0)


def test_recall_empty_gold_is_zero():
    assert recall_at_k([1], set(), k=5) == (0.0, 0.0)


def test_major_hit_is_looser_than_subcategory_hit():
    assert major_hit_at_k(["fire", "municipal"], "fire", k=5) is True
    assert major_hit_at_k(["municipal"], "fire", k=5) is False


def test_mean_and_spread():
    assert mean([1.0, 0.5, 0.0]) == pytest.approx(0.5)
    assert spread([1.0, 1.0, 0.0]) == pytest.approx(1.0)
    assert mean([]) == 0.0
    assert spread([]) == 0.0
