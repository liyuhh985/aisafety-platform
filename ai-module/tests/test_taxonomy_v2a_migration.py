import re

from db.schema.migrate_taxonomy_v2a import (
    AUDIT_ONLY_COLUMNS,
    BACKUP_TABLES,
    KNOWLEDGE_DOCUMENT_CATEGORIES,
    LEGACY_PATH_MAP,
    SchemaStopGate,
    TARGET_TAXONOMY_COLUMNS,
    analyze_table,
    discover_registered_columns,
    transform_multi_taxonomy,
    validate_knowledge_category,
    validate_taxonomy_value,
)


def test_transform_multi_taxonomy_replaces_and_dedupes_in_original_order():
    raw = (
        "建筑安全/危房,建筑安全/墙体开裂/倾斜,"
        "消防安全/消防水源异常,消防安全/消防设施故障"
    )

    assert transform_multi_taxonomy(raw) == (
        "建筑安全/危房,消防安全/消防设施故障"
    )


def test_validate_taxonomy_rejects_retired_paths():
    for retired in LEGACY_PATH_MAP:
        try:
            validate_taxonomy_value(retired)
        except ValueError as exc:
            assert "退役" in str(exc)
        else:
            raise AssertionError(f"retired path accepted: {retired}")


def test_validate_knowledge_category_accepts_document_types_and_rejects_legacy_paths():
    for category in KNOWLEDGE_DOCUMENT_CATEGORIES:
        validate_knowledge_category(category)

    for retired in LEGACY_PATH_MAP:
        try:
            validate_knowledge_category(retired)
        except ValueError as exc:
            assert "退役" in str(exc)
        else:
            raise AssertionError(f"legacy taxonomy accepted as knowledge type: {retired}")


def test_discover_registered_columns_allows_only_explicit_audit_and_archive_rows():
    rows = [
        ("tb_hazard", "hazard_types"),
        ("tb_hazard_case", "category"),
        ("tb_regulation", "category"),
        ("tb_hazard_knowledge", "category"),
        ("tb_hazard_report", "hazard_category"),
        ("ai_historical_analysis", "hazard_category"),
        ("tb_hazard_action", "hazard_id"),
        ("ai_hazard_create_outbox", "event_type"),
        ("tb_hazard_bak_20261030_083201", "hazard_types"),
    ]

    discovered = discover_registered_columns(rows)

    assert set(discovered["taxonomy"]) == set(TARGET_TAXONOMY_COLUMNS)
    assert set(discovered["audit"]) == set(AUDIT_ONLY_COLUMNS)
    assert ("tb_hazard_action", "hazard_id") in discovered["technical"]
    assert ("ai_hazard_create_outbox", "event_type") in discovered["technical"]
    assert ("tb_hazard_bak_20261030_083201", "hazard_types") in discovered["archive"]


def test_discover_rejects_unregistered_business_classification_column():
    rows = [("tb_new_business", "category")]

    try:
        discover_registered_columns(rows)
    except SchemaStopGate as exc:
        assert "tb_new_business.category" in str(exc)
    else:
        raise AssertionError("unregistered business table was accepted")


def test_analyze_table_reports_exact_changed_and_dedupe_counts():
    rows = [
        (1, "建筑安全/危房"),
        (2, "建筑安全/墙体开裂/倾斜"),
        (3, "建筑安全/危房,建筑安全/墙体开裂/倾斜"),
    ]

    result = analyze_table("tb_hazard", "hazard_types", rows, multi=True)

    assert result.total == 3
    assert result.changed == 2
    assert result.deduped == 1


def test_backup_table_names_are_versioned_and_cover_four_planned_tables():
    assert BACKUP_TABLES == (
        "tb_hazard",
        "tb_hazard_case",
        "tb_regulation",
        "tb_hazard_knowledge",
    )
    for table in BACKUP_TABLES:
        assert re.fullmatch(r"[a-z_]+", table)
