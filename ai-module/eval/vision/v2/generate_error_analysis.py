from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import contract
from score_v2 import load_predictions

REVIEW_CONFIDENCES = {"高", "中"}


def _parsed(prediction: dict | None) -> dict | None:
    if not isinstance(prediction, dict):
        return None
    if "parsed" in prediction:
        parsed = prediction.get("parsed")
        return parsed if isinstance(parsed, dict) else None
    if prediction.get("error"):
        return None
    return prediction


def classify_errors(frozen: dict, predictions: list[dict]) -> dict:
    by_sha = {
        prediction.get("sha256"): prediction
        for prediction in predictions
        if isinstance(prediction, dict) and prediction.get("sha256")
    }
    buckets = {
        "false_positive": {"count": 0, "examples": []},
        "false_negative": {"count": 0, "examples": []},
        "major_confusion": {"count": 0, "examples": []},
        "invalid_output": {"count": 0, "examples": []},
        "review_required": {"count": 0, "examples": []},
    }

    for item in frozen.get("items", []):
        sha = item["sha256"]
        prediction = by_sha.get(sha)
        parsed = _parsed(prediction)
        gold_positive = item.get("has_hazard") is True
        if parsed is None:
            buckets["invalid_output"]["count"] += 1
            buckets["invalid_output"]["examples"].append({"sha256": sha, "file": item.get("file", "")})
            continue

        confidence = parsed.get("confidence")
        if confidence not in REVIEW_CONFIDENCES:
            buckets["review_required"]["count"] += 1
            buckets["review_required"]["examples"].append({
                "sha256": sha,
                "file": item.get("file", ""),
                "confidence": confidence,
            })

        pred_positive = parsed.get("has_hazard")
        if not isinstance(pred_positive, bool):
            buckets["invalid_output"]["count"] += 1
            buckets["invalid_output"]["examples"].append({"sha256": sha, "file": item.get("file", "")})
            continue
        major = str(parsed.get("major_category", ""))
        sub = str(parsed.get("subcategory", ""))
        if pred_positive and (major not in contract.MAJOR_CODES or not sub):
            buckets["invalid_output"]["count"] += 1
            buckets["invalid_output"]["examples"].append({"sha256": sha, "file": item.get("file", "")})

        if gold_positive and not pred_positive:
            bucket = "false_negative"
        elif not gold_positive and pred_positive:
            bucket = "false_positive"
        elif gold_positive and pred_positive and major != item.get("major_category"):
            bucket = "major_confusion"
        else:
            continue
        buckets[bucket]["count"] += 1
        buckets[bucket]["examples"].append({
            "sha256": sha,
            "file": item.get("file", ""),
            "gold_major": item.get("major_category", ""),
            "gold_sub": item.get("subcategory", ""),
            "pred_major": major,
            "pred_sub": sub,
            "confidence": confidence,
        })

    for bucket in buckets.values():
        bucket["examples"] = bucket["examples"][:5]
    return buckets


def _bucket_table(title: str, errors: dict) -> str:
    lines = [f"### {title}", "", "| bucket | count | example files |", "|---|---:|---|"]
    for name, data in errors.items():
        files = ", ".join(example.get("file", "") for example in data["examples"]) or "-"
        lines.append(f"| {name} | {data['count']} | {files} |")
    return "\n".join(lines)


def generate_error_markdown(frozen: dict, baseline: dict, final: dict) -> str:
    meta = frozen.get("_meta", {})
    lines = [
        "# 视觉评估错误分析",
        "",
        "> 标签来源：model_consensus。该文档分析模型共识伪标签下的跨模型错误，不代表人工 gold。",
        f"> annotation_mode: `{meta.get('annotation_mode', '')}`",
        f"> test_total: {meta.get('test_total', '')}",
        "",
        _bucket_table("Baseline", baseline),
        "",
        _bucket_table("Final", final),
        "",
        "## 解读边界",
        "",
        "- 错误桶用于定位模型行为，不代表标签一定正确。",
        "- 由于评估集本身是模型共识伪标签，错误分析只能作为诊断证据。",
        "- 低置信度样本应进入人工复核，不应自动形成正式工单。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate v2.1 model-consensus error analysis")
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frozen = json.loads(args.frozen.read_text(encoding="utf-8"))
    items = frozen.get("items", [])
    baseline_predictions = load_predictions(args.baseline, items)
    final_predictions = load_predictions(args.final, items)
    baseline = classify_errors(frozen, baseline_predictions)
    final = classify_errors(frozen, final_predictions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(generate_error_markdown(frozen, baseline, final), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
