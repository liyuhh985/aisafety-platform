# -*- coding: utf-8 -*-
import collections
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
AI_MODULE = HERE.parents[2]
sys.path.insert(0, str(AI_MODULE))
from core.hazard_taxonomy import ALL_SUBCATEGORY_CODES, SUBCATEGORY_TO_MAJOR


def _assert_manifest(path: Path, expected_total: int, expected_pos: int, expected_per_sub: int, split: str) -> tuple[set[str], list[str]]:
    assert path.is_file(), f"missing {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    assert len(items) == expected_total
    pos = [x for x in items if x.get("has_hazard") is True]
    neg = [x for x in items if x.get("has_hazard") is False]
    assert len(pos) == expected_pos
    assert len(neg) == expected_total - expected_pos

    shas = {x["sha256"] for x in items}
    assert len(shas) == expected_total, f"duplicate sha256 in {path.name}"

    sub_counts = collections.Counter(x["subcategory"] for x in pos)
    assert set(sub_counts.keys()) == set(ALL_SUBCATEGORY_CODES)
    assert all(cnt == expected_per_sub for cnt in sub_counts.values())

    for it in items:
        assert it.get("split") == split
        if it["has_hazard"]:
            assert SUBCATEGORY_TO_MAJOR.get(it["subcategory"]) == it["major_category"]
        else:
            assert it["major_category"] == ""
            assert it["subcategory"] == ""
    missing = [it["source_path"] for it in items if not Path(it["source_path"]).is_file()]
    return shas, missing


def test_v3_dev_and_frozen_test_disjoint_and_complete():
    dev_shas, dev_missing = _assert_manifest(HERE / "dev_manifest.v3.json", 200, 132, 4, "dev")
    test_shas, test_missing = _assert_manifest(HERE / "frozen_test_manifest.v3.json", 120, 66, 2, "test")
    assert not (dev_shas & test_shas), "dev and frozen test share SHA-256!"

    frozen = json.loads((HERE / "frozen_test_manifest.v3.json").read_text(encoding="utf-8"))
    assert frozen["_meta"].get("frozen_at")
    assert frozen["_meta"].get("human_reviewed") is True
    assert all(it.get("label_sha256") and it.get("file_sha256") for it in frozen["items"])

    if dev_missing or test_missing:
        pytest.skip("v3 raw images are local-only; manifests, split isolation and frozen metadata were still validated")
