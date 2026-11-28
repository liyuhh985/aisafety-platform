# -*- coding: utf-8 -*-
"""Taxonomy v2b migration: four new subcategories and corpus relabeling."""
import argparse
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pymysql

from core.hazard_taxonomy import HAZARD_TAXONOMY
from db_config import DB_CONFIG
from db.schema.migrate_taxonomy_v2a import (
    LEGACY_PATH_MAP,
    RETIRED_CODES,
    run_schema_discovery,
)
from db.seed.data_cases_v2b import CASES_V2B
from db.seed.data_regulations_v2b import REGULATIONS_V2B

TARGET_PATHS = frozenset(
    f"{major['label']}/{sub_label}"
    for major in HAZARD_TAXONOMY
    for _, sub_label in major["subcategories"]
)
assert len(TARGET_PATHS) == 33

BACKUP_TABLES = (
    "tb_hazard",
    "tb_hazard_case",
    "tb_regulation",
    "tb_hazard_knowledge",
)
BACKUP_STAMP_RE = re.compile(r"^[0-9]{8}_[0-9]{6}$")

CASE_RULES = (
    ("title LIKE %s", ("%南京雨花台%",), "消防安全/电动自行车违规停放/充电"),
    ("title LIKE %s", ("%北京通州%",), "消防安全/电动自行车违规停放/充电"),
    ("title LIKE %s", ("%危险化学品%",), "环境与其他/危化品/易燃易爆违规存运"),
    ("title LIKE %s", ("%易燃溶剂%",), "环境与其他/危化品/易燃易爆违规存运"),
    ("title LIKE %s", ("%烟花爆竹%",), "环境与其他/危化品/易燃易爆违规存运"),
    ("title LIKE %s", ("%有限空间%",), "施工安全/有限空间作业风险"),
    ("title LIKE %s", ("%硫化氢%",), "施工安全/有限空间作业风险"),
    ("title = %s", ("北京海淀私家车多次违停堵塞小区消防车通道拒不挪车被行政拘留案",), "消防安全/消防通道占用"),
    ("title = %s", ("昆明官渡某老旧小区高层天台长期堆放废弃旧木家具火灾隐患案",), "消防安全/消防通道占用"),
)

REG_RULES = (
    ("law_name LIKE %s", ("%GB 43854-2024%",), "消防安全/电动自行车违规停放/充电"),
    ("law_name LIKE %s", ("%国办发〔2024〕19号%",), "消防安全/电动自行车违规停放/充电"),
    ("law_name = %s", ("危险化学品安全管理条例",), "环境与其他/危化品/易燃易爆违规存运"),
    ("law_name = %s", ("工贸企业有限空间作业安全规定",), "施工安全/有限空间作业风险"),
    ("law_name = %s AND content LIKE %s", ("城镇排水与污水处理条例", "%有限空间%"), "施工安全/有限空间作业风险"),
)


def _count_rule(cur, table, where, params, target):
    query = f"SELECT COUNT(*) FROM `{table}` WHERE ({where}) AND category <> %s"
    cur.execute(query, (*params, target))
    return int(cur.fetchone()[0])


def _apply_rule(cur, table, where, params, target):
    query = f"UPDATE `{table}` SET category=%s WHERE ({where}) AND category <> %s"
    cur.execute(query, (target, *params, target))
    return int(cur.rowcount)


def _insert_seeds(cur):
    inserted_cases = 0
    inserted_regs = 0
    for case in CASES_V2B:
        cur.execute("SELECT id FROM tb_hazard_case WHERE title=%s LIMIT 1", (case["title"],))
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO tb_hazard_case
            (category,title,description,severity,city,district,occurrence_date,
             casualties,cause,rectification,regulation_ref,source_url,verdict)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                case["category"], case["title"], case["description"], case.get("severity", "中"),
                case.get("city", ""), case.get("district", ""), case.get("occurrence_date", ""),
                case.get("casualties", ""), case.get("cause", ""), case.get("rectification", ""),
                case.get("regulation_ref", ""), case.get("source_url", ""), case.get("verdict", ""),
            ),
        )
        inserted_cases += 1

    for reg in REGULATIONS_V2B:
        cur.execute(
            "SELECT id FROM tb_regulation WHERE law_name=%s AND article=%s AND category=%s LIMIT 1",
            (reg["law_name"], reg["article"], reg["category"]),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO tb_regulation
            (category,law_name,article,content,keywords,penalty,source_url)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                reg["category"], reg["law_name"], reg["article"], reg["content"],
                reg.get("keywords", ""), reg.get("penalty", ""), reg.get("source_url", ""),
            ),
        )
        inserted_regs += 1
    return inserted_cases, inserted_regs


def _validate_path(value, label):
    if value is None or str(value).strip() != value or not value:
        raise ValueError(f"{label} 分类为空或含首尾空白: {value!r}")
    if value in LEGACY_PATH_MAP or value in RETIRED_CODES:
        raise ValueError(f"{label} 出现退役分类: {value}")
    if value not in TARGET_PATHS:
        raise ValueError(f"{label} 不在 v2b 33 类白名单: {value}")


def validate_all(cur):
    for table, column in (("tb_hazard_case", "category"), ("tb_regulation", "category")):
        cur.execute(f"SELECT id,`{column}` FROM `{table}` ORDER BY id")
        for row_id, value in cur.fetchall():
            _validate_path(value, f"{table}.{column} id={row_id}")

    cur.execute("SELECT id,hazard_types FROM tb_hazard ORDER BY id")
    for row_id, raw in cur.fetchall():
        parts = str(raw).split(",")
        if not 1 <= len(parts) <= 3 or len(parts) != len(dict.fromkeys(parts)):
            raise ValueError(f"tb_hazard.hazard_types id={row_id} 多值格式非法: {raw}")
        for part in parts:
            _validate_path(part, f"tb_hazard.hazard_types id={row_id}")

    for table, column in (
        ("tb_hazard_report", "hazard_category"),
        ("ai_historical_analysis", "hazard_category"),
    ):
        cur.execute(f"SELECT id,`{column}` FROM `{table}` ORDER BY id")
        for row_id, value in cur.fetchall():
            text = str(value or "")
            for retired in (*LEGACY_PATH_MAP.keys(), *RETIRED_CODES):
                if retired in text:
                    raise ValueError(f"{table}.{column} id={row_id} 出现退役值: {retired}")

    cur.execute("SELECT id,category FROM tb_hazard_knowledge ORDER BY id")
    for row_id, value in cur.fetchall():
        if value not in {"POLICY", "BUILDING", "FACILITY", "FIRE", "TRAFFIC"}:
            raise ValueError(f"tb_hazard_knowledge.category id={row_id} 枚举非法: {value}")


def backup_tables(conn, stamp):
    if not BACKUP_STAMP_RE.match(stamp):
        raise ValueError("backup stamp 格式必须为 YYYYMMDD_HHMMSS")
    with conn.cursor() as cur:
        for table in BACKUP_TABLES:
            backup = f"{table}_bak_v2b_{stamp}"
            cur.execute(f"SELECT COUNT(*) FROM `{table}`")
            expected = int(cur.fetchone()[0])
            cur.execute(f"CREATE TABLE IF NOT EXISTS `{backup}` LIKE `{table}`")
            cur.execute(f"TRUNCATE TABLE `{backup}`")
            cur.execute(f"INSERT INTO `{backup}` SELECT * FROM `{table}`")
            cur.execute(f"SELECT COUNT(*) FROM `{backup}`")
            actual = int(cur.fetchone()[0])
            if actual != expected:
                raise RuntimeError(f"备份行数不一致 {backup}: expected={expected} actual={actual}")
            print(f"[Backup] {table} -> {backup} ({actual} rows)")
    conn.commit()


def verify_backups(cur, stamp):
    for table in BACKUP_TABLES:
        backup = f"{table}_bak_v2b_{stamp}"
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
        live = int(cur.fetchone()[0])
        cur.execute(f"SELECT COUNT(*) FROM `{backup}`")
        saved = int(cur.fetchone()[0])
        if live != saved:
            raise RuntimeError(f"备份校验失败 {backup}: live={live} backup={saved}")
    print(f"[Backup] 已核验 {len(BACKUP_TABLES)} 张表，行数一致")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Taxonomy v2b migration")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--backup-only", action="store_true")
    group.add_argument("--execute", action="store_true")
    parser.add_argument("--backup-stamp", default="")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not (args.dry_run or args.backup_only or args.execute):
        args.dry_run = True
    conn = pymysql.connect(**DB_CONFIG, autocommit=False)
    try:
        with conn.cursor() as cur:
            run_schema_discovery(cur)
            print("[v2b] case relabel plan:")
            case_updates = []
            for where, params, target in CASE_RULES:
                count = _count_rule(cur, "tb_hazard_case", where, params, target)
                case_updates.append((where, params, target, count))
                print(f"  {count:3d} rows -> {target} [{where}]")
            print("[v2b] regulation relabel plan:")
            reg_updates = []
            for where, params, target in REG_RULES:
                count = _count_rule(cur, "tb_regulation", where, params, target)
                reg_updates.append((where, params, target, count))
                print(f"  {count:3d} rows -> {target} [{where}]")
            print(f"[v2b] seed additions: {len(CASES_V2B)} cases / {len(REGULATIONS_V2B)} regulations (idempotent)")

            if args.execute:
                if args.backup_stamp:
                    verify_backups(cur, args.backup_stamp)
                else:
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_tables(conn, stamp)
                    verify_backups(cur, stamp)
                for where, params, target, _ in case_updates:
                    _apply_rule(cur, "tb_hazard_case", where, params, target)
                for where, params, target, _ in reg_updates:
                    _apply_rule(cur, "tb_regulation", where, params, target)
                inserted_cases, inserted_regs = _insert_seeds(cur)
                validate_all(cur)
                conn.commit()
                print(f"[v2b] committed; inserted cases={inserted_cases}, regulations={inserted_regs}")
            elif args.backup_only:
                stamp = args.backup_stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_tables(conn, stamp)
            else:
                print("[v2b] dry-run only; no writes")
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"[STOP] {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
