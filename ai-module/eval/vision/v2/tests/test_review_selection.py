from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import contract as c
import review_progress as rp
import select_reviewed_set as sr

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


def make_reviewed_fixture(
    positives_per_major: int,
    negatives_per_group: int,
    label_source: str = "human_reviewed",
):
    items = []
    for major_index, major in enumerate(c.MAJOR_CODES):
        for index in range(positives_per_major):
            items.append({
                "file": f"{major}-pos-{index}.jpg",
                "source_path": f"C:/images/{major}-pos-{index}.jpg",
                "source_category": f"{major}_source",
                "mapped_category": SUB_BY_MAJOR[major],
                "major_category": major,
                "confuser_group": major,
                "candidate_kind": "positive",
                "sha256": f"{major}-pos-{index}",
                "dhash64": random.Random(f"{major}-pos-{index}").getrandbits(64),
                "label_status": "reviewed",
                "has_hazard": True,
                "subcategory": SUB_BY_MAJOR[major],
                "difficulty": "easy",
                "text_in_image": False,
                "notes": "visible hazard",
                "reviewer": "余博洋",
                "review_time": "2026-11-06T10:00:00+08:00",
                "label_source": label_source,
            })
        for index in range(negatives_per_group):
            items.append({
                "file": f"{major}-neg-{index}.jpg",
                "source_path": f"C:/images/{major}-neg-{index}.jpg",
                "source_category": f"{major}_negative",
                "mapped_category": SUB_BY_MAJOR[major],
                "confuser_group": major,
                "candidate_kind": "negative",
                "sha256": f"{major}-neg-{index}",
                "dhash64": random.Random(f"{major}-neg-{index}").getrandbits(64),
                "label_status": "reviewed",
                "has_hazard": False,
                "major_category": "",
                "subcategory": "",
                "difficulty": "easy",
                "text_in_image": False,
                "notes": "visible normal scene",
                "reviewer": "余博洋",
                "review_time": "2026-11-06T10:00:00+08:00",
                "label_source": label_source,
            })
    return {"_meta": {"version": "v2.1-candidate-pool"}, "items": items}


def test_progress_reports_deficits():
    pool = make_reviewed_fixture(positives_per_major=9, negatives_per_group=10)

    progress = rp.summarize_progress(pool)

    assert progress["positive_by_major"]["traffic"] == 9
    assert progress["negative_by_group"]["traffic"] == 10
    assert progress["missing_positive"]["traffic"] == 1
    assert progress["missing_negative"]["traffic"] == 0


def test_progress_does_not_count_ai_direct_as_complete():
    pool = make_reviewed_fixture(
        positives_per_major=10,
        negatives_per_group=10,
        label_source="ai_direct",
    )

    progress = rp.summarize_progress(pool)

    assert progress["positive_by_major"]["traffic"] == 0
    assert progress["missing_positive"]["traffic"] == 10


def test_selection_requires_all_quotas():
    pool = make_reviewed_fixture(positives_per_major=9, negatives_per_group=10)

    with pytest.raises(ValueError, match="traffic: 1"):
        sr.select_reviewed_set(pool, seed=7)


def test_selection_outputs_exact_split_counts():
    pool = make_reviewed_fixture(positives_per_major=10, negatives_per_group=10)

    manifest = sr.select_reviewed_set(pool, seed=7)
    test = [item for item in manifest["items"] if item["split"] == "test"]
    dev = [item for item in manifest["items"] if item["split"] == "dev"]

    assert len(manifest["items"]) == 160
    assert len(test) == 80
    assert len(dev) == 80
    assert sum(item["has_hazard"] is True for item in test) == 40
    assert sum(item["has_hazard"] is False for item in test) == 40
    for major in c.MAJOR_CODES:
        assert sum(
            item["split"] == "test"
            and item["has_hazard"] is True
            and item["major_category"] == major
            for item in manifest["items"]
        ) == 5
        assert sum(
            item["split"] == "test"
            and item["has_hazard"] is False
            and item["confuser_group"] == major
            for item in manifest["items"]
        ) == 5


def test_selection_rejects_candidate_kind_mismatch():
    pool = make_reviewed_fixture(positives_per_major=10, negatives_per_group=10)
    pool["items"][0]["candidate_kind"] = "negative"

    with pytest.raises(ValueError, match="candidate_kind"):
        sr.select_reviewed_set(pool, seed=7)


def test_verify_manifest_rejects_near_duplicate_pair():
    pool = make_reviewed_fixture(positives_per_major=10, negatives_per_group=10)
    manifest = sr.select_reviewed_set(pool, seed=7)
    manifest["items"][1]["dhash64"] = manifest["items"][0]["dhash64"]

    with pytest.raises(ValueError, match="near duplicate"):
        sr.verify_manifest(manifest)

