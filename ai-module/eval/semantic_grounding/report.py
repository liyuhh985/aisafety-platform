# -*- coding: utf-8 -*-
"""Render explicit pseudo-label caveats around calibration/test metrics."""

import json

from eval.semantic_grounding.protocol import (
    COHEN_KAPPA_GATE,
    OVERALL_AGREEMENT_GATE,
)


NOTICE = (
    "Thresholds and evaluation use dual-model consensus pseudo-labels.\n"
    "No human gold labels were available.\n"
    "Test metrics are pseudo-label agreement metrics, not production accuracy.\n"
    "Thresholds were selected against dual-model consensus pseudo-labels.\n"
    "No human review was performed."
)


def quality_gate_passed(metrics: dict) -> bool:
    metrics = metrics or {}
    return (
        float(metrics.get("overall_agreement") or 0.0) >= OVERALL_AGREEMENT_GATE
        and float(metrics.get("cohen_kappa") or 0.0) >= COHEN_KAPPA_GATE
    )


def render_report(metrics: dict) -> str:
    metrics = metrics or {}
    status = "PASSED" if quality_gate_passed(metrics) else "FAILED QUALITY GATE"
    lines = [
        "# Semantic Grounding Pseudo-Label Report",
        "",
        f"**VALIDATION STATUS: {status}**",
        "",
        NOTICE,
        "",
        "## Quality Metrics",
        "",
        "- Overall agreement: %.4f" % float(metrics.get("overall_agreement") or 0.0),
        "- Cohen's kappa: %.4f" % float(metrics.get("cohen_kappa") or 0.0),
        "",
        "## Frozen Thresholds",
        "",
        "```json",
        json.dumps(metrics.get("thresholds") or {}, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Auto-Accept Metrics",
        "",
        "```json",
        json.dumps(metrics.get("auto_accept") or {}, ensure_ascii=False, indent=2),
        "```",
        "",
        "These figures measure agreement with dual-model consensus pseudo-labels. "
        "They are not production accuracy and were not validated by human gold labels.",
        "",
    ]
    return "\n".join(lines)
