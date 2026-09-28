"""检索关键词构造（plan_retrieval 使用）。"""
from core.assistant_graph import _pick_keyword


def test_pick_keyword_uses_label_and_filled_slots():
    kw = _pick_keyword("危房", {"structure": "裂缝"})
    assert "危房" in kw and "裂缝" in kw


def test_pick_keyword_resolves_subcategory_code_to_chinese_label():
    kw = _pick_keyword("fire_equipment_fault", {"facility_type": "消火栓"})
    assert "消火栓" in kw
    assert not kw.startswith("fire_equipment_fault")


def test_pick_keyword_tolerates_empty_slots():
    assert _pick_keyword("road_occupancy", {}) == _pick_keyword("road_occupancy", {})
    assert _pick_keyword("road_occupancy", {}) != ""
