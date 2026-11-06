from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

FIELDS = [
    "file",
    "source_path",
    "source_category",
    "candidate_kind",
    "confuser_group",
    "prelabel_confidence",
    "has_hazard",
    "major_category",
    "subcategory",
    "difficulty",
    "text_in_image",
    "notes",
    "reviewer",
    "review_time",
    "label_status",
    "label_source",
    "exclude_reason",
]


def _bool_text(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def write_worksheet(manifest_path: Path, output_path: Path) -> int:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for item in items:
            status = item.get("label_status", "pending_review")
            reviewed = status in {"reviewed", "excluded"}
            writer.writerow({
                "file": item.get("file", ""),
                "source_path": item.get("source_path", ""),
                "source_category": item.get("source_category", ""),
                "candidate_kind": item.get("candidate_kind", ""),
                "confuser_group": item.get("confuser_group", ""),
                "prelabel_confidence": item.get("prelabel_confidence", ""),
                "has_hazard": _bool_text(item.get("has_hazard")) if reviewed else "",
                "major_category": item.get("major_category", "") if reviewed else "",
                "subcategory": item.get("subcategory", "") if reviewed else "",
                "difficulty": item.get("difficulty", "") if reviewed else "",
                "text_in_image": _bool_text(item.get("text_in_image")) if reviewed else "",
                "notes": item.get("notes", "") if reviewed else "",
                "reviewer": item.get("reviewer", "") if reviewed else "",
                "review_time": item.get("review_time", "") if reviewed else "",
                "label_status": status if reviewed else "pending_review",
                "label_source": item.get("label_source", "") if reviewed else "",
                "exclude_reason": item.get("exclude_reason", "") if reviewed else "",
            })
    return len(items)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the v2.1 human review worksheet")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parent / "candidate_pool.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "review_worksheet.csv",
    )
    args = parser.parse_args()
    count = write_worksheet(args.manifest, args.output)
    print(f"wrote {count} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
