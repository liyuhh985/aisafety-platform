# -*- coding: utf-8 -*-
"""MinIO 文件元数据表与安全可见性迁移（幂等）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import pymysql
from db_config import DB_CONFIG

DDL = """
CREATE TABLE IF NOT EXISTS tb_file_asset (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT       NOT NULL,
    bucket          VARCHAR(64)  NOT NULL,
    object_key      VARCHAR(255) NOT NULL,
    original_name   VARCHAR(255) NULL,
    content_type    VARCHAR(64)  NOT NULL,
    size_bytes      BIGINT       NOT NULL,
    status          VARCHAR(16)  NOT NULL COMMENT 'TEMP/ATTACHED/DELETING',
    visibility      VARCHAR(16)  NOT NULL DEFAULT 'AUTHENTICATED' COMMENT 'AUTHENTICATED/PRIVATE',
    claim_token     VARCHAR(64)  NULL,
    expires_at      DATETIME     NULL,
    create_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_file_asset_object_key (object_key),
    KEY idx_file_asset_user_status (user_id, status),
    KEY idx_file_asset_expiry (status, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

COLUMNS = {
    "visibility": "ALTER TABLE tb_file_asset ADD COLUMN visibility VARCHAR(16) NOT NULL DEFAULT 'AUTHENTICATED' COMMENT 'AUTHENTICATED/PRIVATE' AFTER status",
    "claim_token": "ALTER TABLE tb_file_asset ADD COLUMN claim_token VARCHAR(64) NULL AFTER visibility",
}


def column_exists(cur, column):
    cur.execute(
        """SELECT COUNT(*) FROM information_schema.COLUMNS
           WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tb_file_asset' AND COLUMN_NAME = %s""",
        (column,),
    )
    return cur.fetchone()[0] > 0


def main():
    conn = pymysql.connect(**DB_CONFIG, autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
            for name, ddl in COLUMNS.items():
                if not column_exists(cur, name):
                    cur.execute(ddl)

            # 旧报告图片是 owner/admin 私有，先补元数据再改写业务 URL。
            cur.execute("""
                INSERT INTO tb_file_asset
                    (user_id, bucket, object_key, original_name, content_type,
                     size_bytes, status, visibility, expires_at)
                SELECT r.user_id, 'safety-images',
                       COALESCE(NULLIF(r.image_key, ''),
                                SUBSTRING_INDEX(SUBSTRING_INDEX(r.image_url, '?', 1), '/', -1)),
                       COALESCE(NULLIF(r.image_key, ''),
                                SUBSTRING_INDEX(SUBSTRING_INDEX(r.image_url, '?', 1), '/', -1)),
                       CASE
                         WHEN r.image_url LIKE '%.png%' THEN 'image/png'
                         WHEN r.image_url LIKE '%.gif%' THEN 'image/gif'
                         ELSE 'image/jpeg'
                       END,
                       0, 'ATTACHED', 'PRIVATE', NULL
                FROM tb_hazard_report r
                WHERE (r.image_key IS NOT NULL AND r.image_key <> '')
                   OR r.image_url LIKE '%/safety-images/%'
                ON DUPLICATE KEY UPDATE
                    status = 'ATTACHED', visibility = 'PRIVATE', expires_at = NULL
            """)
            cur.execute("""
                UPDATE tb_hazard_report r
                JOIN tb_file_asset f
                  ON f.object_key = COALESCE(
                       NULLIF(r.image_key, ''),
                       SUBSTRING_INDEX(SUBSTRING_INDEX(r.image_url, '?', 1), '/', -1)
                     )
                SET r.image_url = CONCAT('/api/files/', f.id)
                WHERE (r.image_key IS NOT NULL AND r.image_key <> '')
                   OR r.image_url LIKE '%/safety-images/%'
            """)

            # 隐患图片按当前产品边界允许所有登录用户查看。
            cur.execute("""
                INSERT INTO tb_file_asset
                    (user_id, bucket, object_key, original_name, content_type,
                     size_bytes, status, visibility, expires_at)
                SELECT h.user_id, 'safety-images',
                       SUBSTRING_INDEX(SUBSTRING_INDEX(h.image_url, '?', 1), '/', -1),
                       SUBSTRING_INDEX(SUBSTRING_INDEX(h.image_url, '?', 1), '/', -1),
                       CASE
                         WHEN h.image_url LIKE '%.png%' THEN 'image/png'
                         WHEN h.image_url LIKE '%.gif%' THEN 'image/gif'
                         ELSE 'image/jpeg'
                       END,
                       0, 'ATTACHED', 'AUTHENTICATED', NULL
                FROM tb_hazard h
                WHERE h.image_url LIKE '%/safety-images/%'
                ON DUPLICATE KEY UPDATE
                    status = 'ATTACHED', visibility = 'AUTHENTICATED', expires_at = NULL
            """)
            cur.execute("""
                UPDATE tb_hazard h
                JOIN tb_file_asset f
                  ON f.object_key = SUBSTRING_INDEX(SUBSTRING_INDEX(h.image_url, '?', 1), '/', -1)
                SET h.image_url = CONCAT('/api/files/', f.id)
                WHERE h.image_url LIKE '%/safety-images/%'
            """)

            cur.execute("SHOW COLUMNS FROM tb_file_asset")
            columns = {row[0] for row in cur.fetchall()}
            print("tb_file_asset columns=%s" % sorted(columns))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()

