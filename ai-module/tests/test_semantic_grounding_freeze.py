# -*- coding: utf-8 -*-
import pytest

from eval.semantic_grounding.freeze_test import freeze_manifest
from eval.semantic_grounding.report import render_report


def test_freeze_captures_hashes(tmp_path):
    dataset = tmp_path / "test.jsonl"
    dataset.write_text('{"id":"qv-001"}\n', encoding="utf-8")
    manifest = freeze_manifest(
        dataset_path=dataset,
        model_a="minimax-m3.1-flash",
        model_b="glm-5.3-flash",
        prompt="PROMPT",
        thresholds={
            "threshold_a": 0.91,
            "threshold_b": 0.84,
            "threshold_reject": 0.90,
        },
    )
    assert manifest["test_sha256"]
    assert manifest["prompt_sha256"]
    assert manifest["models"] == ["minimax-m3.1-flash", "glm-5.3-flash"]


def test_freeze_refuses_second_write(tmp_path):
    out = tmp_path / "frozen_test.json"
    out.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        freeze_manifest(
            dataset_path=tmp_path / "missing.jsonl",
            model_a="a",
            model_b="b",
            prompt="P",
            thresholds={},
            output_path=out,
        )


def test_report_labels_metrics_as_pseudo_label_agreement():
    text = render_report({
        "overall_agreement": 0.82,
        "cohen_kappa": 0.71,
        "thresholds": {"threshold_a": 0.91, "threshold_b": 0.84,
                       "threshold_reject": 0.90},
        "auto_accept": {"A": {"precision": 0.99, "coverage": 0.40},
                        "B": {"precision": 0.96, "coverage": 0.35}},
    })
    assert "dual-model consensus pseudo-labels" in text
    assert "No human gold labels were available" in text
    assert "not production accuracy" in text
