# Semantic Grounding Pseudo-Label Report

Thresholds and evaluation use dual-model consensus pseudo-labels.
No human gold labels were available.
Test metrics are pseudo-label agreement metrics, not production accuracy.
Thresholds were selected against dual-model consensus pseudo-labels.
No human review was performed.

## Quality Metrics

- Overall agreement: 0.7436
- Cohen's kappa: 0.5149

## Frozen Thresholds

```json
{
  "threshold_a": 0.75,
  "threshold_b": 0.7,
  "threshold_c": 0.7,
  "dataset": "qv-pseudo-v1",
  "notice": "Thresholds were calibrated against dual-model consensus pseudo-labels.\nNo human review was performed."
}
```

## Auto-Accept Metrics

```json
{
  "A": {
    "slot_class": "A",
    "threshold": 0.75,
    "precision": 1.0,
    "coverage": 0.6666666666666666,
    "accepted": 2
  },
  "B": {
    "slot_class": "B",
    "threshold": 0.7,
    "precision": 1.0,
    "coverage": 1.0,
    "accepted": 1
  }
}
```

These figures measure agreement with dual-model consensus pseudo-labels. They are not production accuracy and were not validated by human gold labels.
