# -*- coding: utf-8 -*-
"""Shared protocol constants and JSONL helpers for semantic grounding."""

import hashlib
import json
import re
from pathlib import Path

LABELS = ("entailed", "neutral", "contradicted")
LABEL_SET = set(LABELS)
SPLITS = ("dev", "test")
BOUNDARY_SPLIT = "boundary"
SLOT_CLASSES = ("A", "B", "C")
THRESHOLDS = (0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
OVERALL_AGREEMENT_GATE = 0.75
COHEN_KAPPA_GATE = 0.60
PRECISION_TARGETS = {"A": 0.98, "B": 0.95, "C": 0.95}
BASE_DATASET = "qv-pseudo-v1"
BASE_TOTAL = 150
LABEL_TOTAL = 50
DEV_TOTAL = 90
TEST_TOTAL = 60
BOUNDARY_MIN = 20
BOUNDARY_MAX = 30


def load_jsonl(path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def dump_jsonl(path, rows) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    )
    target.write_text(text, encoding="utf-8")


def stable_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_content_text(value) -> str:
    return re.sub(r"[\s\W_]+", "", str(value or ""), flags=re.UNICODE).casefold()


def content_fingerprint(row) -> str:
    """Normalized quote/value/source identity used for leakage checks."""
    parts = [
        normalize_content_text((row or {}).get(field, ""))
        for field in ("quote", "value", "source_text")
    ]
    return sha256_text("|".join(parts))


def labeler_visible_fingerprint(row) -> str:
    """Semantic identity of exactly what the labeler can distinguish."""
    parts = [
        normalize_content_text((row or {}).get(field, ""))
        for field in ("category", "slot", "value", "quote")
    ]
    return sha256_text("|".join(parts))
