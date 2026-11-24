# -*- coding: utf-8 -*-
from pathlib import Path

from eval.semantic_grounding.validate_dataset import validate_dataset

DATASET_DIR = Path(__file__).parents[1] / "eval/semantic_grounding/dataset"


def test_base_dataset_quotas_and_no_group_leakage():
    summary = validate_dataset(
        DATASET_DIR / "qv-pseudo-v1.jsonl",
        DATASET_DIR / "boundary.jsonl",
    )
    assert summary["base_total"] == 150
    assert summary["base_labels"] == {
        "entailed": 50,
        "neutral": 50,
        "contradicted": 50,
    }
    assert summary["dev_total"] == 90
    assert summary["test_total"] == 60
    assert summary["group_leakage"] == []
    assert 20 <= summary["boundary_total"] <= 30
