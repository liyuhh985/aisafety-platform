# -*- coding: utf-8 -*-
"""Validate base/boundary semantic-grounding datasets before labeling."""

from collections import Counter

from core.slot_schemas import SUBCATEGORY_SLOT_SCHEMAS, get_slot_schema
from eval.semantic_grounding.protocol import (
    BOUNDARY_MAX,
    BOUNDARY_MIN,
    BOUNDARY_SPLIT,
    BASE_TOTAL,
    DEV_TOTAL,
    LABEL_SET,
    LABEL_TOTAL,
    SPLITS,
    TEST_TOTAL,
    load_jsonl,
)

REQUIRED_FIELDS = (
    "id",
    "source_group_id",
    "category",
    "slot",
    "slot_class",
    "value",
    "quote",
    "source_text",
    "split",
    "expected_label",
)


def _validate_row(row: dict, *, boundary: bool) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in row]
    if missing:
        raise ValueError("missing fields %s: %s" % (missing, row.get("id", "")))
    for field in ("id", "source_group_id", "category", "slot", "slot_class",
                  "value", "quote", "source_text", "split", "expected_label"):
        if not str(row.get(field) or "").strip():
            raise ValueError("empty field %s: %s" % (field, row.get("id", "")))
    category = str(row["category"])
    if category not in SUBCATEGORY_SLOT_SCHEMAS:
        raise ValueError("non-canonical category %r: %s" % (category, row["id"]))
    schema = {slot.key: slot for slot in get_slot_schema(category)}
    if row["slot"] not in schema:
        raise ValueError("slot %r not allowed for %s: %s" % (
            row["slot"], category, row["id"]))
    if row["slot_class"] != schema[row["slot"]].value_class:
        raise ValueError("slot_class mismatch for %s:%s: %s" % (
            category, row["slot"], row["id"]))
    if row["expected_label"] not in LABEL_SET:
        raise ValueError("invalid expected_label %r: %s" % (
            row["expected_label"], row["id"]))
    if boundary:
        if row["split"] != BOUNDARY_SPLIT:
            raise ValueError("boundary row has invalid split: %s" % row["id"])
    elif row["split"] not in SPLITS:
        raise ValueError("base row has invalid split: %s" % row["id"])


def validate_dataset(base_path, boundary_path) -> dict:
    base = load_jsonl(base_path)
    boundary = load_jsonl(boundary_path)
    for row in base:
        _validate_row(row, boundary=False)
    for row in boundary:
        _validate_row(row, boundary=True)

    ids = [row["id"] for row in base + boundary]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate ids across base/boundary dataset")

    if len(base) != BASE_TOTAL:
        raise ValueError("base_total must be %d, got %d" % (BASE_TOTAL, len(base)))
    base_labels = Counter(row["expected_label"] for row in base)
    if any(base_labels[label] != LABEL_TOTAL for label in LABEL_SET):
        raise ValueError("each expected_label must have %d rows: %s" % (
            LABEL_TOTAL, dict(base_labels)))
    dev_total = sum(row["split"] == "dev" for row in base)
    test_total = sum(row["split"] == "test" for row in base)
    if dev_total != DEV_TOTAL or test_total != TEST_TOTAL:
        raise ValueError("split totals must be dev=%d/test=%d, got dev=%d/test=%d" % (
            DEV_TOTAL, TEST_TOTAL, dev_total, test_total))

    split_groups = {}
    for row in base:
        split_groups.setdefault(row["source_group_id"], set()).add(row["split"])
    leakage = sorted(group for group, splits in split_groups.items()
                     if len(splits) > 1)
    if leakage:
        raise ValueError("source_group_id leakage across dev/test: %s" % leakage)

    if not BOUNDARY_MIN <= len(boundary) <= BOUNDARY_MAX:
        raise ValueError("boundary_total must be %d..%d, got %d" % (
            BOUNDARY_MIN, BOUNDARY_MAX, len(boundary)))

    return {
        "base_total": len(base),
        "base_labels": {label: base_labels[label] for label in sorted(LABEL_SET)},
        "dev_total": dev_total,
        "test_total": test_total,
        "group_leakage": leakage,
        "boundary_total": len(boundary),
        "base_groups": len(split_groups),
    }
