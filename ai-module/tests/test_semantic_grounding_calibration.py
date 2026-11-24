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
