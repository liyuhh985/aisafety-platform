# -*- coding: utf-8 -*-
"""Dev-only precision-first threshold calibration."""

import json
from pathlib import Path

from eval.semantic_grounding.consensus import assert_quality_gate
from eval.semantic_grounding.protocol import (
    BASE_DATASET,
    PRECISION_TARGETS,
    THRESHOLDS,
)


def _rows_for_class(rows, slot_class):
    return [
        row for row in (rows or [])
        if not slot_class or str(row.get("slot_class") or "") == slot_class
    ]


def _scan_results(rows, target_precision):
    rows = list(rows or [])
    entailed_total = sum(row.get("label") == "entailed" for row in rows)
    non_entailed_total = sum(row.get("label") != "entailed" for row in rows)
    observed = sorted({
        float(row.get("min_confidence"))
        for row in rows
        if isinstance(row.get("min_confidence"), (int, float))
        and not isinstance(row.get("min_confidence"), bool)
        and 0.0 <= float(row.get("min_confidence")) <= 1.0
    })
    candidates = sorted(set(THRESHOLDS) | set(observed))
    results = []
    for threshold in candidates:
        auto_accept = [
            row for row in rows
            if row.get("runtime_label_a") == "entailed"
            and float(row.get("min_confidence") or 0.0) >= threshold
        ]
        correct = [row for row in auto_accept if row.get("label") == "entailed"]
        precision = len(correct) / len(auto_accept) if auto_accept else 0.0
        coverage = len(correct) / entailed_total if entailed_total else 0.0
        false_accept_proxy = (
            sum(row.get("label") != "entailed" for row in auto_accept)
            / non_entailed_total
            if non_entailed_total else 0.0
        )
        results.append({
            "threshold": threshold,
            "precision": precision,
            "coverage": coverage,
            "false_accept_proxy": false_accept_proxy,
            "accepted": len(auto_accept),
        })
    return results


def scan_thresholds(rows, slot_class, target_precision) -> dict:
    filtered = _rows_for_class(rows, slot_class)
    results = _scan_results(filtered, target_precision)
    eligible = [
        result for result in results
        if result["precision"] >= target_precision and result["coverage"] > 0
    ]
    if not eligible:
        raise ValueError(
            "no threshold meets precision target with non-zero coverage"
        )
    best = min(eligible, key=lambda item: item["threshold"])
    return {**best, "scan": results, "target_precision": target_precision}


def scan_rejection_threshold(rows, target_precision=0.95) -> dict:
    rows = list(rows or [])
    contradicted_total = sum(row.get("label") == "contradicted" for row in rows)
    non_contradicted_total = len(rows) - contradicted_total
    observed = sorted({
        float(row.get("min_confidence"))
        for row in rows
        if isinstance(row.get("min_confidence"), (int, float))
        and not isinstance(row.get("min_confidence"), bool)
        and 0.0 <= float(row.get("min_confidence")) <= 1.0
    })
    candidates = sorted(set(THRESHOLDS) | set(observed))
    results = []
    for threshold in candidates:
        auto_reject = [
            row for row in rows
            if row.get("runtime_label_a") == "contradicted"
            and row.get("runtime_label_b") == "contradicted"
            and float(row.get("min_confidence") or 0.0) >= threshold
        ]
        correct = [row for row in auto_reject if row.get("label") == "contradicted"]
        precision = len(correct) / len(auto_reject) if auto_reject else 0.0
        coverage = len(correct) / contradicted_total if contradicted_total else 0.0
        false_reject_proxy = (
            sum(row.get("label") != "contradicted" for row in auto_reject)
            / non_contradicted_total
            if non_contradicted_total else 0.0
        )
        results.append({
            "threshold": threshold,
            "precision": precision,
            "coverage": coverage,
            "false_reject_proxy": false_reject_proxy,
            "accepted": len(auto_reject),
        })
    eligible = [
        result for result in results
        if result["precision"] >= target_precision and result["coverage"] > 0
    ]
    if not eligible:
        raise ValueError("no rejection threshold meets precision target")
    best = min(eligible, key=lambda item: item["threshold"])
    return {**best, "scan": results, "target_precision": target_precision}


def calibration_rows(consensus_rows) -> list[dict]:
    rows = []
    for row in consensus_rows or []:
        if row.get("status") != "agreed":
            continue
        if row.get("label") not in {"entailed", "neutral", "contradicted"}:
            continue
        rows.append({
            "id": row.get("id", ""),
            "slot_class": row.get("slot_class", ""),
            "label": row["label"],
            "runtime_label_a": row.get("label_a", ""),
            "runtime_label_b": row.get("label_b", ""),
            "confidence_a": float(row.get("confidence_a") or 0.0),
            "min_confidence": min(
                float(row.get("confidence_a") or 0.0),
                float(row.get("confidence_b") or 0.0),
            ),
        })
    return rows


ICD_CALIBRATION_NOTICE = (
    "Thresholds were calibrated against dual-model consensus pseudo-labels.\n"
    "No human review was performed."
)


def calibrate_from_consensus(consensus_result, output_dir) -> dict:
    assert_quality_gate((consensus_result or {}).get("summary") or {})
    rows = calibration_rows((consensus_result or {}).get("consensus") or [])
    scan_a = scan_thresholds(rows, "A", PRECISION_TARGETS["A"])
    scan_b = scan_thresholds(rows, "B", PRECISION_TARGETS["B"])
    scan_c = scan_rejection_threshold(rows, PRECISION_TARGETS["C"])
    thresholds = {
        "threshold_a": scan_a["threshold"],
        "threshold_b": scan_b["threshold"],
        "threshold_c": scan_c["threshold"],
        "dataset": BASE_DATASET,
        "notice": ICD_CALIBRATION_NOTICE,
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("threshold_scan_a.json", scan_a),
        ("threshold_scan_b.json", scan_b),
        ("threshold_scan_c.json", scan_c),
        ("thresholds.json", thresholds),
    ):
        (output / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return thresholds
