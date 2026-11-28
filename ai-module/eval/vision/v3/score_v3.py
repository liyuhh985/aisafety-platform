# -*- coding: utf-8 -*-
"""
33 类视觉诊断集（v3）分层评分脚本：
输出二分类总体指标（Recall/Precision/FPR/F1/Accuracy + Wilson CI）、
纯视觉 30 类 vs 弱视觉 3 类分层 Recall 与小类准确率、
8 大类与全 33 小类逐类命中统计及常见混淆对。
"""
import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_MODULE = HERE.parents[2]
sys.path.insert(0, str(AI_MODULE))
sys.path.insert(0, str(AI_MODULE / "eval" / "vision" / "v2"))

from core.hazard_taxonomy import ALL_SUBCATEGORY_CODES, SUBCATEGORY_LABELS, SUBCATEGORY_TO_MAJOR
import score_v2


def evaluate_v3(manifest_path: Path, prediction_dir: Path, taxonomy_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    predictions = score_v2.load_predictions(prediction_dir, items)
    base = score_v2.evaluate_items(items, predictions, taxonomy_path)

    by_sub = {}
    for code in ALL_SUBCATEGORY_CODES:
        by_sub[code] = {
            "label": SUBCATEGORY_LABELS[code],
            "major": SUBCATEGORY_TO_MAJOR[code],
            "n": 0,
            "detected": 0,
            "major_correct": 0,
            "sub_correct": 0,
            "pred_subs": collections.Counter(),
        }

    tier_stats = collections.defaultdict(lambda: {"n": 0, "detected": 0, "major_correct": 0, "sub_correct": 0})
    sub_confusions = collections.Counter()
    fp_cases = []
    fn_cases = []

    for item, raw_pred in zip(items, predictions):
        parsed = score_v2._parsed_prediction(raw_pred)
        has_hazard_pred = isinstance(parsed, dict) and parsed.get("has_hazard") is True
        pred_major = str(parsed.get("major_category") or "") if isinstance(parsed, dict) else ""
        pred_sub = str(parsed.get("subcategory") or "") if isinstance(parsed, dict) else ""

        if item.get("has_hazard"):
            sub = item["subcategory"]
            maj = item["major_category"]
            tier = item.get("visual_tier", "pure_visual")
            row = by_sub[sub]
            row["n"] += 1
            tier_stats[tier]["n"] += 1
            if has_hazard_pred:
                row["detected"] += 1
                tier_stats[tier]["detected"] += 1
                if pred_major == maj:
                    row["major_correct"] += 1
                    tier_stats[tier]["major_correct"] += 1
                if pred_sub == sub:
                    row["sub_correct"] += 1
                    tier_stats[tier]["sub_correct"] += 1
                else:
                    sub_confusions[f"{sub} -> {pred_sub or 'INVALID'}"] += 1
                row["pred_subs"][pred_sub or "INVALID"] += 1
            else:
                sub_confusions[f"{sub} -> FN"] += 1
                row["pred_subs"]["FN"] += 1
                fn_cases.append({"file": item["file"], "subcategory": sub, "notes": item.get("notes", "")})
        else:
            if has_hazard_pred:
                fp_cases.append({
                    "file": item["file"],
                    "hard_negative_for": item.get("hard_negative_for", ""),
                    "pred_major": pred_major,
                    "pred_sub": pred_sub,
                    "confidence": parsed.get("confidence", "") if isinstance(parsed, dict) else "",
                    "reason": parsed.get("description", "")[:80] if isinstance(parsed, dict) else "",
                })

    pos_n = sum(r["n"] for r in by_sub.values())
    total_sub_ok = sum(r["sub_correct"] for r in by_sub.values())
    total_maj_ok = sum(r["major_correct"] for r in by_sub.values())

    by_sub_serial = {}
    for code, r in by_sub.items():
        n = r["n"]
        by_sub_serial[code] = {
            "label": r["label"],
            "major": r["major"],
            "n": n,
            "recall": r["detected"] / n if n else 0.0,
            "major_acc": r["major_correct"] / n if n else 0.0,
            "sub_acc": r["sub_correct"] / n if n else 0.0,
            "preds": dict(r["pred_subs"]),
        }

    tier_out = {}
    for tier, t in tier_stats.items():
        n = t["n"]
        tier_out[tier] = {
            "n": n,
            "recall": t["detected"] / n if n else 0.0,
            "major_acc": t["major_correct"] / n if n else 0.0,
            "sub_acc": t["sub_correct"] / n if n else 0.0,
        }

    base["v3_positive_summary"] = {
        "n": pos_n,
        "major_acc": total_maj_ok / pos_n if pos_n else 0.0,
        "subcategory_acc": total_sub_ok / pos_n if pos_n else 0.0,
        "by_visual_tier": tier_out,
        "by_subcategory": by_sub_serial,
        "top_sub_confusions": dict(sub_confusions.most_common(20)),
    }
    base["fp_cases"] = fp_cases
    base["fn_cases"] = fn_cases
    return base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--predictions", type=Path, required=True)
    ap.add_argument("--taxonomy", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    res = evaluate_v3(args.manifest, args.predictions, args.taxonomy)
    args.output.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    b = res["binary"]
    p = res["v3_positive_summary"]
    print(
        f"V3 EVAL DONE: n={b['n']} (tp={b['tp']}, tn={b['tn']}, fp={b['fp']}, fn={b['fn']}) | "
        f"Recall={b['recall']:.3f}, Precision={b['precision']:.3f}, FPR={b['fpr']:.3f}, F1={b['f1']:.3f} | "
        f"MajorAcc={p['major_acc']:.3f}, SubAcc={p['subcategory_acc']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
