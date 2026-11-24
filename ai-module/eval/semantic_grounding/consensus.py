# -*- coding: utf-8 -*-
"""Dual-model consensus, exact agreement, and Cohen's kappa."""

import json
from pathlib import Path

from eval.semantic_grounding.protocol import (
    COHEN_KAPPA_GATE,
    LABELS,
    OVERALL_AGREEMENT_GATE,
    dump_jsonl,
)

LABEL_SET = set(LABELS)


def merge_pair(a, b) -> dict:
    if a in LABEL_SET and b in LABEL_SET and a == b:
        return {"label": a, "status": "agreed"}
    return {"label": "ambiguous", "status": "disagreed"}


def cohen_kappa(labels_a, labels_b) -> float:
    left = list(labels_a or [])
    right = list(labels_b or [])
    if len(left) != len(right) or not left:
        return 0.0
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    expected = 0.0
    for label in LABELS:
        pa = sum(value == label for value in left) / len(left)
        pb = sum(value == label for value in right) / len(right)
        expected += pa * pb
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def _label_map(value) -> dict:
    if isinstance(value, dict):
        return value
    rows = []
    if isinstance(value, (str, Path)):
        from eval.semantic_grounding.protocol import load_jsonl
        rows = load_jsonl(value)
    else:
        rows = list(value or [])
    return {str(row.get("id") or ""): row for row in rows}


def _valid_result(result) -> bool:
    return (isinstance(result, dict)
            and result.get("label") in LABEL_SET
            and isinstance(result.get("confidence"), (int, float))
            and not isinstance(result.get("confidence"), bool)
            and 0.0 <= float(result["confidence"]) <= 1.0)


def build_consensus(deterministic_rows, labels_a, labels_b) -> dict:
    deterministic = _label_map(deterministic_rows)
    map_a = _label_map(labels_a)
    map_b = _label_map(labels_b)
    agreement_rows = []
    disagreement_rows = []
    consensus_rows = []
    invalid_count = 0

    for identifier, decision in deterministic.items():
        decision_name = str((decision or {}).get("decision") or "")
        if decision_name not in {"needs_verifier", "grounded", "contradicted"}:
            invalid_count += 1
            continue
        if decision_name == "grounded":
            consensus_rows.append({"id": identifier, "label": "entailed",
                                   "status": "deterministic"})
            continue
        if decision_name == "contradicted":
            consensus_rows.append({"id": identifier, "label": "contradicted",
                                   "status": "deterministic"})
            continue

        a = map_a.get(identifier) or {}
        b = map_b.get(identifier) or {}
        if not _valid_result(a) or not _valid_result(b):
            invalid_count += 1
            continue
        merged = merge_pair(a["label"], b["label"])
        row = {
            "id": identifier,
            "slot_class": (decision or {}).get("slot_class", ""),
            "label_a": a["label"],
            "confidence_a": float(a["confidence"]),
            "label_b": b["label"],
            "confidence_b": float(b["confidence"]),
            **merged,
        }
        consensus_rows.append(row)
        if merged["status"] == "agreed":
            agreement_rows.append(row)
        else:
            disagreement_rows.append(row)

    total_pairs = len(agreement_rows) + len(disagreement_rows)
    overall_agreement = (
        len(agreement_rows) / total_pairs if total_pairs else 0.0
    )
    labels_a = [row["label_a"] for row in agreement_rows + disagreement_rows]
    labels_b = [row["label_b"] for row in agreement_rows + disagreement_rows]
    kappa = cohen_kappa(labels_a, labels_b)

    label_agreement = {}
    for label in LABELS:
        relevant = [row for row in agreement_rows + disagreement_rows
                    if row["label_a"] == label or row["label_b"] == label]
        if relevant:
            label_agreement[label] = sum(
                row["label_a"] == row["label_b"] == label for row in relevant
            ) / len(relevant)
    class_agreement = {}
    for slot_class in ("A", "B"):
        relevant = [row for row in agreement_rows + disagreement_rows
                    if row["slot_class"] == slot_class]
        if relevant:
            class_agreement[slot_class] = sum(
                row["status"] == "agreed" for row in relevant
            ) / len(relevant)

    summary = {
        "overall_agreement": overall_agreement,
        "cohen_kappa": kappa,
        "label_agreement": label_agreement,
        "class_agreement": class_agreement,
        "agreed_count": len(agreement_rows),
        "disagreed_count": len(disagreement_rows),
        "invalid_count": invalid_count,
    }
    return {
        "summary": summary,
        "consensus": consensus_rows,
        "disagreements": disagreement_rows,
    }


def assert_quality_gate(summary) -> None:
    if float((summary or {}).get("overall_agreement") or 0.0) < OVERALL_AGREEMENT_GATE:
        raise ValueError("overall_agreement below 0.75")
    if float((summary or {}).get("cohen_kappa") or 0.0) < COHEN_KAPPA_GATE:
        raise ValueError("cohen_kappa below 0.60")


def write_consensus_artifacts(result, output_dir) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    dump_jsonl(output / "consensus.jsonl", result["consensus"])
    dump_jsonl(output / "disagreement.jsonl", result["disagreements"])
    (output / "agreement_summary.json").write_text(
        json.dumps(result["summary"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
