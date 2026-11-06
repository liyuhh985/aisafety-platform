from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import contract


def summarize_progress(pool: dict) -> dict:
    items = pool.get("items", [])
    reviewed = [
        item for item in items
        if item.get("label_status") == "reviewed"
        and item.get("label_source") in contract.ALLOWED_LABEL_SOURCES
    ]
    positive_by_major = Counter(
        item.get("major_category")
        for item in reviewed
        if item.get("has_hazard") is True
    )
    negative_by_group = Counter(
        item.get("confuser_group")
        for item in reviewed
        if item.get("has_hazard") is False
    )
    return {
        "reviewed": len(reviewed),
        "excluded": sum(item.get("label_status") == "excluded" for item in items),
        "pending": sum(
            item.get("label_status") not in {"reviewed", "excluded"}
            for item in items
        ),
        "positive_by_major": {
            major: positive_by_major[major] for major in contract.MAJOR_CODES
        },
        "negative_by_group": {
            major: negative_by_group[major] for major in contract.MAJOR_CODES
        },
        "missing_positive": {
            major: max(0, contract.PER_MAJOR - positive_by_major[major])
            for major in contract.MAJOR_CODES
        },
        "missing_negative": {
            major: max(0, contract.PER_CONFUSER_GROUP - negative_by_group[major])
            for major in contract.MAJOR_CODES
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report v2.1 human-review quota progress")
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pool = json.loads(args.pool.read_text(encoding="utf-8"))
    progress = summarize_progress(pool)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(progress, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
