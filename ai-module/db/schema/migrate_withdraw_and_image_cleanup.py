# -*- coding: utf-8 -*-
"""迁移：撤回字段 + image_key(+回填) + 对象清理 outbox 表。

幂等：每步先探测再改，可重复执行。执行： python db/schema/migrate_withdraw_and_image_cleanup.py
上游 spec：私有历史设计文档
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import pymysql
from pymysql.constants import CLIENT
from db_config import DB_CONFIG

BAK = "bak_20260929"

DDL_OUTBOX = """
CREATE TABLE IF NOT EXISTS tb_resource_cleanup_outbox (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    target          VARCHAR(16)   NOT NULL COMMENT '外部资源类型，目前只有 MINIO',
    ref_id          BIGINT        NULL     COMMENT '来源记录 id（例如报告 id）',
    source_table    VARCHAR(64)   NULL     COMMENT '来源表名',
    bucket          VARCHAR(64)   NULL     COMMENT '对象存储桶',
    object_key      VARCHAR(255)  NULL     COMMENT '对象 key',
    status          VARCHAR(20)   NOT NULL COMMENT 'PENDING/RETRY/PROCESSING/SUCCEEDED/FAILED',
    claim_version   INT           NOT NULL DEFAULT 0,
    retry_count     INT           NOT NULL DEFAULT 0,
    next_retry_time DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at       DATETIME      NULL,
    last_error      VARCHAR(1000) NULL,
    create_time     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_resource_cleanup_due (status, next_retry_time),
    INDEX idx_resource_cleanup_stale (status, locked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def col_exists(cur, table, col):
    cur.execute("SHOW COLUMNS FROM %s LIKE %%s" % table, (col,))
    return cur.fetchone() is not None


def table_exists(cur, table):
    cur.execute("SHOW TABLES LIKE %s", (table,))
    return cur.fetchone() is not None


def add_col(cur, table, col, ddl):
    if col_exists(cur, table, col):
        print("  -> %s.%s 已存在，跳过" % (table, col))
        return False
    cur.execute("ALTER TABLE %s ADD COLUMN %s" % (table, ddl))
    print("  -> 已添加 %s.%s" % (table, col))
    return True


def main():
    conn = pymysql.connect(**DB_CONFIG, client_flag=CLIENT.MULTI_STATEMENTS, autocommit=False)
    changed = []
    try:
        with conn.cursor() as cur:
            # ---- 0. 备份（只做一次，避免覆盖改动前的快照）----
            for t in ("tb_hazard", "tb_hazard_report"):
                bak = "%s_%s" % (t, BAK)
                if table_exists(cur, bak):
                    print("[0] %s 备份已存在，跳过" % bak)
                else:
                    cur.execute("CREATE TABLE %s AS SELECT * FROM %s" % (bak, t))
                    cur.execute("SELECT COUNT(*) FROM %s" % bak)
                    print("[0] 已备份 %s -> %s（%d 行）" % (t, bak, cur.fetchone()[0]))
                    changed.append("backup:" + bak)

            # ---- 1. 撤回字段 ----
            print("[1] tb_hazard 加撤回字段")
            if add_col(cur, "tb_hazard", "withdrawn_at", "withdrawn_at DATETIME NULL COMMENT '撤回时间'"):
                changed.append("tb_hazard.withdrawn_at")
            if add_col(cur, "tb_hazard", "withdrawn_by", "withdrawn_by BIGINT NULL COMMENT '撤回人 userId'"):
                changed.append("tb_hazard.withdrawn_by")

            # ---- 2. image_key ----
            print("[2] tb_hazard_report 加 image_key")
            if add_col(cur, "tb_hazard_report", "image_key",
                       "image_key VARCHAR(128) NULL COMMENT 'MinIO 对象 key'"):
                changed.append("tb_hazard_report.image_key")

            # ---- 3. 回填 image_key（能填多少填多少）----
            cur.execute("""SELECT COUNT(*) FROM tb_hazard_report
                           WHERE image_key IS NULL AND image_url IS NOT NULL AND image_url <> ''""")
            before = cur.fetchone()[0]
            if before:
                cur.execute("""UPDATE tb_hazard_report
                                  SET image_key = SUBSTRING_INDEX(image_url, '/', -1)
                                WHERE image_key IS NULL
                                  AND image_url IS NOT NULL AND image_url <> ''
                                  AND image_url LIKE '%/%'""")
                filled = cur.rowcount
                cur.execute("""SELECT COUNT(*) FROM tb_hazard_report
                               WHERE image_key IS NULL AND image_url IS NOT NULL AND image_url <> ''""")
                left = cur.fetchone()[0]
                print("[3] 回填 image_key：本次填 %d 条，剩余无法解析 %d 条（原待回填 %d）"
                      % (filled, left, before))
                changed.append("backfill:%d" % filled)
            else:
                print("[3] 无需回填（image_key 已齐或没有 image_url）")

            # ---- 4. 对象清理 outbox 表 ----
            print("[4] 建 tb_resource_cleanup_outbox")
            existed = table_exists(cur, "tb_resource_cleanup_outbox")
            cur.execute(DDL_OUTBOX)
            print("  -> %s" % ("已存在，跳过" if existed else "已创建"))
            if not existed:
                changed.append("create:tb_resource_cleanup_outbox")

        conn.commit()
        print("\n=== 迁移完成，变更项 %d 个 ===" % len(changed))
        for c in changed:
            print("  · %s" % c)

        # 复核
        with conn.cursor() as cur:
            for t, cols in (("tb_hazard", ("withdrawn_at", "withdrawn_by")),
                            ("tb_hazard_report", ("image_key",))):
                cur.execute("SHOW COLUMNS FROM %s" % t)
                have = [r[0] for r in cur.fetchall()]
                print("复核 %s：%s" % (t, {c: (c in have) for c in cols}))
            cur.execute("SELECT COUNT(*) FROM tb_hazard_report WHERE image_key IS NOT NULL")
            print("复核 image_key 非空条数 = %d" % cur.fetchone()[0])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
