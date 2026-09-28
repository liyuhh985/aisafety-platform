from core.hazard_taxonomy import (
    ALL_SUBCATEGORY_CODES,
    HAZARD_TYPE_MAX_LENGTH,
    HAZARD_TAXONOMY,
    format_hazard_type,
    normalize_taxonomy,
    parse_hazard_type,
)


def test_equipment_fault_and_lane_block_are_distinct():
    assert normalize_taxonomy("utility/exposed_wire") == ("utility", "exposed_wire")
    assert normalize_taxonomy("fire/fire_equipment_fault") == (
        "fire",
        "fire_equipment_fault",
    )
    assert normalize_taxonomy("fire/fire_lane_blocked") == (
        "fire",
        "fire_lane_blocked",
    )


def test_legacy_mapping_is_supported():
    assert normalize_taxonomy("消防设施") == ("fire", "fire_equipment_fault")
    assert normalize_taxonomy("占道") == ("traffic", "road_occupancy")
    assert normalize_taxonomy("井盖/道路") == ("municipal", "manhole_damage")


def test_task_storage_format_round_trips():
    value = format_hazard_type("fire", "fire_equipment_fault")
    assert value == "fire/fire_equipment_fault"
    assert parse_hazard_type(value) == ("fire", "fire_equipment_fault")
    assert parse_hazard_type("消防设施") == ("fire", "fire_equipment_fault")


def test_every_subcategory_code_is_unique():
    assert len(ALL_SUBCATEGORY_CODES) == sum(
        len(item["subcategories"]) for item in HAZARD_TAXONOMY
    )


def test_major_mismatch_is_corrected_by_subcategory():
    assert normalize_taxonomy("municipal/fire_equipment_fault") == (
        "fire",
        "fire_equipment_fault",
    )


def test_submit_categories_include_every_canonical_subcategory():
    from core.hazard_categories import SUBMIT_CATEGORIES
    assert "fire_equipment_fault" in SUBMIT_CATEGORIES
    assert "dangerous_building" in SUBMIT_CATEGORIES
    assert "gas_leak" in SUBMIT_CATEGORIES


def test_task_extractor_accepts_new_subcategory_codes(monkeypatch):
    from tools import hazard_submit
    monkeypatch.setattr(
        hazard_submit._extractor,
        "_call_llm",
        lambda *_, **__: {"content": (
            '{"category":"fire/fire_equipment_fault",'
            '"address":"三明市万达广场对面","district":"三明市",'
            '"description":"消防设施老旧","severity":1}'
        )},
    )
    info = hazard_submit._extract([], "消防设施老旧")
    assert info["category"] == "fire/fire_equipment_fault"


def test_task_extractor_normalizes_legacy_category(monkeypatch):
    from tools import hazard_submit
    monkeypatch.setattr(
        hazard_submit._extractor,
        "_call_llm",
        lambda *_, **__: {"content": (
            '{"category":"消防设施","address":"三明市万达广场对面",'
            '"district":"三明市","description":"消防设施老旧","severity":1}'
        )},
    )
    info = hazard_submit._extract([], "消防设施老旧")
    assert info["category"] == "fire/fire_equipment_fault"


def test_hazard_type_values_fit_the_persisted_column():
    values = [
        format_hazard_type(item["code"], subcategory_code)
        for item in HAZARD_TAXONOMY
        for subcategory_code, _ in item["subcategories"]
    ]
    assert max(len(value) for value in values) <= HAZARD_TYPE_MAX_LENGTH
