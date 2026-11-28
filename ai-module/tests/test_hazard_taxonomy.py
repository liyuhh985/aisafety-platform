from core.hazard_taxonomy import (
    ALL_SUBCATEGORY_CODES,
    SUBCATEGORY_DEFAULT_RISK,
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


def test_retired_subcategories_are_not_silent_aliases():
    retired = (
        "building/wall_crack_lean",
        "建筑安全/墙体开裂/倾斜",
        "墙体开裂/倾斜",
        "building/facade_fall",
        "建筑安全/外立面脱落",
        "外立面脱落",
        "fire/fire_water_abnormal",
        "消防安全/消防水源异常",
        "消防水源异常",
    )
    for value in retired:
        assert normalize_taxonomy(value) is None, value
    assert len(ALL_SUBCATEGORY_CODES) == 33
    assert "wall_crack_lean" not in ALL_SUBCATEGORY_CODES
    assert "facade_fall" not in ALL_SUBCATEGORY_CODES
    assert "fire_water_abnormal" not in ALL_SUBCATEGORY_CODES


def test_v2b_adds_four_high_value_subcategories():
    expected = {
        "ebike_hazard": "fire",
        "tree_fall_hazard": "municipal",
        "confined_space": "construction",
        "hazmat_storage": "environment_other",
    }
    for code, major in expected.items():
        assert code in ALL_SUBCATEGORY_CODES
        assert normalize_taxonomy(f"{major}/{code}") == (major, code)
    assert len(ALL_SUBCATEGORY_CODES) == 33


def test_every_subcategory_has_a_default_risk_and_no_phantom_entries():
    assert set(SUBCATEGORY_DEFAULT_RISK) == set(ALL_SUBCATEGORY_CODES)
    assert set(SUBCATEGORY_DEFAULT_RISK.values()) <= {"high", "medium", "low"}
    assert SUBCATEGORY_DEFAULT_RISK["hazmat_storage"] == "high"
    assert SUBCATEGORY_DEFAULT_RISK["confined_space"] == "high"
    assert SUBCATEGORY_DEFAULT_RISK["garbage_pile"] == "low"


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
