# -*- coding: utf-8 -*-
"""迁移：为管理员撤回记录原因。

幂等：先探测列是否存在。执行：python db/schema/migrate_admin_withdraw_reason.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import pymysql
from db_config import DB_CONFIG


def col_exists(cur, table, col):
    cur.execute("SHOW COLUMNS FROM %s LIKE %%s" % table, (col,))
    return cur.fetchone() is not None


def main():
    conn = pymysql.connect(**DB_CONFIG, autocommit=False)
    try:
        with conn.cursor() as cur:
            if col_exists(cur, "tb_hazard", "withdrawn_reason"):
                print("[1] tb_hazard.withdrawn_reason 已存在，跳过")
            else:
                cur.execute(
                    "ALTER TABLE tb_hazard ADD COLUMN "
                    "withdrawn_reason VARCHAR(500) NULL COMMENT '撤回原因' AFTER withdrawn_by"
                )
                print("[1] 已添加 tb_hazard.withdrawn_reason")
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM tb_hazard LIKE 'withdrawn_reason'")
            row = cur.fetchone()
            print("[verify] withdrawn_reason=%s" % (row is not None))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
