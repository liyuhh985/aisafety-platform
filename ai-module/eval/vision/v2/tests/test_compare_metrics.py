from __future__ import annotations

import sys
from pathlib import Path

import pytest

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import compare_metrics as cm


def test_compare_metrics_reports_signed_deltas():
    baseline = {
        "binary": {"recall": 0.8, "fpr": 0.4, "precision": 0.6, "f1": 0.68, "accuracy": 0.7},
        "review_aware": {
            "review_rate": 0.0,
            "auto_recall": 0.8,
            "auto_fpr": 0.4,
            "critical_miss_rate": 0.2,
        },
        "major": {"macro_recall": 0.7},
    }
    final = {
        "binary": {"recall": 0.75, "fpr": 0.2, "precision": 0.75, "f1": 0.75, "accuracy": 0.775},
        "review_aware": {
            "review_rate": 0.1,
            "auto_recall": 0.7,
            "auto_fpr": 0.15,
            "critical_miss_rate": 0.2,
        },
        "major": {"macro_recall": 0.72},
    }

    result = cm.compare_metrics(baseline, final)

    assert result["delta"]["fpr"] == pytest.approx(-0.2)
    assert result["delta"]["precision"] == pytest.approx(0.15)
    assert result["delta"]["review_rate"] == pytest.approx(0.1)
    assert result["delta"]["macro_recall"] == pytest.approx(0.02)


def test_compare_metrics_marks_final_when_fpr_drops_without_more_critical_misses():
    baseline = {
        "binary": {"accuracy": 0.7},
        "review_aware": {"auto_fpr": 0.4, "critical_miss_rate": 0.2},
        "major": {"macro_recall": 0.7},
    }
    final = {
        "binary": {"accuracy": 0.8},
        "review_aware": {"auto_fpr": 0.2, "critical_miss_rate": 0.2},
        "major": {"macro_recall": 0.72},
    }

    assert cm.compare_metrics(baseline, final)["winner"] == "final"
