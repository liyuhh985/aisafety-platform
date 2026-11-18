from __future__ import annotations

import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import generate_error_analysis as gea
import generate_report as gr


def test_classify_errors_buckets_false_positive_and_major_confusion():
    frozen = {"items": [
        {"sha256": "a", "file": "a.jpg", "has_hazard": False, "major_category": "", "subcategory": ""},
        {"sha256": "b", "file": "b.jpg", "has_hazard": True, "major_category": "traffic", "subcategory": "road_occupancy"},
    ]}
    predictions = [
        {"sha256": "a", "parsed": {"has_hazard": True, "confidence": "高", "major_category": "municipal", "subcategory": "manhole_damage"}},
        {"sha256": "b", "parsed": {"has_hazard": True, "confidence": "高", "major_category": "municipal", "subcategory": "manhole_damage"}},
    ]
    errors = gea.classify_errors(frozen, predictions)
    assert errors["false_positive"]["count"] == 1
    assert errors["major_confusion"]["count"] == 1


def test_report_marks_model_consensus_as_not_human_gold():
    baseline = {
        "binary": {"recall": 0.95, "fpr": 0.30, "precision": 0.76, "f1": 0.844, "accuracy": 0.825},
        "major": {"macro_recall": 0.825},
        "review_aware": {"review_rate": 0.275, "auto_recall": 0.625, "auto_fpr": 0.075, "critical_miss_rate": 0.05},
    }
    final = dict(baseline)
    report = gr.generate_report(baseline, final, {"winner": "baseline", "delta": {}}, "# errors")
    assert "model_consensus" in report
    assert "不是人工 gold" in report
