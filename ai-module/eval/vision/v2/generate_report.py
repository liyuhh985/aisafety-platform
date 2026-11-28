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


def generate_interview_notes(baseline: dict, final: dict, comparison: dict) -> str:
    winner = comparison.get("winner", "baseline")
    b = baseline
    f = final
    delta = comparison.get("delta", {})
    decision = (
        "Final prompt 未通过预注册安全门槛，所以我不声称它整体优于 baseline。"
        if winner != "final"
        else "Final prompt 通过预注册安全门槛，按同一冻结 test 记录为最终方案。"
    )
    return f"""# 评估集面试讲解

## 90 秒主叙事

我做的不是人工 gold benchmark，而是一个 **model-consensus diagnostic set**。旧版双模型流程里，被评测的 DeepSeek 同时也是标注员 A，而且 27.8% 的标签依赖第三方仲裁或单模型兜底。为了去掉这个循环和兜底，我重新做了标注协议：MiMo 和 GLM 通过同一个 OpenDesign 端点独立标注，同一提示词、temperature 0，只保留二分类和 8 大类都一致的样本，分歧和不确定直接剔除。

主候选池 342 张，一致产出 73 个正样本、137 个负样本；大类 Kappa 是 0.808。随后只针对缺口补了 73 张候选和 10 张电梯候选，最终凑出严格的 80 正 / 80 负，test 冻结为 40 正 / 40 负，8 大类各 5 个正样本。

冻结 test 上，baseline recall {_pct(b['binary']['recall'])}、FPR {_pct(b['binary']['fpr'])}、F1 {_pct(b['binary']['f1'])}；final recall {_pct(f['binary']['recall'])}、FPR {_pct(f['binary']['fpr'])}、F1 {_pct(f['binary']['f1'])}。{decision} 这组结果反映的是召回和误报的取舍，不是生产准确率。

## 三个追问

### 1. 为什么这不叫人工标注？

因为标签来源是 MiMo + GLM 两个模型的共识，不是人类逐张确认。Kappa 0.808 表示模型之间的一致性，不代表人工 ground truth。面试里必须说 `model_consensus`，否则就是伪造数据来源。

### 2. 为什么 FPR 只有 {_pct(f['binary']['fpr'])} 还不能说线上误报率？

因为 test 是平衡的 40 正 / 40 负，场景来自公开图片和候选池，不是线上正常图片分布。这里的 FPR 只说明固定 test 里的负样本误报比例。

### 3. 这个评估集最大的局限是什么？

- 小样本：每个大类 test 只有 5 个正样本，置信区间很宽。
- 伪标签：模型共识不是人工 gold。
- 公开场景：不代表真实业务分布。
- 方法价值在于流程、冻结、对比和错误分析，不在于宣称生产准确率。

## 禁止表述

- 不说“人工标注”。
- 不说“人工专家共识”。
- 不说“生产准确率”。
- 不说“线上误报率”。
- 不说“25 类全部通过统计评估”。
- 不说“模型可以自动建单”。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate v2.1 model-consensus report and interview notes")
    parser.add_argument("--baseline-metrics", type=Path, required=True)
    parser.add_argument("--final-metrics", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--error-analysis", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--interview-notes", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline_metrics.read_text(encoding="utf-8"))
    final = json.loads(args.final_metrics.read_text(encoding="utf-8"))
    comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
    error_markdown = args.error_analysis.read_text(encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(generate_report(baseline, final, comparison, error_markdown), encoding="utf-8")
    args.interview_notes.parent.mkdir(parents=True, exist_ok=True)
    args.interview_notes.write_text(generate_interview_notes(baseline, final, comparison), encoding="utf-8")
    print(f"wrote {args.report}")
    print(f"wrote {args.interview_notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
