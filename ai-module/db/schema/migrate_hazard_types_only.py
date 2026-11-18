# -*- coding: utf-8 -*-
"""分阶段将 tb_hazard 收敛为只使用中文路径多值字段 hazard_types。

阶段：
  --prepare  备份、回填并校验 hazard_types，然后把旧 hazard_type 改为可空，
             用于新后端上线前消除 NOT NULL 写入冲突。
  --execute  再次备份、校验并执行最终 DDL：删旧索引/旧列、hazard_types NOT NULL、
             创建 idx_types。

默认 dry-run，仅打印计划。
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import pymysql
from db_config import DB_CONFIG

TABLE = "tb_hazard"
VALID_PATHS = {
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
    "消防安全/消防水源异常",
    "建筑安全/危房",
    "建筑安全/墙体开裂/倾斜",
    "建筑安全/外立面脱落",
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


def column_exists(cur, column):
    cur.execute(
        """SELECT COUNT(*) FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s""",
        (TABLE, column),
    )
    return cur.fetchone()[0] > 0


def index_exists(cur, index):
    cur.execute(
        """SELECT COUNT(*) FROM information_schema.STATISTICS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s""",
        (TABLE, index),
    )
    return cur.fetchone()[0] > 0


def backfill_from_legacy(cur):
    if not column_exists(cur, "hazard_type"):
        return
    cur.execute(
        f"UPDATE {TABLE} SET hazard_types = hazard_type "
        "WHERE (hazard_types IS NULL OR TRIM(hazard_types) = '') "
        "AND hazard_type IS NOT NULL AND TRIM(hazard_type) <> ''"
    )


def validate_value(raw):
    if raw is None or raw != raw.strip() or not raw:
        return "空值或首尾空白"
    if "," in raw:
        parts = raw.split(",")
        if any(not item or item != item.strip() for item in parts):
            return f"逗号格式非法: {raw}"
        if len(parts) > 3:
            return f"超过 3 个类别: {raw}"
        if len(parts) != len(set(parts)):
            return f"存在重复类别: {raw}"
    else:
        parts = [raw]
    for item in parts:
        if item not in VALID_PATHS:
            return item
    return None


def validate_rows(cur):
    cur.execute(f"SELECT id, hazard_types FROM {TABLE} ORDER BY id")
    invalid = []
    for row_id, raw in cur.fetchall():
        error = validate_value(raw)
        if error:
            invalid.append((row_id, error))
    if invalid:
        sample = "; ".join(f"id={row_id}:{value}" for row_id, value in invalid[:10])
        raise RuntimeError(f"hazard_types 存在非法分类，迁移中止: {sample}")
    print(f"[OK] hazard_types 校验通过，合法分类 {len(VALID_PATHS)} 个")


def backup_table(cur):
    cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
    total = cur.fetchone()[0]
    backup = f"{TABLE}_bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cur.execute(f"CREATE TABLE {backup} LIKE {TABLE}")
    cur.execute(f"INSERT INTO {backup} SELECT * FROM {TABLE}")
    cur.execute(f"SELECT COUNT(*) FROM {backup}")
    backup_total = cur.fetchone()[0]
    if backup_total != total:
        raise RuntimeError(f"备份行数不一致: expected={total}, actual={backup_total}")
    print(f"[OK] 已备份 {total} 行到 {backup}")
    return backup


def prepare_statements(cur):
    statements = []
    if column_exists(cur, "hazard_type"):
        statements.append(f"ALTER TABLE {TABLE} MODIFY COLUMN hazard_type VARCHAR(64) NULL")
    return statements


def final_statements(cur):
    statements = []
    if index_exists(cur, "idx_type"):
        statements.append(f"ALTER TABLE {TABLE} DROP INDEX idx_type")
    for column in ("hazard_type", "major_category", "subcategory"):
        if column_exists(cur, column):
            statements.append(f"ALTER TABLE {TABLE} DROP COLUMN {column}")
    statements.append(f"ALTER TABLE {TABLE} MODIFY COLUMN hazard_types VARCHAR(255) NOT NULL")
    if not index_exists(cur, "idx_types"):
        statements.append(f"ALTER TABLE {TABLE} ADD INDEX idx_types (hazard_types(64))")
    return statements


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true", help="备份、回填并解除旧列非空约束")
    mode.add_argument("--execute", action="store_true", help="备份并执行最终删列 DDL")
    args = parser.parse_args()

    conn = pymysql.connect(**DB_CONFIG, autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
            print(f"[INFO] {TABLE} 当前 {cur.fetchone()[0]} 行")

            if args.prepare:
                backup_table(cur)
                backfill_from_legacy(cur)
                validate_rows(cur)
                statements = prepare_statements(cur)
            elif args.execute:
                backup_table(cur)
                backfill_from_legacy(cur)
                validate_rows(cur)
                statements = final_statements(cur)
            else:
                validate_rows(cur)
                statements = prepare_statements(cur) + final_statements(cur)

            for statement in statements:
                print(f"[DDL] {statement}")
            if not args.prepare and not args.execute:
                print("[DRY-RUN] 未修改数据库；上线前用 --prepare，最终切换后用 --execute")
                return

            for statement in statements:
                cur.execute(statement)
            conn.commit()
            print(f"[OK] 阶段完成: {'prepare' if args.prepare else 'execute'}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
