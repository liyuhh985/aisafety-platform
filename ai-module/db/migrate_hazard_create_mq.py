# -*- coding: utf-8 -*-
"""迁移：AI 建任务 MQ + Outbox（Python 侧状态表/outbox + Java 侧 tb_hazard.request_id）。

幂等：每步先探测再改，可重复执行。
执行： python db/migrate_hazard_create_mq.py
上游设计：docs/current/ai-hazard-create-mq.md
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymysql
from pymysql.constants import CLIENT
from db_config import DB_CONFIG

BAK = "bak_20261010"
REQUEST_TABLE = "ai_hazard_create_request"
OUTBOX_TABLE = "ai_hazard_create_outbox"
UNIQUE_INDEX = "uk_tb_hazard_request_id"

DDL_REQUEST = """
CREATE TABLE IF NOT EXISTS ai_hazard_create_request (
    request_id    VARCHAR(64)  NOT NULL COMMENT '请求 id（幂等主体）',
    user_id       BIGINT       NOT NULL COMMENT '上报用户',
    session_id    VARCHAR(128) NULL     COMMENT '会话 id（观测用）',
    payload       MEDIUMTEXT   NULL     COMMENT '建单 payload（JSON 文本）',
    status        VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                  COMMENT 'PENDING/PUBLISHED/SUCCESS/FAILED',
    hazard_id     BIGINT       NULL     COMMENT '成功后由 Java 回执带回',
    error_message VARCHAR(1000) NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (request_id),
    INDEX idx_ai_hazard_req_user (user_id, created_at),
    INDEX idx_ai_hazard_req_status (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI 建任务请求（Python 侧唯一写入）'
"""

DDL_OUTBOX = """
CREATE TABLE IF NOT EXISTS ai_hazard_create_outbox (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    request_id      VARCHAR(64)  NOT NULL COMMENT '对应的建单请求',
    event_type      VARCHAR(64)  NOT NULL DEFAULT 'HAZARD_CREATE_REQUESTED',
    payload         MEDIUMTEXT   NULL     COMMENT '投递到 MQ 的消息体（JSON 文本）',
    status          VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                    COMMENT 'PENDING/PUBLISHED/RETRY/FAILED',
    retry_count     INT          NOT NULL DEFAULT 0,
    next_retry_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at       DATETIME     NULL,
    last_error      VARCHAR(1000) NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_ai_hazard_outbox_request (request_id),
    INDEX idx_ai_hazard_outbox_due (status, next_retry_time),
    INDEX idx_ai_hazard_outbox_stale (status, locked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI 建任务 Outbox（Relay 扫描投递）'
"""


def table_exists(cur, table):
    cur.execute("SHOW TABLES LIKE %s", (table,))
    return cur.fetchone() is not None


def col_exists(cur, table, col):
    cur.execute("SHOW COLUMNS FROM %s LIKE %%s" % table, (col,))
    return cur.fetchone() is not None


def index_exists(cur, table, index):
    cur.execute(
        "SELECT 1 FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s LIMIT 1",
        (table, index),
    )
    return cur.fetchone() is not None


def main():
    conn = pymysql.connect(**DB_CONFIG, client_flag=CLIENT.MULTI_STATEMENTS, autocommit=False)
    changed = []
    try:
        with conn.cursor() as cur:
            # ---- 0. 备份 tb_hazard（只做一次）----
            bak = "tb_hazard_%s" % BAK
            if table_exists(cur, bak):
                print("[0] %s 备份已存在，跳过" % bak)
            else:
                cur.execute("CREATE TABLE %s AS SELECT * FROM tb_hazard" % bak)
                cur.execute("SELECT COUNT(*) FROM %s" % bak)
                print("[0] 已备份 tb_hazard -> %s（%d 行）" % (bak, cur.fetchone()[0]))
                changed.append("backup:" + bak)

            # ---- 1. tb_hazard.request_id ----
            print("[1] tb_hazard 加 request_id")
            if col_exists(cur, "tb_hazard", "request_id"):
                print("  -> tb_hazard.request_id 已存在，跳过")
            else:
                cur.execute(
                    "ALTER TABLE tb_hazard ADD COLUMN request_id VARCHAR(64) NULL "
                    "COMMENT 'AI 建任务请求 id（幂等键，唯一）'"
                )
                print("  -> 已添加 tb_hazard.request_id")
                changed.append("tb_hazard.request_id")

            # ---- 2. tb_hazard.request_id 唯一索引 ----
            print("[2] tb_hazard 加唯一索引 %s" % UNIQUE_INDEX)
            if index_exists(cur, "tb_hazard", UNIQUE_INDEX):
                print("  -> 唯一索引已存在，跳过")
            else:
                cur.execute(
                    "ALTER TABLE tb_hazard ADD UNIQUE INDEX %s (request_id)" % UNIQUE_INDEX
                )
                print("  -> 已添加唯一索引（MySQL 唯一索引允许多个 NULL，存量行不受影响）")
                changed.append("index:" + UNIQUE_INDEX)

            # ---- 3. ai_hazard_create_request ----
            print("[3] 建 %s" % REQUEST_TABLE)
            existed = table_exists(cur, REQUEST_TABLE)
            cur.execute(DDL_REQUEST)
            print("  -> %s" % ("已存在，跳过" if existed else "已创建"))
            if not existed:
                changed.append("create:" + REQUEST_TABLE)

            # ---- 4. ai_hazard_create_outbox ----
            print("[4] 建 %s" % OUTBOX_TABLE)
            existed = table_exists(cur, OUTBOX_TABLE)
            cur.execute(DDL_OUTBOX)
            print("  -> %s" % ("已存在，跳过" if existed else "已创建"))
            if not existed:
                changed.append("create:" + OUTBOX_TABLE)

        conn.commit()
        print("\n=== 迁移完成，变更项 %d 个 ===" % len(changed))
        for item in changed:
            print("  · %s" % item)

        # ---- 复核 ----
        with conn.cursor() as cur:
            print("\n复核：")
            print("  tb_hazard.request_id           = %s" % col_exists(cur, "tb_hazard", "request_id"))
            print("  tb_hazard.%s        = %s" % (UNIQUE_INDEX, index_exists(cur, "tb_hazard", UNIQUE_INDEX)))
            print("  %s           = %s" % (REQUEST_TABLE, table_exists(cur, REQUEST_TABLE)))
            print("  %s            = %s" % (OUTBOX_TABLE, table_exists(cur, OUTBOX_TABLE)))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()