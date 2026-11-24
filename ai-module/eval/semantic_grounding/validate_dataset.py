# -*- coding: utf-8 -*-
"""Validate base/boundary semantic-grounding datasets before labeling."""

import re
from collections import Counter

from core.slot_schemas import SUBCATEGORY_SLOT_SCHEMAS, get_slot_schema
from eval.semantic_grounding.protocol import (
    BOUNDARY_MAX,
    BOUNDARY_MIN,
    BOUNDARY_MAX,
    BOUNDARY_SPLIT,
    BASE_TOTAL,
    DEV_TOTAL,
    LABEL_SET,
    LABEL_TOTAL,
    SPLITS,
    TEST_TOTAL,
    content_fingerprint,
    labeler_visible_fingerprint,
    load_jsonl,
)

BOUNDARY_KINDS = {
    "synonym": 5,
    "negation": 5,
    "number": 5,
    "multi_turn": 5,
    "vision": 5,
    "assistant_misuse": 5,
}
BOUNDARY_SOURCE_KINDS = {"user", "vision", "assistant"}


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
        kind = str(row.get("boundary_kind") or "")
        if kind not in BOUNDARY_KINDS:
            raise ValueError("invalid boundary_kind %r: %s" % (kind, row["id"]))
        source_kind = str(row.get("source_kind") or "")
        source_ref = str(row.get("source_ref") or "")
        if source_kind not in BOUNDARY_SOURCE_KINDS or not source_ref:
            raise ValueError("boundary source metadata missing: %s" % row["id"])
        if kind == "negation":
            if row["expected_label"] != "contradicted":
                raise ValueError("negation boundary must be contradicted: %s" % row["id"])
            if not any(token in row["source_text"] for token in ("没有", "并非", "未", "不是")):
                raise ValueError("negation boundary lacks negation: %s" % row["id"])
        elif kind == "number":
            if row["expected_label"] != "contradicted":
                raise ValueError("number boundary must be contradicted: %s" % row["id"])
            digits = re.findall(r"\d+", row["value"])
            if not digits or all(digit in row["source_text"] for digit in digits):
                raise ValueError("number boundary lacks numeric mismatch: %s" % row["id"])
        elif kind == "multi_turn":
            turns = row.get("turns")
            if not isinstance(turns, list) or len(turns) < 2:
                raise ValueError("multi_turn boundary needs >=2 turns: %s" % row["id"])
        elif kind == "vision":
            if source_kind != "vision" or not source_ref.startswith("v"):
                raise ValueError("vision boundary needs vN source: %s" % row["id"])
        elif kind == "assistant_misuse":
            if source_kind != "assistant" or not source_ref.startswith("a"):
                raise ValueError("assistant boundary needs aN source: %s" % row["id"])
        elif kind == "synonym":
            from core.uncertainty import normalize_text
            if row["expected_label"] != "entailed":
                raise ValueError("synonym boundary must be entailed: %s" % row["id"])
            if normalize_text(row["value"]) in normalize_text(row["quote"]):
                raise ValueError("synonym boundary is direct support, not synonym: %s" % row["id"])
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

    split_hashes = {"dev": {}, "test": {}}
    for row in base:
        split_hashes[row["split"]].setdefault(content_fingerprint(row), []).append(row["id"])
    within_duplicates = []
    for split, hashes in split_hashes.items():
        for fingerprint, identifiers in hashes.items():
            if len(identifiers) > 1:
                within_duplicates.append({
                    "split": split,
                    "fingerprint": fingerprint,
                    "ids": identifiers,
                })
    if within_duplicates:
        raise ValueError("duplicate content within split: %s" % within_duplicates)
    dev_hashes = set(split_hashes["dev"])
    test_hashes = set(split_hashes["test"])
    cross_leakage = sorted(dev_hashes & test_hashes)
    if cross_leakage:
        raise ValueError("content leakage across dev/test: %s" % cross_leakage)

    visible_hashes = {"dev": {}, "test": {}}
    for row in base:
        visible_hashes[row["split"]].setdefault(
            labeler_visible_fingerprint(row), []
        ).append(row["id"])
    visible_within_duplicates = []
    for split, hashes in visible_hashes.items():
        for fingerprint, identifiers in hashes.items():
            if len(identifiers) > 1:
                visible_within_duplicates.append({
                    "split": split,
                    "fingerprint": fingerprint,
                    "ids": identifiers,
                })
    if visible_within_duplicates:
        raise ValueError(
            "duplicate labeler-visible input within split: %s"
            % visible_within_duplicates
        )
    visible_cross_leakage = sorted(
        set(visible_hashes["dev"]) & set(visible_hashes["test"])
    )
    if visible_cross_leakage:
        raise ValueError(
            "labeler-visible leakage across dev/test: %s"
            % visible_cross_leakage
        )

    boundary_kinds = Counter(row["boundary_kind"] for row in boundary)
    if dict(boundary_kinds) != BOUNDARY_KINDS:
        raise ValueError("boundary kinds must each have 5 rows: %s" % dict(boundary_kinds))

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
        "boundary_kinds": dict(boundary_kinds),
        "base_groups": len(split_groups),
        "within_split_content_duplicates": within_duplicates,
        "cross_split_content_leakage": cross_leakage,
        "within_split_labeler_visible_duplicates": visible_within_duplicates,
        "cross_split_labeler_visible_leakage": visible_cross_leakage,
    }
