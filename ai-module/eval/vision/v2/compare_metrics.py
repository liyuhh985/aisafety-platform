from __future__ import annotations

import argparse
import json
from pathlib import Path

DELTA_PATHS = {
    "recall": ("binary", "recall"),
    "precision": ("binary", "precision"),
    "fpr": ("binary", "fpr"),
    "f1": ("binary", "f1"),
    "accuracy": ("binary", "accuracy"),
    "macro_recall": ("major", "macro_recall"),
    "review_rate": ("review_aware", "review_rate"),
    "auto_recall": ("review_aware", "auto_recall"),
    "auto_fpr": ("review_aware", "auto_fpr"),
    "critical_miss_rate": ("review_aware", "critical_miss_rate"),
}


def _value(metrics: dict, path: tuple[str, str], default: float = 0.0) -> float:
    current = metrics
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return float(current) if isinstance(current, (int, float)) else default


def compare_metrics(baseline: dict, final: dict) -> dict:
    delta = {
        name: _value(final, path) - _value(baseline, path)
        for name, path in DELTA_PATHS.items()
    }
    baseline_miss = _value(baseline, ("review_aware", "critical_miss_rate"))
    final_miss = _value(final, ("review_aware", "critical_miss_rate"))
    baseline_auto_fpr = _value(baseline, ("review_aware", "auto_fpr"))
    final_auto_fpr = _value(final, ("review_aware", "auto_fpr"))

    if final_miss > baseline_miss:
        winner = "baseline"
    elif final_auto_fpr < baseline_auto_fpr:
        winner = "final"
    elif delta["f1"] > 0 and final_miss <= baseline_miss:
        winner = "final"
    else:
        winner = "baseline"

    return {
        "baseline": {
            name: _value(baseline, path)
            for name, path in DELTA_PATHS.items()
        },
        "final": {
            name: _value(final, path)
            for name, path in DELTA_PATHS.items()
        },
        "delta": delta,
        "winner": winner,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare baseline and final v2.1 metrics")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    final = json.loads(args.final.read_text(encoding="utf-8"))
    result = compare_metrics(baseline, final)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
