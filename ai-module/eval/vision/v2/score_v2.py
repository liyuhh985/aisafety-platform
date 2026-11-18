from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import contract

REVIEW_CONFIDENCES = {"高", "中"}


def binary_metrics(y_true: list[int], y_pred: list[int]) -> dict[str, float]:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    tp = sum(1 for truth, pred in zip(y_true, y_pred) if truth and pred)
    tn = sum(1 for truth, pred in zip(y_true, y_pred) if not truth and not pred)
    fp = sum(1 for truth, pred in zip(y_true, y_pred) if not truth and pred)
    fn = sum(1 for truth, pred in zip(y_true, y_pred) if truth and not pred)
    recall = tp / (tp + fn) if tp + fn else 0.0
    precision = tp / (tp + fp) if tp + fp else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = (tp + tn) / len(y_true) if y_true else 0.0
    return {
        "n": len(y_true),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "recall": recall,
        "precision": precision,
        "fpr": fpr,
        "f1": f1,
        "accuracy": accuracy,
    }


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, center - half), min(1.0, center + half)


def load_taxonomy(path: Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        sub["code"]: major["code"]
        for major in data
        for sub in major.get("subcategories", [])
    }


def _parsed_prediction(prediction: dict) -> dict | None:
    if not isinstance(prediction, dict):
        return None
    if "parsed" in prediction:
        parsed = prediction.get("parsed")
        return parsed if isinstance(parsed, dict) else None
    if prediction.get("error"):
        return None
    return prediction


def _gold_major(item: dict, major_by_sub: dict[str, str]) -> str:
    return str(item.get("major_category") or major_by_sub.get(item.get("subcategory", ""), ""))


def _prediction_major(parsed: dict, major_by_sub: dict[str, str]) -> str:
    return str(parsed.get("major_category") or major_by_sub.get(parsed.get("subcategory", ""), ""))


def evaluate_items(gold_items: list[dict], predictions: list[dict], taxonomy_path: Path) -> dict:
    if len(gold_items) != len(predictions):
        raise ValueError("gold_items and predictions must have the same length")
    major_by_sub = load_taxonomy(taxonomy_path)

    y_true: list[int] = []
    y_pred: list[int] = []
    invalid = {
        "parse_failed": 0,
        "invalid_has_hazard": 0,
        "invalid_confidence": 0,
        "invalid_category": 0,
    }
    review_required = 0
    review_positive = 0
    review_negative = 0
    auto_tp = auto_tn = auto_fp = auto_fn = 0
    major_counts = {major: {"n": 0, "correct": 0} for major in contract.MAJOR_CODES}
    confusion: dict[str, int] = defaultdict(int)

    for item, raw_prediction in zip(gold_items, predictions):
        parsed = _parsed_prediction(raw_prediction)
        gold_positive = item.get("has_hazard") is True
        y_true.append(1 if gold_positive else 0)

        needs_review = False
        if parsed is None:
            invalid["parse_failed"] += 1
            needs_review = True
            pred_positive = False
        else:
            has_hazard = parsed.get("has_hazard")
            if not isinstance(has_hazard, bool):
                invalid["invalid_has_hazard"] += 1
                needs_review = True
                pred_positive = False
            else:
                pred_positive = has_hazard

            confidence = parsed.get("confidence")
            if confidence not in REVIEW_CONFIDENCES:
                invalid["invalid_confidence"] += 1
                needs_review = True

            if pred_positive:
                pred_major = _prediction_major(parsed, major_by_sub)
                subcategory = str(parsed.get("subcategory", ""))
                if (
                    pred_major not in contract.MAJOR_CODES
                    or major_by_sub.get(subcategory) != pred_major
                ):
                    invalid["invalid_category"] += 1
                    needs_review = True

        y_pred.append(1 if pred_positive else 0)
        if needs_review:
            review_required += 1
            if gold_positive:
                review_positive += 1
            else:
                review_negative += 1
            continue

        if gold_positive and pred_positive:
            auto_tp += 1
        elif gold_positive:
            auto_fn += 1
        elif pred_positive:
            auto_fp += 1
        else:
            auto_tn += 1

        if gold_positive:
            gold_major = _gold_major(item, major_by_sub)
            major_counts.setdefault(gold_major, {"n": 0, "correct": 0})["n"] += 1
            if pred_positive:
                pred_major = _prediction_major(parsed, major_by_sub)
                confusion[f"{gold_major} -> {pred_major}"] += 1
                if pred_major == gold_major:
                    major_counts[gold_major]["correct"] += 1
            else:
                confusion[f"{gold_major} -> FN"] += 1

    binary = binary_metrics(y_true, y_pred)
    total_positive = sum(y_true)
    total_negative = len(y_true) - total_positive

    for major, row in major_counts.items():
        row["recall"] = row["correct"] / row["n"] if row["n"] else 0.0
    macro_recall = sum(row["recall"] for row in major_counts.values()) / len(contract.MAJOR_CODES)

    recall_ci = wilson_interval(binary["tp"], binary["tp"] + binary["fn"])
    fpr_ci = wilson_interval(binary["fp"], binary["fp"] + binary["tn"])
    return {
        "binary": binary,
        "binary_recall_ci": {"estimate": recall_ci[0], "low": recall_ci[1], "high": recall_ci[2]},
        "binary_fpr_ci": {"estimate": fpr_ci[0], "low": fpr_ci[1], "high": fpr_ci[2]},
        "review_aware": {
            "review_rate": review_required / len(gold_items) if gold_items else 0.0,
            "auto_coverage": 1 - (review_required / len(gold_items)) if gold_items else 0.0,
            "auto_recall": auto_tp / total_positive if total_positive else 0.0,
            "critical_miss_rate": auto_fn / total_positive if total_positive else 0.0,
            "auto_fpr": auto_fp / total_negative if total_negative else 0.0,
            "review_positive": review_positive,
            "review_negative": review_negative,
            "auto_tp": auto_tp,
            "auto_tn": auto_tn,
            "auto_fp": auto_fp,
            "auto_fn": auto_fn,
        },
        "major": {
            "macro_recall": macro_recall,
            "by_major": major_counts,
            "confusion": dict(sorted(confusion.items())),
        },
        "invalid": invalid,
        "limitations": [
            "public-scene diagnostic set, not production-traffic distribution",
            "small balanced test set; confidence intervals are wide",
            "single reviewer; labels are not expert consensus",
            "subcategory accuracy is not reported",
        ],
    }


def load_predictions(prediction_dir: Path, items: list[dict]) -> list[dict]:
    predictions = []
    for item in items:
        path = Path(prediction_dir) / f"{item['sha256']}.json"
        if not path.is_file():
            raise FileNotFoundError(f"missing prediction: {path}")
        predictions.append(json.loads(path.read_text(encoding="utf-8")))
    return predictions


def evaluate(
    manifest_path: Path,
    prediction_dir: Path,
    taxonomy_path: Path,
    split: str | None = None,
) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    if split is not None:
        items = [item for item in items if item.get("split") == split]
    predictions = load_predictions(prediction_dir, items)
    result = evaluate_items(items, predictions, taxonomy_path)
    result["split"] = split or "all"
    result["items"] = len(items)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a v2.1 vision evaluation run")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", default=None)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.manifest, args.predictions, args.taxonomy, split=args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote metrics to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
