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


def test_dev_has_grey_zone_samples_for_every_expected_label():
    from collections import Counter
    from eval.semantic_grounding.deterministic_prefilter import prefilter_sample
    from eval.semantic_grounding.protocol import load_jsonl

    rows = [
        row for row in load_jsonl(DATASET_DIR / "qv-pseudo-v1.jsonl")
        if row["split"] == "dev"
    ]
    for label in ("entailed", "neutral", "contradicted"):
        decisions = Counter(
            prefilter_sample(row)["decision"]
            for row in rows
            if row["expected_label"] == label
        )
        assert decisions["needs_verifier"] > 0, (label, decisions)


def test_dev_has_grey_entailed_examples_in_a_and_b_classes():
    from eval.semantic_grounding.deterministic_prefilter import prefilter_sample
    from eval.semantic_grounding.protocol import load_jsonl

    rows = [
        row for row in load_jsonl(DATASET_DIR / "qv-pseudo-v1.jsonl")
        if row["split"] == "dev"
        and row["expected_label"] == "entailed"
        and prefilter_sample(row)["decision"] == "needs_verifier"
    ]
    classes = {row["slot_class"] for row in rows}
    assert {"A", "B"} <= classes
