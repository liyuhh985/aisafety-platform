# -*- coding: utf-8 -*-
from eval.semantic_grounding.calibrate_thresholds import scan_thresholds

ROWS = [
    {"label": "entailed", "min_confidence": 0.91, "slot_class": "A",
     "runtime_label_a": "entailed"},
    {"label": "entailed", "min_confidence": 0.84, "slot_class": "A",
     "runtime_label_a": "entailed"},
    {"label": "neutral", "min_confidence": 0.90, "slot_class": "A",
     "runtime_label_a": "entailed"},
]


def test_scan_picks_lowest_threshold_meeting_precision():
    best = scan_thresholds(ROWS, "A", target_precision=0.98)
    assert best["threshold"] == 0.91


def test_scan_can_require_a_threshold_strictly_above_b():
    from eval.semantic_grounding.calibrate_thresholds import scan_thresholds

    best = scan_thresholds(ROWS, "A", target_precision=0.98, higher_than=0.70)
    assert best["threshold"] > 0.70
    assert best["threshold"] == 0.91


def test_calibration_forces_a_threshold_above_b(monkeypatch, tmp_path):
    from eval.semantic_grounding import calibrate_thresholds as cal

    seen = {}

    def fake_scan(rows, slot_class, target_precision, higher_than=0.0):
        if slot_class == "B":
            return {"threshold": 0.80, "precision": 1.0, "coverage": 1.0}
        seen["higher_than"] = higher_than
        return {"threshold": 0.90, "precision": 1.0, "coverage": 0.5}

    monkeypatch.setattr(cal, "calibration_rows", lambda _rows: ROWS)
    monkeypatch.setattr(cal, "assert_quality_gate", lambda _summary: None)
    monkeypatch.setattr(cal, "scan_thresholds", fake_scan)
    monkeypatch.setattr(
        cal, "scan_rejection_threshold",
        lambda rows, target_precision=0.95: {
            "threshold": 0.85, "precision": 1.0, "coverage": 1.0,
        },
    )
    thresholds = cal.calibrate_from_consensus(
        {"summary": {}, "consensus": []}, tmp_path
    )
    assert seen["higher_than"] == 0.80
    assert thresholds["threshold_a"] > thresholds["threshold_b"]


def test_threshold_scan_never_selects_below_grid_floor():
    from eval.semantic_grounding.calibrate_thresholds import scan_thresholds

    rows = [
        {"label": "entailed", "min_confidence": 0.60, "slot_class": "A",
         "runtime_label_a": "entailed"},
        {"label": "entailed", "min_confidence": 0.90, "slot_class": "A",
         "runtime_label_a": "entailed"},
    ]
    best = scan_thresholds(rows, "A", target_precision=0.98)
    assert best["threshold"] == 0.70
