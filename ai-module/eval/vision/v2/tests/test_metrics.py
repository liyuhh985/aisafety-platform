from __future__ import annotations

import sys
from pathlib import Path

import pytest

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import contract as c
import score_v2 as sv

TAXONOMY_PATH = V2_DIR.parent / "_taxonomy_final.json"
SUB_BY_MAJOR = {
    "traffic": "road_occupancy",
    "municipal": "manhole_damage",
    "fire": "fire_lane_blocked",
    "building": "structural_damage",
    "utility": "wire_fault",
    "construction": "deep_pit",
    "elevator_special": "elevator_stopped",
    "environment_other": "garbage_pile",
}


def test_binary_precision_recall_and_fpr():
    metrics = sv.binary_metrics([1, 1, 0, 0], [1, 0, 1, 0])
    assert metrics["tp"] == 1
    assert metrics["fn"] == 1
    assert metrics["fp"] == 1
    assert metrics["tn"] == 1
    assert metrics["recall"] == pytest.approx(0.5)
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["fpr"] == pytest.approx(0.5)
    assert metrics["f1"] == pytest.approx(0.5)
    assert metrics["accuracy"] == pytest.approx(0.5)


def test_wilson_interval_contains_observed_rate():
    p, lo, hi = sv.wilson_interval(5, 10)
    assert p == pytest.approx(0.5)
    assert 0.0 <= lo < p < hi <= 1.0


def test_review_aware_routes_low_confidence_to_review():
    items = [
        {"has_hazard": True, "major_category": "traffic", "subcategory": "road_occupancy"},
        {"has_hazard": True, "major_category": "traffic", "subcategory": "road_occupancy"},
        {"has_hazard": False, "major_category": "", "subcategory": ""},
        {"has_hazard": False, "major_category": "", "subcategory": ""},
    ]
    preds = [
        {"has_hazard": True, "confidence": "高", "major_category": "traffic", "subcategory": "road_occupancy"},
        {"has_hazard": False, "confidence": "低", "major_category": "", "subcategory": ""},
        {"has_hazard": True, "confidence": "高", "major_category": "traffic", "subcategory": "road_occupancy"},
        {"has_hazard": False, "confidence": "高", "major_category": "", "subcategory": ""},
    ]

    metrics = sv.evaluate_items(items, preds, TAXONOMY_PATH)

    assert metrics["binary"]["tp"] == 1
    assert metrics["binary"]["tn"] == 1
    assert metrics["binary"]["fp"] == 1
    assert metrics["binary"]["fn"] == 1
    assert metrics["review_aware"]["review_rate"] == pytest.approx(0.25)
    assert metrics["review_aware"]["auto_recall"] == pytest.approx(0.5)
    assert metrics["review_aware"]["critical_miss_rate"] == pytest.approx(0.0)
    assert metrics["review_aware"]["auto_fpr"] == pytest.approx(0.5)
    assert metrics["review_aware"]["auto_coverage"] == pytest.approx(0.75)


def test_invalid_prediction_is_counted_not_dropped():
    metrics = sv.evaluate_items(
        [{"has_hazard": True, "major_category": "traffic", "subcategory": "road_occupancy"}],
        [{"error": "parse_failed", "parsed": None}],
        TAXONOMY_PATH,
    )

    assert metrics["invalid"]["parse_failed"] == 1
    assert metrics["binary"]["fn"] == 1
    assert metrics["review_aware"]["review_rate"] == pytest.approx(1.0)
    assert metrics["review_aware"]["critical_miss_rate"] == pytest.approx(0.0)


def test_major_macro_recall_and_confusion():
    items = []
    preds = []
    for index, major in enumerate(c.MAJOR_CODES):
        sub = SUB_BY_MAJOR[major]
        items.append({"has_hazard": True, "major_category": major, "subcategory": sub})
        preds.append({
            "has_hazard": True,
            "confidence": "高",
            "major_category": major if index < 6 else "municipal",
            "subcategory": sub if index < 6 else "manhole_damage",
        })

    metrics = sv.evaluate_items(items, preds, TAXONOMY_PATH)

    assert metrics["major"]["macro_recall"] == pytest.approx(6 / 8)
    assert metrics["major"]["by_major"]["traffic"]["correct"] == 1
    assert metrics["major"]["by_major"]["elevator_special"]["correct"] == 0
    assert metrics["major"]["confusion"]["elevator_special -> municipal"] == 1
