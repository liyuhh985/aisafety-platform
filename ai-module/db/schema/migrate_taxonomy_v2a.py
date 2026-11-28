# -*- coding: utf-8 -*-
"""Taxonomy v2a migration: merge 3 redundant hazard subcategories.

The script is deliberately fail-closed:

* schema discovery rejects any unregistered business classification column;
* dry-run validates every row against the 29-path target taxonomy;
* ``tb_hazard_knowledge.category`` is a document-type enum, not a hazard
  taxonomy column, so it is backed up and audited but never rewritten;
* execute only runs after a separately verified backup exists.
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

import pymysql

from db_config import DB_CONFIG

LEGACY_PATH_MAP = {
    "建筑安全/墙体开裂/倾斜": "建筑安全/危房",
    "建筑安全/外立面脱落": "建筑安全/高空坠物",
    "消防安全/消防水源异常": "消防安全/消防设施故障",
}

RETIRED_CODES = {
    "wall_crack_lean",
    "facade_fall",
    "fire_water_abnormal",
}

TARGET_TAXONOMY_PATHS = frozenset(
    {
        "交通与通行/占道经营/乱堆乱放",
        "交通与通行/车辆占道",
        "交通与通行/盲道占用",
        "交通与通行/交通设施损坏",
        "市政设施/井盖缺失/破损",
        "市政设施/路面塌陷",
        "市政设施/排水/积水",
        "市政设施/路灯/线杆损坏",
        "消防安全/消防通道占用",
        "消防安全/消防设施故障",
        "建筑安全/危房",
        "建筑安全/高空坠物",
        "建筑安全/违规搭建",
        "电气与燃气/裸露/老化电线",
        "电气与燃气/配电设施故障",
        "电气与燃气/私拉乱接",
        "电气与燃气/燃气泄漏",
        "电气与燃气/燃气管道老化",
        "施工安全/未设置围挡",
        "施工安全/无安全警示",
        "施工安全/脚手架/临边防护",
        "施工安全/深基坑风险",
        "施工安全/施工临时用电",
        "电梯与特种设备/电梯困人",
        "电梯与特种设备/停运/异响",
        "电梯与特种设备/超期未检",
        "环境与其他/垃圾堆积",
        "环境与其他/污水/异味",
        "环境与其他/其他",
    }
)

TARGET_TAXONOMY_COLUMNS = (
    ("tb_hazard", "hazard_types"),
    ("tb_hazard_case", "category"),
    ("tb_regulation", "category"),
)

AUDIT_ONLY_COLUMNS = (
    ("tb_hazard_report", "hazard_category"),
    ("ai_historical_analysis", "hazard_category"),
    ("tb_hazard_knowledge", "category"),
)

BACKUP_TABLES = (
    "tb_hazard",
    "tb_hazard_case",
    "tb_regulation",
    "tb_hazard_knowledge",
)

KNOWLEDGE_DOCUMENT_CATEGORIES = frozenset(
    {"POLICY", "BUILDING", "FACILITY", "FIRE", "TRAFFIC"}
)

ARCHIVE_TABLE_RE = re.compile(
    r"^(?:ai_hazard_create_(?:request|outbox)_archive|[a-z_]+_archive|"
    r"[a-z_]+_bak[_a-z0-9]*)$"
)

BACKUP_STAMP_RE = re.compile(r"^[0-9]{8}_[0-9]{6}$")

TECHNICAL_COLUMNS = frozenset(
    {"hazard_id", "event_type", "action_type", "content_type"}
)


class SchemaStopGate(RuntimeError):
    """Raised when schema discovery finds an unregistered classification field."""


@dataclass(frozen=True)
class TableAnalysis:
    table: str
    column: str
    total: int
    changed: int
    deduped: int
    updates: tuple[tuple[int, str], ...]


def _ensure_plain_value(raw, label: str = "分类值") -> str:
    if raw is None:
        raise ValueError(f"{label}不能为空")
    value = str(raw)
    if not value or value != value.strip():
        raise ValueError(f"{label}为空或含首尾空白: {value!r}")
    return value


def validate_taxonomy_value(raw) -> str:
    value = _ensure_plain_value(raw)
    if value in LEGACY_PATH_MAP:
        raise ValueError(f"退役分类路径不得继续写入: {value}")
    if value in RETIRED_CODES:
        raise ValueError(f"退役分类编码不得继续写入: {value}")
    if "," in value:
        raise ValueError(f"单值分类字段不得包含逗号: {value}")
    if value not in TARGET_TAXONOMY_PATHS:
        raise ValueError(f"分类不在 v2a 29 类白名单: {value}")
    return value


def transform_single_taxonomy(raw) -> str:
    value = _ensure_plain_value(raw)
    if value in LEGACY_PATH_MAP:
        return validate_taxonomy_value(LEGACY_PATH_MAP[value])
    return validate_taxonomy_value(value)


def transform_multi_taxonomy(raw) -> str:
    value = _ensure_plain_value(raw)
    parts = value.split(",")
    if any(not part or part != part.strip() for part in parts):
        raise ValueError(f"多值分类格式非法: {value}")

    transformed = []
    for part in parts:
        if part in LEGACY_PATH_MAP:
            part = LEGACY_PATH_MAP[part]
        part = validate_taxonomy_value(part)
        if part not in transformed:
            transformed.append(part)

    if not 1 <= len(transformed) <= 3:
        raise ValueError(f"多值分类去重后数量非法: {value}")
    return ",".join(transformed)


def validate_knowledge_category(raw) -> str:
    value = _ensure_plain_value(raw)
    if value in LEGACY_PATH_MAP or value in RETIRED_CODES:
        raise ValueError(f"知识库 category 出现退役 taxonomy 值: {value}")
    if "/" in value:
        raise ValueError(f"知识库 category 不是文档类型枚举: {value}")
    if value not in KNOWLEDGE_DOCUMENT_CATEGORIES:
        raise ValueError(f"知识库 category 枚举非法: {value}")
    return value


def _looks_like_archived_table(table: str) -> bool:
    return bool(ARCHIVE_TABLE_RE.match(table))


def discover_registered_columns(rows):
    """Classify broad information_schema matches and fail on unknown business columns."""
    discovered = {
        "taxonomy": [],
        "audit": [],
        "archive": [],
        "technical": [],
    }
    taxonomy_set = set(TARGET_TAXONOMY_COLUMNS)
    audit_set = set(AUDIT_ONLY_COLUMNS)

    for row in rows:
        if not row or len(row) < 2:
            continue
        table, column = str(row[0]), str(row[1])
        pair = (table, column)
        if pair in taxonomy_set:
            bucket = "taxonomy"
        elif pair in audit_set:
            bucket = "audit"
        elif _looks_like_archived_table(table):
            bucket = "archive"
        elif column in TECHNICAL_COLUMNS:
            bucket = "technical"
        else:
            raise SchemaStopGate(
                "Schema 发现闸门触发：未登记业务分类列 %s.%s；"
                "请先核实归属并更新执行文档/白名单" % (table, column)
            )
        discovered[bucket].append(pair)

    missing_targets = taxonomy_set - set(discovered["taxonomy"])
    if missing_targets:
        raise SchemaStopGate(
            "Schema 发现闸门触发：缺少主迁移列 " + ", ".join(
                "%s.%s" % pair for pair in sorted(missing_targets)
            )
        )
    missing_audits = audit_set - set(discovered["audit"])
    if missing_audits:
        raise SchemaStopGate(
            "Schema 发现闸门触发：缺少已登记审计列 " + ", ".join(
                "%s.%s" % pair for pair in sorted(missing_audits)
            )
        )
    return {key: tuple(value) for key, value in discovered.items()}


def analyze_table(table: str, column: str, rows, multi: bool) -> TableAnalysis:
    updates = []
    changed = 0
    deduped = 0
    for row_id, raw in rows:
        if multi:
            transformed = transform_multi_taxonomy(raw)
            before_parts = str(raw).split(",")
            after_parts = transformed.split(",")
            if len(after_parts) < len(before_parts):
                deduped += 1
        else:
            transformed = transform_single_taxonomy(raw)
        if transformed != raw:
            changed += 1
            updates.append((int(row_id), transformed))
    return TableAnalysis(
        table=table,
        column=column,
        total=len(rows),
        changed=changed,
        deduped=deduped,
        updates=tuple(updates),
    )


def _audit_value(table: str, column: str, raw) -> str:
    value = _ensure_plain_value(raw, f"{table}.{column}")
    if table == "tb_hazard_knowledge" and column == "category":
        return validate_knowledge_category(value)
    for retired_path in LEGACY_PATH_MAP:
        if retired_path in value:
            raise ValueError(f"{table}.{column} 出现退役路径: {retired_path}")
    for retired_code in RETIRED_CODES:
        if retired_code in value:
            raise ValueError(f"{table}.{column} 出现退役编码: {retired_code}")
    return value


def _select_values(cur, table: str, column: str, order_by="id"):
    cur.execute(f"SELECT `{order_by}`, `{column}` FROM `{table}` ORDER BY `{order_by}`")
    return cur.fetchall()


def analyze_database(cur):
    taxonomy = []
    for table, column in TARGET_TAXONOMY_COLUMNS:
        rows = _select_values(cur, table, column)
        taxonomy.append(
            analyze_table(table, column, rows, multi=(table == "tb_hazard"))
        )
    for table, column in AUDIT_ONLY_COLUMNS:
        for row_id, raw in _select_values(cur, table, column):
            try:
                _audit_value(table, column, raw)
            except ValueError as exc:
                raise ValueError(f"审计校验失败 id={row_id}: {exc}") from exc
    return taxonomy


def run_schema_discovery(cur):
    cur.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND (COLUMN_NAME LIKE '%%hazard%%'
               OR COLUMN_NAME LIKE '%%category%%'
               OR COLUMN_NAME LIKE '%%type%%')
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """
    )
    rows = cur.fetchall()
    print("[Schema] 潜在分类/类型列：")
    for row in rows:
        print("  %s.%s | %s | nullable=%s" % (row[0], row[1], row[2], row[3]))
    registered = discover_registered_columns(rows)
    print("[Schema] 迁移列 = %s" % (registered["taxonomy"],))
    print("[Schema] 审计列 = %s" % (registered["audit"],))
    print("[Schema] 归档/备份列 = %d 个" % len(registered["archive"]))
    print("[Schema] 技术字段 = %s" % (registered["technical"],))
    return registered


def print_analysis(analyses):
    print("[Dry-run] 主表迁移统计：")
    for item in analyses:
        print(
            "  %s.%s total=%d changed=%d dedupe=%d"
            % (item.table, item.column, item.total, item.changed, item.deduped)
        )
        for row_id, value in item.updates[:5]:
            print("    id=%s -> %s" % (row_id, value))


def backup_tables(conn, stamp: str):
    if not BACKUP_STAMP_RE.match(stamp):
        raise ValueError("backup stamp 格式必须为 YYYYMMDD_HHMMSS")
    backups = {}
    with conn.cursor() as cur:
        for table in BACKUP_TABLES:
            backup = "%s_bak_v2a_%s" % (table, stamp)
            cur.execute("SELECT COUNT(*) FROM `%s`" % table)
            expected = int(cur.fetchone()[0])
            cur.execute("CREATE TABLE IF NOT EXISTS `%s` LIKE `%s`" % (backup, table))
            cur.execute("TRUNCATE TABLE `%s`" % backup)
            cur.execute("INSERT INTO `%s` SELECT * FROM `%s`" % (backup, table))
            cur.execute("SELECT COUNT(*) FROM `%s`" % backup)
            actual = int(cur.fetchone()[0])
            if actual != expected:
                raise RuntimeError(
                    "备份行数不一致 %s: expected=%d actual=%d"
                    % (backup, expected, actual)
                )
            backups[table] = backup
            print("[Backup] %s -> %s (%d rows)" % (table, backup, actual))
    conn.commit()
    return backups


def verify_backups(cur, stamp: str):
    backups = {}
    for table in BACKUP_TABLES:
        backup = "%s_bak_v2a_%s" % (table, stamp)
        cur.execute("SELECT COUNT(*) FROM `%s`" % backup)
        backup_count = int(cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM `%s`" % table)
        live_count = int(cur.fetchone()[0])
        if backup_count != live_count:
            raise RuntimeError(
                "备份校验失败 %s: live=%d backup=%d"
                % (backup, live_count, backup_count)
            )
        backups[table] = backup
    print("[Backup] 已核验 %d 张表，行数一致" % len(backups))
    return backups


def apply_analyses(cur, analyses):
    for item in analyses:
        for row_id, value in item.updates:
            cur.execute(
                "UPDATE `%s` SET `%s`=%%s WHERE id=%%s" % (item.table, item.column),
                (value, row_id),
            )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Taxonomy v2a migration")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="validate and print only")
    group.add_argument("--backup-only", action="store_true", help="create four snapshots")
    group.add_argument("--execute", action="store_true", help="apply migration transaction")
    parser.add_argument("--backup-stamp", default="", help="existing YYYYMMDD_HHMMSS backup stamp")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not (args.dry_run or args.backup_only or args.execute):
        args.dry_run = True

    conn = pymysql.connect(**DB_CONFIG, autocommit=False)
    try:
        with conn.cursor() as cur:
            run_schema_discovery(cur)
            analyses = analyze_database(cur)
            print_analysis(analyses)

            if args.execute:
                if args.backup_stamp:
                    verify_backups(cur, args.backup_stamp)
                else:
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_tables(conn, stamp)
                    verify_backups(cur, stamp)
                print("[Execute] 开始事务迁移")
                apply_analyses(cur, analyses)
                post = analyze_database(cur)
                for item in post:
                    if item.changed:
                        raise RuntimeError(
                            "迁移后仍有待替换值 %s.%s changed=%d"
                            % (item.table, item.column, item.changed)
                        )
                conn.commit()
                print("[Execute] COMMIT 完成；v2a 主表共 %d 行合法" % sum(x.total for x in post))
            elif args.backup_only:
                stamp = args.backup_stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_tables(conn, stamp)
            else:
                print("[Dry-run] 未写库、未创建备份")

        return 0
    except Exception as exc:
        conn.rollback()
        print("[STOP] %s" % exc, file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
