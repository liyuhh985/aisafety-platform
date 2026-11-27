"""分类评测纯函数单测：不联网、不读库、不调模型。

只测 eval_classify 里的指标/解析函数，以及查询集本身的自洽性。
"""
from collections import Counter

import pytest

from eval.eval_classify import (
    confusion_pairs,
    is_intercepted,
    major_hit,
    mean_range,
    predicted_pair,
    round_accuracy,
    subcategory_hit,
    top_confusions,
)
from eval.eval_queries import NEGATIVE_SET, QUERY_SET
from core.hazard_taxonomy import HAZARD_TAXONOMY


# ---------- 查询集自洽性 ----------
def test_query_set_is_29_subcategories_times_two_styles():
    assert len(QUERY_SET) == 58
    pairs = {(q["major"], q["subcategory"]) for q in QUERY_SET}
    assert len(pairs) == 29
    per_pair = Counter((q["major"], q["subcategory"]) for q in QUERY_SET)
    assert all(count == 2 for count in per_pair.values())
    styles = Counter(q["style"] for q in QUERY_SET)
    assert styles == {"explicit": 29, "colloquial": 29}
    retired = {"wall_crack_lean", "facade_fall", "fire_water_abnormal"}
    assert retired.isdisjoint({q["subcategory"] for q in QUERY_SET})


def test_query_set_covers_every_taxonomy_subcategory():
    covered = {(q["major"], q["subcategory"]) for q in QUERY_SET}
    taxonomy = {
        (item["code"], sub_code)
        for item in HAZARD_TAXONOMY
        for sub_code, _ in item["subcategories"]
    }
    assert covered == taxonomy
    assert len(taxonomy) == 29


def test_negative_set_has_ten_unrelated_queries():
    assert len(NEGATIVE_SET) == 10
    assert all(q["query"].strip() for q in NEGATIVE_SET)


# ---------- predicted_pair ----------
def test_predicted_pair_reads_locked_fields():
    assert predicted_pair({"locked_major": "fire", "locked_subcategory": "fire_lane_blocked"}) == (
        "fire", "fire_lane_blocked")


def test_predicted_pair_falls_back_to_suggested_major():
    out = {"locked_major": "", "suggested_major_code": "municipal"}
    assert predicted_pair(out) == ("municipal", "")


def test_predicted_pair_handles_empty_and_none():
    assert predicted_pair({}) == ("", "")
    assert predicted_pair(None) == ("", "")


# ---------- 命中判定 ----------
def test_subcategory_hit_requires_exact_pair():
    assert subcategory_hit("fire", "fire_lane_blocked", "fire", "fire_lane_blocked") is True
    assert subcategory_hit("fire", "fire_lane_blocked", "fire", "fire_equipment_fault") is False
    assert subcategory_hit("fire", "fire_lane_blocked", "municipal", "manhole_damage") is False


def test_subcategory_hit_false_when_prediction_empty():
    assert subcategory_hit("fire", "fire_lane_blocked", "fire", "") is False
    assert subcategory_hit("fire", "fire_lane_blocked", "", "") is False


def test_major_hit_is_looser_than_subcategory_hit():
    assert major_hit("fire", "fire") is True
    assert major_hit("fire", "municipal") is False
    assert major_hit("fire", "") is False


# ---------- 范围拦截 ----------
def test_is_intercepted_only_for_guard_scopes():
    assert is_intercepted({"scope": "out_of_scope"}) is True
    assert is_intercepted({"scope": "ambiguous"}) is True
    assert is_intercepted({"scope": "hazard"}) is False
    assert is_intercepted({"scope": "emergency"}) is False
    assert is_intercepted({}) is False
    assert is_intercepted(None) is False


# ---------- 混淆对 ----------
def test_confusion_pairs_counts_direction():
    wrong = [("fire_equipment_fault", "fire_lane_blocked"),
             ("fire_equipment_fault", "fire_lane_blocked"),
             ("manhole_damage", "drainage_flood")]
    counts = confusion_pairs(wrong)
    assert counts[("fire_equipment_fault", "fire_lane_blocked")] == 2
    assert counts[("manhole_damage", "drainage_flood")] == 1


def test_confusion_pairs_marks_empty_prediction():
    counts = confusion_pairs([("manhole_damage", "")])
    assert counts[("manhole_damage", "<空>")] == 1


def test_top_confusions_sorted_and_capped():
    wrong = [("a", "b")] * 3 + [("c", "d")] * 2 + [("e", "f")]
    top = top_confusions(wrong, top_n=2)
    assert top == [(("a", "b"), 3), (("c", "d"), 2)]


def test_top_confusions_ties_break_by_name_for_stability():
    wrong = [("z", "y"), ("a", "b")]
    assert top_confusions(wrong, top_n=2) == [(("a", "b"), 1), (("z", "y"), 1)]


def test_top_confusions_empty():
    assert top_confusions([], 10) == []


# ---------- 采样聚合 ----------
def test_round_accuracy_per_round():
    flags = [[True, True], [True, False], [False, False]]
    assert round_accuracy(flags, 3) == pytest.approx([1.0, 0.5, 0.0])


def test_round_accuracy_pads_missing_rounds_as_zero():
    assert round_accuracy([[True]], 3) == pytest.approx([1.0, 0.0, 0.0])


def test_mean_range_reports_mean_and_spread():
    assert mean_range([1.0, 0.5, 0.0]) == pytest.approx((0.5, 1.0))


def test_mean_range_empty_is_zero():
    assert mean_range([]) == pytest.approx((0.0, 0.0))
