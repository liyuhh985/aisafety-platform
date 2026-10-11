# -*- coding: utf-8 -*-
"""迁移：AI 建任务 request / outbox 归档表。

幂等：CREATE TABLE IF NOT EXISTS ... LIKE ...，可重复执行。
执行： python db/migrate_hazard_create_archive.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql

from db_config import DB_CONFIG

DDL_REQUEST_ARCHIVE = (
    "CREATE TABLE IF NOT EXISTS ai_hazard_create_request_archive "
    "LIKE ai_hazard_create_request"
)
DDL_OUTBOX_ARCHIVE = (
    "CREATE TABLE IF NOT EXISTS ai_hazard_create_outbox_archive "
    "LIKE ai_hazard_create_outbox"
)


def table_exists(cur, table):
    cur.execute("SHOW TABLES LIKE %s", (table,))
    return cur.fetchone() is not None


def main():
    conn = pymysql.connect(**DB_CONFIG, autocommit=False)
    changed = []
    try:
        with conn.cursor() as cur:
            for table, ddl in (
                ("ai_hazard_create_request_archive", DDL_REQUEST_ARCHIVE),
                ("ai_hazard_create_outbox_archive", DDL_OUTBOX_ARCHIVE),
            ):
                existed = table_exists(cur, table)
                cur.execute(ddl)
                if not existed:
                    changed.append(table)
        conn.commit()
        print("=== archive migration done, changed=%s ===" % changed)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
