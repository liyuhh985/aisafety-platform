from __future__ import annotations

import sys
from pathlib import Path

import pytest

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import build_v2a_manifest as v2a


TAXONOMY = {
    "dangerous_building": "building",
    "falling_object": "building",
    "illegal_structure": "building",
    "fire_equipment_fault": "fire",
    "fire_lane_blocked": "fire",
    "deep_pit": "construction",
}


def test_retired_source_folders_map_only_to_the_three_merged_targets():
    assert v2a.map_positive_label({"source_category": "wall_crack_lean", "subcategory": ""}, TAXONOMY) == (
        "building", "dangerous_building")
    assert v2a.map_positive_label({"source_category": "facade_fall", "subcategory": "structural_damage"}, TAXONOMY) == (
        "building", "falling_object")
    assert v2a.map_positive_label({"source_category": "fire_water_abnormal", "subcategory": "road_surface_collapse"}, TAXONOMY) == (
        "fire", "fire_equipment_fault")


def test_private_visual_codes_fall_back_to_their_canonical_subcategory():
    assert v2a.map_positive_label(
        {"source_category": "construction_prot", "subcategory": "deep_pit"}, TAXONOMY
    ) == ("construction", "deep_pit")


def test_unknown_positive_label_fails_closed():
    with pytest.raises(ValueError, match="cannot map v2a label"):
        v2a.map_positive_label(
            {"source_category": "construction_prot", "subcategory": "unknown"}, TAXONOMY
        )
