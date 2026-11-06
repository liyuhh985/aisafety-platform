from __future__ import annotations

import sys
from pathlib import Path

import pytest

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import contract as c
import pilot_consensus as pc


def make_pool():
    items = []
    for major_index, major in enumerate(c.MAJOR_CODES):
        for index in range(8):
            items.append({
                "file": f"{major}-pos-{index}.jpg",
                "sha256": f"{major}-pos-{index}",
                "dhash64": major_index * 1000 + index,
                "candidate_kind": "positive",
                "major_category": major,
                "confuser_group": major,
                "source_path": f"C:/images/{major}-pos-{index}.jpg",
            })
        for index in range(4):
            items.append({
                "file": f"{major}-neg-{index}.jpg",
                "sha256": f"{major}-neg-{index}",
                "dhash64": major_index * 1000 + 500 + index,
                "candidate_kind": "negative",
                "major_category": "",
                "confuser_group": major,
                "source_path": f"C:/images/{major}-neg-{index}.jpg",
            })
    return {"items": items}


def test_select_pilot_sample_is_stratified_and_deterministic():
    pool = make_pool()
    first = pc.select_pilot_sample(pool, sample_size=60, seed=7)
    second = pc.select_pilot_sample(pool, sample_size=60, seed=7)

    assert [item["sha256"] for item in first] == [item["sha256"] for item in second]
    assert len(first) == 60
    positives = [item for item in first if item["candidate_kind"] == "positive"]
    negatives = [item for item in first if item["candidate_kind"] == "negative"]
    assert len(positives) == 40
    assert len(negatives) == 20
    for major in c.MAJOR_CODES:
        assert sum(item["major_category"] == major for item in positives) == 5
        assert sum(item["confuser_group"] == major for item in negatives) >= 2


def test_normalize_annotation_marks_uncertain_and_invalid():
    valid = pc.normalize_annotation({
        "has_hazard": True,
        "uncertain": False,
        "major_category": "municipal",
        "subcategory": "manhole_damage",
        "evidence": "井盖破损",
    })
    uncertain = pc.normalize_annotation({"has_hazard": False, "uncertain": True})
    invalid = pc.normalize_annotation({"has_hazard": True, "uncertain": False, "major_category": "bad"})

    assert valid["status"] == "valid"
    assert uncertain["status"] == "uncertain"
    assert invalid["status"] == "invalid"


def test_cohen_kappa_handles_perfect_and_chance_agreement():
    assert pc.cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == pytest.approx(1.0)
    assert pc.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == pytest.approx(0.0)


def test_build_pilot_summary_excludes_disagreement_and_uncertainty():
    items = [
        {"sha256": "1", "file": "1.jpg", "candidate_kind": "positive", "major_category": "traffic", "confuser_group": "traffic"},
        {"sha256": "2", "file": "2.jpg", "candidate_kind": "positive", "major_category": "traffic", "confuser_group": "traffic"},
        {"sha256": "3", "file": "3.jpg", "candidate_kind": "negative", "major_category": "", "confuser_group": "municipal"},
    ]
    labels_a = {
        "1": {"has_hazard": True, "uncertain": False, "major_category": "traffic", "subcategory": "road_occupancy", "evidence": "占用道路", "status": "valid"},
        "2": {"has_hazard": True, "uncertain": False, "major_category": "traffic", "subcategory": "vehicle_occupancy", "evidence": "车辆占道", "status": "valid"},
        "3": {"has_hazard": False, "uncertain": False, "major_category": "", "subcategory": "", "evidence": "正常", "status": "valid"},
    }
    labels_b = {
        "1": {"has_hazard": True, "uncertain": False, "major_category": "traffic", "subcategory": "road_occupancy", "evidence": "占用道路", "status": "valid"},
        "2": {"has_hazard": True, "uncertain": False, "major_category": "municipal", "subcategory": "manhole_damage", "evidence": "井盖", "status": "valid"},
        "3": {"has_hazard": False, "uncertain": False, "major_category": "", "subcategory": "", "evidence": "正常", "status": "valid"},
    }

    result = pc.build_pilot_summary(items, labels_a, labels_b)

    assert result["valid_pairs"] == 3
    assert result["consensus"]["binary_major"] == 2
    assert result["consensus"]["exact"] == 2
    assert result["rejected"]["major_disagreement"] == 1

def test_run_model_passes_temperature_to_client(tmp_path):
    class FakeClient:
        def __init__(self):
            self.seen = []

        def analyze(self, image_path, prompt, temperature):
            self.seen.append(temperature)
            return '{"has_hazard": false, "uncertain": false, "evidence": "normal"}'

        @staticmethod
        def _extract_json(text):
            import json
            return json.loads(text)

    client = FakeClient()
    items = [{"sha256": "abc", "source_path": "C:/image.jpg"}]
    result = pc._run_model(items, client, "prompt", tmp_path, workers=1, temperature=0.3)

    assert result["abc"]["status"] == "valid"
    assert client.seen == [0.3]
