from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import contract


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_bool(value: str, field: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"{field} must be a boolean, got {value!r}")


def load_taxonomy(path: Path) -> tuple[dict[str, str], set[str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    major_by_sub: dict[str, str] = {}
    majors: set[str] = set()
    for major in data:
        major_code = major["code"]
        majors.add(major_code)
        for sub in major.get("subcategories", []):
            major_by_sub[sub["code"]] = major_code
    return major_by_sub, majors


def _decision_row(item: dict, row: dict, label_source: str) -> dict[str, Any]:
    decision = {
        "source_path": item["source_path"],
        "file": item.get("file", ""),
        "has_hazard": item.get("has_hazard"),
        "major_category": item.get("major_category", ""),
        "subcategory": item.get("subcategory", ""),
        "difficulty": item.get("difficulty", ""),
        "text_in_image": item.get("text_in_image"),
        "notes": item.get("notes", ""),
        "reviewer": item.get("reviewer", ""),
        "review_time": item.get("review_time", ""),
        "label_status": item.get("label_status", ""),
        "label_source": label_source,
    }
    if item.get("label_status") == "excluded":
        decision["exclude_reason"] = item.get("exclude_reason", "")
    return decision


def finalize_labels(
    worksheet_path: Path,
    manifest_path: Path,
    taxonomy_path: Path,
    decisions_output: Path | None = None,
) -> dict[str, int]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    by_source = {item["source_path"]: item for item in items}
    if len(by_source) != len(items):
        raise ValueError("manifest contains duplicate source_path values")

    major_by_sub, majors = load_taxonomy(taxonomy_path)
    reviewed = excluded = pending = 0
    seen: set[str] = set()
    decisions: list[dict[str, Any]] = []

    with Path(worksheet_path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        source_path = row.get("source_path", "")
        if source_path not in by_source:
            raise ValueError(f"worksheet source_path not found in manifest: {source_path}")
        if source_path in seen:
            raise ValueError(f"duplicate worksheet source_path: {source_path}")
        seen.add(source_path)

        status = row.get("label_status", "").strip() or "pending_review"
        if status == "pending_review":
            pending += 1
            continue
        if status not in {"reviewed", "excluded"}:
            raise ValueError(f"label_status must be pending_review, reviewed, or excluded: {source_path}")

        if not row.get("reviewer", "").strip():
            raise ValueError(f"reviewer is required: {source_path}")
        if not row.get("review_time", "").strip():
            raise ValueError(f"review_time is required: {source_path}")
        label_source = row.get("label_source", "").strip() or "human_reviewed"
        if label_source == "ai_direct":
            raise ValueError(f"ai_direct cannot be finalized: {source_path}")
        if label_source not in contract.ALLOWED_LABEL_SOURCES:
            raise ValueError(f"unsupported label source: {label_source}")

        item = by_source[source_path]
        image_path = Path(source_path)
        if not image_path.is_file():
            raise ValueError(f"source image missing: {source_path}")
        if sha256_file(image_path) != item["sha256"]:
            raise ValueError(f"sha256 changed after manifest creation: {source_path}")

        base = {
            "notes": row.get("notes", "").strip(),
            "reviewer": row["reviewer"].strip(),
            "review_time": row["review_time"].strip(),
            "label_source": label_source,
        }

        if status == "excluded":
            exclude_reason = row.get("exclude_reason", "").strip()
            if not exclude_reason:
                raise ValueError(f"exclude_reason is required: {source_path}")
            item.update({
                **base,
                "has_hazard": None,
                "major_category": "",
                "subcategory": "",
                "difficulty": "",
                "text_in_image": None,
                "label_status": "excluded",
                "exclude_reason": exclude_reason,
            })
            decisions.append(_decision_row(item, row, label_source))
            excluded += 1
            continue

        if not base["notes"]:
            raise ValueError(f"notes are required for reviewed labels: {source_path}")
        has_hazard = parse_bool(row.get("has_hazard", ""), "has_hazard")
        difficulty = row.get("difficulty", "").strip()
        if difficulty not in {"easy", "medium", "hard"}:
            raise ValueError(f"invalid difficulty: {source_path}")
        text_in_image = parse_bool(row.get("text_in_image", ""), "text_in_image")
        major_category = row.get("major_category", "").strip()
        subcategory = row.get("subcategory", "").strip()

        if has_hazard:
            if item.get("candidate_kind") != "positive":
                raise ValueError(f"candidate_kind mismatch for positive label: {source_path}")
            if not major_category or not subcategory:
                raise ValueError(f"positive row requires major_category and subcategory: {source_path}")
            if major_category not in majors:
                raise ValueError(f"unknown major_category: {source_path}")
            if subcategory not in major_by_sub:
                raise ValueError(f"unknown subcategory: {source_path}")
            if major_by_sub[subcategory] != major_category:
                raise ValueError(f"subcategory does not belong to major_category: {source_path}")
        else:
            if item.get("candidate_kind") != "negative":
                raise ValueError(f"candidate_kind mismatch for negative label: {source_path}")
            if major_category or subcategory:
                raise ValueError(f"negative row must not contain category fields: {source_path}")

        item.update({
            **base,
            "has_hazard": has_hazard,
            "major_category": major_category,
            "subcategory": subcategory,
            "difficulty": difficulty,
            "text_in_image": text_in_image,
            "label_status": "reviewed",
        })
        item.pop("exclude_reason", None)
        decisions.append(_decision_row(item, row, label_source))
        reviewed += 1

    reviewed_items = [item for item in items if item.get("label_status") == "reviewed"]
    excluded_items = [item for item in items if item.get("label_status") == "excluded"]
    pending_items = [
        item for item in items
        if item.get("label_status") not in {"reviewed", "excluded"}
    ]
    positive_by_major = Counter(
        item.get("major_category") for item in reviewed_items if item.get("has_hazard") is True
    )
    negative_by_group = Counter(
        item.get("confuser_group") for item in reviewed_items if item.get("has_hazard") is False
    )
    manifest.setdefault("_meta", {})["label_completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest["_meta"]["review_summary"] = {
        "reviewed": len(reviewed_items),
        "excluded": len(excluded_items),
        "pending": len(pending_items),
        "positive": sum(item.get("has_hazard") is True for item in reviewed_items),
        "negative": sum(item.get("has_hazard") is False for item in reviewed_items),
        "positive_by_major": dict(sorted(positive_by_major.items())),
        "negative_by_group": dict(sorted(negative_by_group.items())),
    }
    Path(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if decisions_output is not None:
        decisions_output = Path(decisions_output)
        decisions_output.parent.mkdir(parents=True, exist_ok=True)
        decisions_output.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in decisions)
            + ("\n" if decisions else ""),
            encoding="utf-8",
        )

    return {
        "reviewed": reviewed,
        "excluded": excluded,
        "pending": pending,
        "total_reviewed": len(reviewed_items),
        "total_excluded": len(excluded_items),
        "total_pending": len(pending_items),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize human-reviewed v2.1 labels")
    parser.add_argument("--worksheet", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--decisions-output", type=Path, default=None)
    args = parser.parse_args()
    result = finalize_labels(
        args.worksheet,
        args.manifest,
        args.taxonomy,
        decisions_output=args.decisions_output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
