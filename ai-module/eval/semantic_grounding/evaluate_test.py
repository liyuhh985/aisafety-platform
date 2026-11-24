# -*- coding: utf-8 -*-
"""Evaluate a frozen semantic-grounding test set exactly once per output."""

import json
from pathlib import Path

from eval.semantic_grounding.calibrate_thresholds import calibration_rows
from eval.semantic_grounding.consensus import build_consensus
from eval.semantic_grounding.freeze_test import load_frozen_manifest
from eval.semantic_grounding.labeler_config import build_labeler
from eval.semantic_grounding.protocol import sha256_file, sha256_text
from eval.semantic_grounding.report import render_report
from eval.semantic_grounding.run_labelers import run_labeling


def _accept_metrics(rows, thresholds) -> dict:
    threshold_a = float(thresholds.get("threshold_a") or 1.01)
    threshold_b = float(thresholds.get("threshold_b") or 1.01)
    class_rows = []
    for slot_class, threshold in (("A", threshold_a), ("B", threshold_b)):
        relevant = [row for row in rows if row.get("slot_class") == slot_class]
        if slot_class == "A":
            accepted = [
                row for row in relevant
                if row.get("runtime_label_a") == "entailed"
                and row.get("runtime_label_b") == "entailed"
                and float(row.get("min_confidence") or 0.0) >= threshold
            ]
        else:
            accepted = [
                row for row in relevant
                if row.get("runtime_label_a") == "entailed"
                and float(row.get("confidence_a") or 0.0) >= threshold
            ]
        correct = [row for row in accepted if row.get("label") == "entailed"]
        entailed_total = sum(row.get("label") == "entailed" for row in relevant)
        class_rows.append({
            "slot_class": slot_class,
            "threshold": threshold,
            "precision": len(correct) / len(accepted) if accepted else 0.0,
            "coverage": len(correct) / entailed_total if entailed_total else 0.0,
            "accepted": len(accepted),
        })
    return {row["slot_class"]: row for row in class_rows}


def evaluate_frozen_test(*, dataset_path, frozen_path, prompt,
                         labeler_a=None, labeler_b=None, output_dir=None):
    output = Path(output_dir or Path(dataset_path).parent / "test_eval")
    metrics_path = output / "test_metrics.json"
    if metrics_path.exists():
        raise FileExistsError(str(metrics_path))
    manifest = load_frozen_manifest(frozen_path)
    if sha256_file(dataset_path) != manifest.get("test_sha256"):
        raise ValueError("test dataset hash does not match frozen manifest")
    if sha256_text(prompt) != manifest.get("prompt_sha256"):
        raise ValueError("prompt hash does not match frozen manifest")

    labeler_a = labeler_a or build_labeler("A")
    labeler_b = labeler_b or build_labeler("B")
    seeds = run_labeling(
        dataset_path, output, split="test",
        labeler_a=labeler_a, labeler_b=labeler_b,
    )
    from eval.semantic_grounding.protocol import load_jsonl
    deterministic = load_jsonl(output / "deterministic.jsonl")
    labels_a = load_jsonl(output / "labels_A.jsonl")
    labels_b = load_jsonl(output / "labels_B.jsonl")
    consensus = build_consensus(deterministic, labels_a, labels_b)
    rows = consensus["consensus"]
    # Attach labeler-A confidence for the B-class single-model calibration proxy.
    map_a = {row.get("id"): row for row in labels_a}
    calibration_input = []
    for row in rows:
        if row.get("status") != "agreed":
            continue
        calibration_input.append({
            **row,
            "confidence_a": float((map_a.get(row.get("id")) or {}).get("confidence") or
                                  row.get("confidence_a") or 0.0),
        })
    calibration = calibration_rows(calibration_input)
    thresholds = dict(manifest.get("thresholds") or {})
    metrics = {
        "overall_agreement": consensus["summary"]["overall_agreement"],
        "cohen_kappa": consensus["summary"]["cohen_kappa"],
        "invalid_count": consensus["summary"]["invalid_count"],
        "thresholds": thresholds,
        "auto_accept": _accept_metrics(calibration, thresholds),
        "dataset": manifest.get("dataset"),
        "models": manifest.get("models"),
        "test_sha256": manifest.get("test_sha256"),
        "prompt_sha256": manifest.get("prompt_sha256"),
        "candidate_count": seeds["candidates"],
    }
    output.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("x", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    (output / "REPORT.md").write_text(render_report(metrics), encoding="utf-8")
    return metrics
