from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import finalize_labels as fl


def make_case(tmp_path: Path):
    taxonomy = [
        {
            "code": "municipal",
            "label": "市政设施",
            "subcategories": [{"code": "manhole_damage", "label": "井盖缺失/破损"}],
        },
        {
            "code": "traffic",
            "label": "交通与通行",
            "subcategories": [{"code": "vehicle_occupancy", "label": "车辆占道"}],
        },
    ]
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(json.dumps(taxonomy), encoding="utf-8")

    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"image-bytes")
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()

    manifest = {
        "_meta": {"version": "test"},
        "items": [{
            "file": "image.jpg",
            "source_path": str(image_path),
            "source_category": "manhole_damage",
            "mapped_category": "manhole_damage",
            "major_category": "municipal",
            "confuser_group": "municipal",
            "candidate_kind": "positive",
            "sha256": digest,
            "split": "test",
            "label_status": "pending_review",
        }],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    worksheet_path = tmp_path / "review.csv"
    row = {
        "file": "image.jpg",
        "source_path": str(image_path),
        "source_category": "manhole_damage",
        "candidate_kind": "positive",
        "confuser_group": "municipal",
        "has_hazard": "true",
        "major_category": "municipal",
        "subcategory": "manhole_damage",
        "difficulty": "easy",
        "text_in_image": "false",
        "notes": "clear broken cover",
        "reviewer": "tester",
        "review_time": "2026-11-06T10:00:00+08:00",
        "label_status": "reviewed",
        "label_source": "",
        "exclude_reason": "",
    }
    write_rows(worksheet_path, [row])
    return taxonomy_path, manifest_path, worksheet_path, row


def write_rows(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_finalize_accepts_reviewed_positive_and_writes_decisions(tmp_path):
    taxonomy_path, manifest_path, worksheet_path, _ = make_case(tmp_path)
    decisions_path = tmp_path / "decisions.jsonl"

    result = fl.finalize_labels(
        worksheet_path,
        manifest_path,
        taxonomy_path,
        decisions_output=decisions_path,
    )

    assert result["reviewed"] == 1
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = updated["items"][0]
    assert item["label_status"] == "reviewed"
    assert item["has_hazard"] is True
    assert item["subcategory"] == "manhole_damage"
    assert item["label_source"] == "human_reviewed"
    decision = json.loads(decisions_path.read_text(encoding="utf-8").strip())
    assert decision["label_source"] == "human_reviewed"


def test_finalize_skips_pending_rows(tmp_path):
    taxonomy_path, manifest_path, worksheet_path, row = make_case(tmp_path)
    row["label_status"] = "pending_review"
    write_rows(worksheet_path, [row])

    result = fl.finalize_labels(worksheet_path, manifest_path, taxonomy_path)

    assert result["reviewed"] == 0
    assert result["pending"] == 1
    item = json.loads(manifest_path.read_text(encoding="utf-8"))["items"][0]
    assert item["label_status"] == "pending_review"


def test_finalize_accepts_excluded_row(tmp_path):
    taxonomy_path, manifest_path, worksheet_path, row = make_case(tmp_path)
    row.update({
        "has_hazard": "",
        "major_category": "",
        "subcategory": "",
        "difficulty": "",
        "text_in_image": "",
        "label_status": "excluded",
        "exclude_reason": "示意图，非现场",
    })
    write_rows(worksheet_path, [row])

    result = fl.finalize_labels(worksheet_path, manifest_path, taxonomy_path)

    assert result["excluded"] == 1
    item = json.loads(manifest_path.read_text(encoding="utf-8"))["items"][0]
    assert item["label_status"] == "excluded"
    assert item["has_hazard"] is None
    assert item["exclude_reason"] == "示意图，非现场"


def test_finalize_rejects_ai_direct_source(tmp_path):
    taxonomy_path, manifest_path, worksheet_path, row = make_case(tmp_path)
    row["label_source"] = "ai_direct"
    write_rows(worksheet_path, [row])

    with pytest.raises(ValueError, match="ai_direct"):
        fl.finalize_labels(worksheet_path, manifest_path, taxonomy_path)


def test_finalize_rejects_negative_with_subcategory(tmp_path):
    taxonomy_path, manifest_path, worksheet_path, row = make_case(tmp_path)
    row["has_hazard"] = "false"
    row["major_category"] = "municipal"
    row["subcategory"] = "manhole_damage"
    write_rows(worksheet_path, [row])

    with pytest.raises(ValueError, match="negative"):
        fl.finalize_labels(worksheet_path, manifest_path, taxonomy_path)


def test_finalize_rejects_subcategory_from_wrong_major(tmp_path):
    taxonomy_path, manifest_path, worksheet_path, row = make_case(tmp_path)
    row["major_category"] = "traffic"
    write_rows(worksheet_path, [row])

    with pytest.raises(ValueError, match="does not belong"):
        fl.finalize_labels(worksheet_path, manifest_path, taxonomy_path)


def test_finalize_rejects_changed_image_hash(tmp_path):
    taxonomy_path, manifest_path, worksheet_path, _ = make_case(tmp_path)
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"changed")

    with pytest.raises(ValueError, match="sha256"):
        fl.finalize_labels(worksheet_path, manifest_path, taxonomy_path)
