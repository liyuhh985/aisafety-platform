# -*- coding: utf-8 -*-
"""Render explicit pseudo-label caveats around calibration/test metrics."""

import json


NOTICE = (
    "Thresholds and evaluation use dual-model consensus pseudo-labels.\n"
    "No human gold labels were available.\n"
    "Test metrics are pseudo-label agreement metrics, not production accuracy.\n"
    "Thresholds were selected against dual-model consensus pseudo-labels.\n"
    "No human review was performed."
)


def render_report(metrics: dict) -> str:
    metrics = metrics or {}
    lines = [
        "# Semantic Grounding Pseudo-Label Report",
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
