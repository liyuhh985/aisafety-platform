from __future__ import annotations

import argparse
import json
from pathlib import Path


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _metric_table(baseline: dict, final: dict) -> str:
    rows = [
        ("Recall", "recall"),
        ("Precision", "precision"),
        ("FPR", "fpr"),
        ("F1", "f1"),
        ("Accuracy", "accuracy"),
        ("Macro Recall", None),
        ("Review Rate", None),
        ("Critical Miss Rate", None),
    ]
    lines = ["| 指标 | Baseline | Final |", "|---|---:|---:|"]
    for label, key in rows:
        if key:
            b = baseline["binary"][key]
            f = final["binary"][key]
        elif label == "Macro Recall":
            b = baseline["major"]["macro_recall"]
            f = final["major"]["macro_recall"]
        elif label == "Review Rate":
            b = baseline["review_aware"]["review_rate"]
            f = final["review_aware"]["review_rate"]
        else:
            b = baseline["review_aware"]["critical_miss_rate"]
            f = final["review_aware"]["critical_miss_rate"]
        lines.append(f"| {label} | {_pct(b)} | {_pct(f)} |")
    return "\n".join(lines)


def generate_report(baseline: dict, final: dict, comparison: dict, error_markdown: str) -> str:
    winner = comparison.get("winner", "baseline")
    delta = comparison.get("delta", {})
    report = f"""# Vision Evaluation v2.1 · Model-Consensus Diagnostic Report

> 标签来源：`model_consensus`。这是 MiMo 与 GLM 双模型共识伪标签诊断集，不是人工 gold benchmark。
> 评估对象：DeepSeek V4.1 Flash。
> test：80 张，40 正 / 40 负，8 大类各 5 个正样本。

## 核心结果

{_metric_table(baseline, final)}

## 对比结论

- 预注册 winner：**{winner}**
- Recall 变化：{_pct(delta.get('recall', 0.0))}
- FPR 变化：{_pct(delta.get('fpr', 0.0))}
- Precision 变化：{_pct(delta.get('precision', 0.0))}
- F1 变化：{_pct(delta.get('f1', 0.0))}
- Critical Miss Rate 变化：{_pct(delta.get('critical_miss_rate', 0.0))}

Final prompt 没有通过预注册安全门槛，因此不声称整体优化。Final 的精度/FPR 优势应作为召回-误报取舍展示，而不是单项冠军。

## 方法边界

- 标注方式：MiMo + GLM 独立标注，二分类和大类一致才保留。
- Kappa 只表示模型一致性，不是人工一致性。
- 这是伪标签诊断集，不是人工 gold；不能据此声称生产准确率或线上误报率。
- 测试集是平衡设计，不能代表真实业务分布。
- 低置信度样本应转人工复核；模型不能自动建单。

## 错误分析

{error_markdown}
"""
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate v2.1 model-consensus report")
    parser.add_argument("--baseline-metrics", type=Path, required=True)
    parser.add_argument("--final-metrics", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--error-analysis", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline_metrics.read_text(encoding="utf-8"))
    final = json.loads(args.final_metrics.read_text(encoding="utf-8"))
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    error_markdown = args.error_analysis.read_text(encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(generate_report(baseline, final, comparison, error_markdown), encoding="utf-8")
    print(f"wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
