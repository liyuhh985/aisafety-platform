from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import build_consensus_dataset as bcd
import contract as c

SUB_BY_MAJOR = {
    "traffic": "road_occupancy",
    "municipal": "manhole_damage",
    "fire": "fire_lane_blocked",
    "building": "structural_damage",
    "utility": "wire_fault",
    "construction": "deep_pit",
    "elevator_special": "elevator_stopped",
    "environment_other": "garbage_pile",
}


def make_items(pos_per_major: int = 10, neg_per_group: int = 10):
    items = []
    for major in c.MAJOR_CODES:
        for index in range(pos_per_major):
            items.append({
                "file": f"{major}-pos-{index}.jpg",
                "source_path": f"C:/images/{major}-pos-{index}.jpg",
                "source_category": SUB_BY_MAJOR[major],
                "mapped_category": SUB_BY_MAJOR[major],
                "major_category": major,
                "confuser_group": major,
                "candidate_kind": "positive",
                "source_candidate_kind": "positive",
                "sha256": f"{major}-pos-{index}",
                "dhash64": random.Random(f"{major}-pos-{index}").getrandbits(64),
                "has_hazard": True,
                "subcategory": SUB_BY_MAJOR[major],
                "difficulty": "",
                "text_in_image": None,
                "notes": "visible hazard",
                "reviewer": "model_consensus",
                "review_time": "2026-11-06T10:00:00+00:00",
                "label_status": "reviewed",
                "label_source": c.MODEL_LABEL_SOURCE,
                "annotation_models": ["mimo-v2.6-flash", "glm-5.3-flash"],
            })
        for index in range(neg_per_group):
            items.append({
                "file": f"{major}-neg-{index}.jpg",
                "source_path": f"C:/images/{major}-neg-{index}.jpg",
                "source_category": SUB_BY_MAJOR[major],
                "mapped_category": SUB_BY_MAJOR[major],
                "major_category": "",
                "confuser_group": major,
                "candidate_kind": "negative",
                "source_candidate_kind": "negative",
                "sha256": f"{major}-neg-{index}",
                "dhash64": random.Random(f"{major}-neg-{index}").getrandbits(64),
                "has_hazard": False,
                "subcategory": "",
                "difficulty": "",
                "text_in_image": None,
                "notes": "visible normal scene",
                "reviewer": "model_consensus",
                "review_time": "2026-11-06T10:00:00+00:00",
                "label_status": "reviewed",
                "label_source": c.MODEL_LABEL_SOURCE,
                "annotation_models": ["mimo-v2.6-flash", "glm-5.3-flash"],
            })
    return items


def test_normalize_consensus_items_marks_model_provenance():
    pool = [{
        "file": "a.jpg",
        "source_path": "C:/a.jpg",
        "source_category": "elevator_stopped",
        "mapped_category": "elevator_stopped",
        "major_category": "elevator_special",
        "confuser_group": "elevator_special",
        "candidate_kind": "positive",
        "sha256": "a",
        "dhash64": 1,
    }]
    rows = [{
        "sha256": "a",
        "file": "a.jpg",
        "label": {
            "status": "valid",
            "has_hazard": True,
            "major_category": "elevator_special",
            "subcategory": "elevator_stopped",
            "evidence": "电梯困人",
        },
    }]
    items = bcd.normalize_consensus_items(pool, rows, {
        "A": "mimo-v2.6-flash",
        "B": "glm-5.3-flash",
        "created_at": "2026-11-06T10:00:00+00:00",
    })
    assert items[0]["label_source"] == c.MODEL_LABEL_SOURCE
    assert items[0]["source_candidate_kind"] == "positive"
    assert items[0]["candidate_kind"] == "positive"


def test_select_consensus_dataset_outputs_exact_quotas():
    manifest = bcd.select_consensus_dataset(make_items(), seed=7)
    items = manifest["items"]
    test = [item for item in items if item["split"] == "test"]
    assert len(items) == 160
    assert len(test) == 80
    assert sum(item["has_hazard"] is True for item in test) == 40
    assert sum(item["has_hazard"] is False for item in test) == 40
    for major in c.MAJOR_CODES:
        assert sum(item["has_hazard"] is True and item["major_category"] == major for item in items) == 10
        assert sum(item["split"] == "test" and item["has_hazard"] is True and item["major_category"] == major for item in items) == 5
        assert sum(item["has_hazard"] is False and item["confuser_group"] == major for item in items) == 10


def test_select_consensus_dataset_reports_missing_positive_quota():
    items = make_items()
    items = [item for item in items if not (item["major_category"] == "fire" and item["file"] == "fire-pos-0.jpg")]
    with pytest.raises(ValueError, match="fire"):
        bcd.select_consensus_dataset(items, seed=7)


def test_select_consensus_dataset_rejects_near_duplicate():
    items = make_items()
    items[1]["dhash64"] = items[0]["dhash64"]
    with pytest.raises(ValueError, match="near duplicate"):
        bcd.select_consensus_dataset(items, seed=7)
