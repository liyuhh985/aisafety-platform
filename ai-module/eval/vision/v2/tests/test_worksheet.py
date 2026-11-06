from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import make_review_worksheet as wr


def write_manifest(path: Path) -> None:
    manifest = {
        "_meta": {"version": "v2.1-candidate-pool"},
        "items": [
            {
                "file": "candidate.jpg",
                "source_path": "C:/images/candidate.jpg",
                "source_category": "manhole_damage",
                "mapped_category": "manhole_damage",
                "major_category": "municipal",
                "confuser_group": "municipal",
                "candidate_kind": "positive",
                "sha256": "abc",
                "dhash64": 1,
                "label_status": "pending_review",
                "label_source": "",
            },
            {
                "file": "seeded.jpg",
                "source_path": "C:/images/seeded.jpg",
                "source_category": "vehicle_occupancy",
                "mapped_category": "vehicle_occupancy",
                "major_category": "traffic",
                "confuser_group": "traffic",
                "candidate_kind": "positive",
                "sha256": "def",
                "dhash64": 2,
                "has_hazard": True,
                "major_category": "traffic",
                "subcategory": "vehicle_occupancy",
                "difficulty": "easy",
                "text_in_image": False,
                "notes": "车辆占道",
                "reviewer": "余博洋",
                "review_time": "2026-11-06T10:00:00+08:00",
                "label_status": "reviewed",
                "label_source": "legacy_review",
            },
        ],
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def test_worksheet_has_one_row_per_manifest_item(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    worksheet_path = tmp_path / "worksheet.csv"
    write_manifest(manifest_path)

    wr.write_worksheet(manifest_path, worksheet_path)

    with worksheet_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert [row["file"] for row in rows] == ["candidate.jpg", "seeded.jpg"]


def test_worksheet_pending_human_fields_are_blank(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    worksheet_path = tmp_path / "worksheet.csv"
    write_manifest(manifest_path)

    wr.write_worksheet(manifest_path, worksheet_path)

    with worksheet_path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["has_hazard"] == ""
    assert row["major_category"] == ""
    assert row["subcategory"] == ""
    assert row["difficulty"] == ""
    assert row["text_in_image"] == ""
    assert row["notes"] == ""
    assert row["reviewer"] == ""
    assert row["review_time"] == ""
    assert row["label_status"] == "pending_review"


def test_worksheet_preserves_seeded_review_and_source(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    worksheet_path = tmp_path / "worksheet.csv"
    write_manifest(manifest_path)

    wr.write_worksheet(manifest_path, worksheet_path)

    with worksheet_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    seeded = rows[1]
    assert seeded["has_hazard"] == "true"
    assert seeded["subcategory"] == "vehicle_occupancy"
    assert seeded["label_status"] == "reviewed"
    assert seeded["label_source"] == "legacy_review"


def test_worksheet_exposes_stratum_but_not_mapping_as_ground_truth(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    worksheet_path = tmp_path / "worksheet.csv"
    write_manifest(manifest_path)

    wr.write_worksheet(manifest_path, worksheet_path)

    with worksheet_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None
        assert "mapped_category" not in reader.fieldnames
        assert "confuser_group" in reader.fieldnames
        assert "label_source" in reader.fieldnames
