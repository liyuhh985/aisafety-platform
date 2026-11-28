from __future__ import annotations
import sys
from pathlib import Path
V2_DIR=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(V2_DIR))
import build_v2b_manifest as v2b


def test_ebike_notes_relabel_to_new_fire_class():
    taxonomy=v2b.taxonomy_map()
    item={"source_category":"illegal_wiring","subcategory":"illegal_wiring","notes":"飞线给电动自行车充电","evidence":""}
    assert v2b.map_positive_label(item,taxonomy)==("fire","ebike_hazard")


def test_tree_notes_relabel_to_municipal_tree_class():
    taxonomy=v2b.taxonomy_map()
    item={"source_category":"road_surface_collapse","subcategory":"road_surface_collapse","notes":"树木倒伏横在路面","evidence":""}
    assert v2b.map_positive_label(item,taxonomy)==("municipal","tree_fall_hazard")


def test_taxonomy_has_33_classes():
    assert len(v2b.taxonomy_map())==33
