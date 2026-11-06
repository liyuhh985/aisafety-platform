from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import pytest

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import contract as c
import freeze_test as ft

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


def make_final_manifest(path: Path, label_source: str = "human_reviewed") -> None:
    items = []
    for major in c.MAJOR_CODES:
        for kind, count in (("positive", 10), ("negative", 10)):
            for index in range(count):
                is_positive = kind == "positive"
                filename = f"{major}-{kind}-{index}.jpg"
                source_path = path.parent / filename
                source_path.write_bytes(b"x")
                items.append({
                    "file": filename,
                    "source_path": str(source_path),
                    "source_category": f"{major}-source",
                    "mapped_category": SUB_BY_MAJOR[major],
                    "major_category": major if is_positive else "",
                    "confuser_group": major,
                    "candidate_kind": kind,
                    "sha256": hashlib.sha256(filename.encode("utf-8")).hexdigest(),
                    "dhash64": random.Random(filename).getrandbits(64),
                    "split": "test" if index < 5 else "dev",
                    "label_status": "reviewed",
                    "has_hazard": is_positive,
                    "subcategory": SUB_BY_MAJOR[major] if is_positive else "",
                    "difficulty": "easy",
                    "text_in_image": False,
                    "notes": "fixture",
                    "reviewer": "余博洋",
                    "review_time": "2026-11-06T10:00:00+08:00",
                    "label_source": label_source,
                })
    path.write_text(
        json.dumps({"_meta": {"version": "v2.1"}, "items": items}, ensure_ascii=False),
        encoding="utf-8",
    )


def make_prompt_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "prompt_manifest.json"
    path.write_text(
        json.dumps({
            "baseline": {"id": "baseline", "sha256": "a" * 64},
            "final": {"id": "final", "sha256": "b" * 64},
        }),
        encoding="utf-8",
    )
    return path


def test_freeze_creates_80_item_test_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    frozen_path = tmp_path / "frozen.json"
    make_final_manifest(manifest_path)

    ft.freeze_test_manifest(
        manifest_path,
        frozen_path,
        protocol_version="v2.1",
        prompt_manifest_path=make_prompt_manifest(tmp_path),
    )

    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    assert len(frozen["items"]) == 80
    assert frozen["_meta"]["test_positive"] == 40
    assert frozen["_meta"]["test_negative"] == 40
    assert frozen["_meta"]["dev_total"] == 80
    assert frozen["_meta"]["protocol_version"] == "v2.1"
    assert all(len(item["label_sha256"]) == 64 for item in frozen["items"])
    assert all(len(item["prompt_baseline_sha256"]) == 64 for item in frozen["items"])
    assert all(len(item["prompt_final_sha256"]) == 64 for item in frozen["items"])


def test_freeze_uses_has_hazard_not_candidate_kind(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    make_final_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = next(
        item for item in manifest["items"]
        if item["split"] == "test" and item["candidate_kind"] == "positive"
    )
    item["has_hazard"] = False
    item["major_category"] = ""
    item["subcategory"] = ""
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="40 positive"):
        ft.freeze_test_manifest(
            manifest_path,
            tmp_path / "frozen.json",
            protocol_version="v2.1",
            prompt_manifest_path=make_prompt_manifest(tmp_path),
        )


def test_freeze_rejects_ai_direct_label(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    make_final_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    next(item for item in manifest["items"] if item["split"] == "test")["label_source"] = "ai_direct"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="label source"):
        ft.freeze_test_manifest(
            manifest_path,
            tmp_path / "frozen.json",
            protocol_version="v2.1",
            prompt_manifest_path=make_prompt_manifest(tmp_path),
        )


def test_freeze_rejects_near_duplicate_pair(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    make_final_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["items"][1]["dhash64"] = manifest["items"][0]["dhash64"]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="near duplicate"):
        ft.freeze_test_manifest(
            manifest_path,
            tmp_path / "frozen.json",
            protocol_version="v2.1",
            prompt_manifest_path=make_prompt_manifest(tmp_path),
        )


def test_freeze_refuses_overwrite_without_force(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    frozen_path = tmp_path / "frozen.json"
    make_final_manifest(manifest_path)
    prompt_manifest = make_prompt_manifest(tmp_path)
    ft.freeze_test_manifest(
        manifest_path,
        frozen_path,
        protocol_version="v2.1",
        prompt_manifest_path=prompt_manifest,
    )

    with pytest.raises(FileExistsError):
        ft.freeze_test_manifest(
            manifest_path,
            frozen_path,
            protocol_version="v2.1",
            prompt_manifest_path=prompt_manifest,
        )

def test_freeze_accepts_model_consensus_mode(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    frozen_path = tmp_path / "frozen.json"
    make_final_manifest(manifest_path, label_source=c.MODEL_LABEL_SOURCE)

    ft.freeze_test_manifest(
        manifest_path,
        frozen_path,
        protocol_version=c.MODEL_PROTOCOL_VERSION,
        prompt_manifest_path=make_prompt_manifest(tmp_path),
        annotation_mode="model_consensus",
    )

    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    assert frozen["_meta"]["annotation_mode"] == "model_consensus"
    assert frozen["_meta"]["label_source"] == c.MODEL_LABEL_SOURCE
    assert all(item["label_source"] == c.MODEL_LABEL_SOURCE for item in frozen["items"])


def test_freeze_human_mode_rejects_model_consensus_labels(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    make_final_manifest(manifest_path, label_source=c.MODEL_LABEL_SOURCE)

    with pytest.raises(ValueError, match="label source"):
        ft.freeze_test_manifest(
            manifest_path,
            tmp_path / "frozen.json",
            protocol_version="v2.1",
            prompt_manifest_path=make_prompt_manifest(tmp_path),
        )
