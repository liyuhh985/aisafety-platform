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


def test_base_content_hashes_are_unique_within_and_across_splits():
    summary = validate_dataset(
        DATASET_DIR / "qv-pseudo-v1.jsonl",
        DATASET_DIR / "boundary.jsonl",
    )
    assert summary["within_split_content_duplicates"] == []
    assert summary["cross_split_content_leakage"] == []


def test_boundary_rows_are_semantic_cases_not_relabelled_base_rows():
    from collections import Counter
    import re
    from eval.semantic_grounding.deterministic_prefilter import prefilter_sample
    from eval.semantic_grounding.protocol import load_jsonl

    rows = load_jsonl(DATASET_DIR / "boundary.jsonl")
    kinds = Counter(row["boundary_kind"] for row in rows)
    assert kinds == {
        "synonym": 5,
        "negation": 5,
        "number": 5,
        "multi_turn": 5,
        "vision": 5,
        "assistant_misuse": 5,
    }

    for row in rows:
        if row["boundary_kind"] == "negation":
            assert any(token in row["source_text"]
                       for token in ("没有", "并非", "未", "不是"))
            assert prefilter_sample(row)["decision"] == "contradicted"
        elif row["boundary_kind"] == "number":
            value_digits = re.findall(r"\d+", row["value"])
            assert value_digits
            assert any(digit not in row["source_text"] for digit in value_digits)
            assert prefilter_sample(row)["decision"] == "contradicted"
        elif row["boundary_kind"] == "multi_turn":
            assert len(row["turns"]) >= 2
        elif row["boundary_kind"] == "vision":
            assert row["source_kind"] == "vision"
            assert row["source_ref"].startswith("v")
        elif row["boundary_kind"] == "assistant_misuse":
            assert row["source_kind"] == "assistant"
            assert row["source_ref"].startswith("a")
        elif row["boundary_kind"] == "synonym":
            assert row["expected_label"] == "entailed"
            assert prefilter_sample(row)["decision"] == "needs_verifier"


def test_boundary_source_kinds_drive_actual_evidence_verification():
    from core.uncertainty import verify_slot_evidence
    from eval.semantic_grounding.protocol import load_jsonl

    rows = load_jsonl(DATASET_DIR / "boundary.jsonl")
    for row in rows:
        if row["boundary_kind"] not in {"vision", "assistant_misuse"}:
            continue
        result = verify_slot_evidence(
            row["slot"],
            row["value"],
            {"quote": row["quote"], "source_ref": row["source_ref"]},
            {row["source_ref"]: row["source_text"]},
            row["category"],
        )
        if row["boundary_kind"] == "vision":
            assert result["business_status"] in {"grounded", "unavailable"}
            assert result["reason"] != "assistant_source"
        else:
            assert result["reason"] == "assistant_source"
            assert result["business_status"] == "rejected"


def test_labeler_visible_fingerprints_are_unique_within_and_across_splits():
    summary = validate_dataset(
        DATASET_DIR / "qv-pseudo-v1.jsonl",
        DATASET_DIR / "boundary.jsonl",
    )
    assert summary["within_split_labeler_visible_duplicates"] == []
    assert summary["cross_split_labeler_visible_leakage"] == []
