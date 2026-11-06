from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

V2_DIR = Path(__file__).resolve().parents[1]
VISION_DIR = V2_DIR.parent
sys.path.insert(0, str(V2_DIR))

import build_manifest as bm
import contract as c


def make_balanced_candidates():
    items = []
    for major in c.MAJOR_CODES:
        for index in range(40):
            items.append({
                "file": f"{major}-pos-{index}.jpg",
                "source_path": f"C:/images/{major}-pos-{index}.jpg",
                "source_category": f"{major}_source",
                "mapped_category": "manhole_damage" if major == "municipal" else major,
                "major_category": major,
                "confuser_group": major,
                "candidate_kind": "positive",
                "sha256": f"{major}-pos-{index}",
                "dhash64": index,
                "label_status": "pending_review",
                "label_source": "",
            })
        for index in range(20):
            items.append({
                "file": f"{major}-neg-{index}.jpg",
                "source_path": f"C:/images/{major}-neg-{index}.jpg",
                "source_category": f"{major}_negative",
                "mapped_category": "manhole_damage" if major == "municipal" else major,
                "major_category": "",
                "confuser_group": major,
                "candidate_kind": "negative",
                "sha256": f"{major}-neg-{index}",
                "dhash64": 1000 + index,
                "label_status": "pending_review",
                "label_source": "",
            })
    return items


def write_noise_image(path: Path, seed: int) -> None:
    image = Image.effect_noise((300, 300), 80 + seed).convert("RGB")
    image.save(path, format="JPEG", quality=95)


def test_taxonomy_has_eight_majors_and_25_subcategories():
    taxonomy = bm.load_taxonomy(VISION_DIR / "_taxonomy_final.json")
    assert len(taxonomy.major_codes) == 8
    assert len(taxonomy.major_by_sub) == 25
    assert taxonomy.major_by_sub["manhole_damage"] == "municipal"
    assert taxonomy.major_by_sub["deep_pit"] == "construction"


def test_allocate_quotas_honors_total_and_minimum():
    quotas = bm.allocate_quotas(
        {"traffic": 20, "municipal": 20, "construction": 2},
        total=10,
        minimum=2,
    )
    assert sum(quotas.values()) == 10
    assert all(value >= 2 for value in quotas.values())
    assert quotas["construction"] <= 2
    assert quotas["traffic"] + quotas["municipal"] == 8


def test_candidate_pool_reserves_thirty_positives_per_major():
    items = make_balanced_candidates()

    pool = bm.select_candidate_reservoir(
        items,
        positives_per_major=30,
        negatives_per_group=15,
        seed=7,
    )

    counts = Counter(
        item["major_category"]
        for item in pool
        if item["candidate_kind"] == "positive"
    )
    assert counts == Counter({major: 30 for major in c.MAJOR_CODES})


def test_candidate_pool_reserves_fifteen_negatives_per_confuser_group():
    items = make_balanced_candidates()

    pool = bm.select_candidate_reservoir(
        items,
        positives_per_major=30,
        negatives_per_group=15,
        seed=7,
    )

    counts = Counter(
        item["confuser_group"]
        for item in pool
        if item["candidate_kind"] == "negative"
    )
    assert counts == Counter({major: 15 for major in c.MAJOR_CODES})


def test_candidate_pool_refuses_insufficient_group_capacity():
    items = make_balanced_candidates()
    removed = {f"fire-pos-{index}.jpg" for index in range(29, 40)}
    items = [
        item
        for item in items
        if not (
            item["candidate_kind"] == "positive"
            and item["major_category"] == "fire"
            and item["file"] in removed
        )
    ]

    with pytest.raises(ValueError, match="fire"):
        bm.select_candidate_reservoir(items, seed=7)

def test_apply_seed_decisions_preserves_human_source(tmp_path):
    items = [{
        "file": "candidate.jpg",
        "source_path": str(tmp_path / "candidate.jpg"),
        "sha256": "abc",
        "label_status": "pending_review",
    }]
    decision = {
        "source_path": items[0]["source_path"],
        "file": "candidate.jpg",
        "has_hazard": True,
        "major_category": "municipal",
        "subcategory": "manhole_damage",
        "difficulty": "easy",
        "text_in_image": False,
        "notes": "井盖破损",
        "reviewer": "余博洋",
        "review_time": "2026-11-06T10:00:00+08:00",
        "label_status": "reviewed",
        "label_source": "legacy_review",
    }
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(json.dumps(decision, ensure_ascii=False) + "\n", encoding="utf-8")

    count = bm.apply_seed_decisions(items, decisions)

    assert count == 1
    assert items[0]["has_hazard"] is True
    assert items[0]["label_status"] == "reviewed"
    assert items[0]["label_source"] == "legacy_review"


def test_apply_seed_decisions_rejects_ai_direct(tmp_path):
    items = [{"file": "candidate.jpg", "source_path": "C:/candidate.jpg", "sha256": "abc"}]
    decision = {
        "source_path": "C:/candidate.jpg",
        "has_hazard": False,
        "difficulty": "easy",
        "text_in_image": False,
        "notes": "正常",
        "reviewer": "Codex AI",
        "review_time": "2026-11-06T10:00:00+08:00",
        "label_status": "reviewed",
        "label_source": "ai_direct",
    }
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(json.dumps(decision, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="ai_direct"):
        bm.apply_seed_decisions(items, decisions)


def test_collect_positive_candidates_uses_human_review_pool(tmp_path):
    taxonomy = bm.Taxonomy(
        major_codes=("municipal",),
        major_by_sub={"manhole_damage": "municipal"},
        subcategories_by_major={"municipal": ("manhole_damage",)},
    )
    source = tmp_path / "pool" / "manhole_damage"
    review = source / "review"
    review.mkdir(parents=True)
    (source / "annotations.json").write_text(
        json.dumps({
            "items": {},
            "rejected": [{"file": "rejected.jpg", "reason": "information_insufficient"}],
        }),
        encoding="utf-8",
    )
    write_noise_image(review / "candidate.jpg", 1)
    write_noise_image(review / "rejected.jpg", 2)

    candidates = bm.collect_positive_candidates(tmp_path, taxonomy, set())

    assert [item["file"] for item in candidates] == ["candidate.jpg"]
    assert candidates[0]["mapped_category"] == "manhole_damage"
    assert candidates[0]["major_category"] == "municipal"
    assert isinstance(candidates[0]["dhash64"], int)
    assert candidates[0]["label_status"] == "pending_review"


