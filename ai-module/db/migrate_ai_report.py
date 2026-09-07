"""迁移 tb_hazard：放宽 image_url/经度/纬度，加 category/district/report 列 + 索引。幂等。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymysql
from db_config import DB_CONFIG


def column_info(cur, table, col):
    cur.execute("""
        SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_TYPE FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s
    """, (table, col))
    return cur.fetchone()


def has_index(cur, table, idx):
    cur.execute("""
        SELECT INDEX_NAME FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s
    """, (table, idx))
    return cur.fetchone() is not None


def run():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            # 1) image_url 可空
            if column_info(cur, 'tb_hazard', 'image_url'):
                if column_info(cur, 'tb_hazard', 'image_url')[1] == 'NO':
                    cur.execute("ALTER TABLE tb_hazard MODIFY image_url VARCHAR(500) NULL")
                    print("image_url -> NULL")
            # 2) longitude/latitude 可空
            for col in ('longitude', 'latitude'):
                ci = column_info(cur, 'tb_hazard', col)
                if ci and ci[1] == 'NO':
                    cur.execute(f"ALTER TABLE tb_hazard MODIFY {col} DECIMAL(10,7) NULL")
                    print(f"{col} -> NULL")
            # 3) 加 category/district/report
            for col, ddl in [
                ('category', "ADD COLUMN category VARCHAR(30) DEFAULT '' COMMENT '隐患类别(占道/井盖道路/消防通道/施工)'"),
                ('district', "ADD COLUMN district VARCHAR(50) DEFAULT '' COMMENT '行政区'"),
                ('report', "ADD COLUMN report TEXT NULL COMMENT 'AI报告全文'"),
            ]:
                if not column_info(cur, 'tb_hazard', col):
                    cur.execute(f"ALTER TABLE tb_hazard {ddl}")
                    print(f"ADD COLUMN {col}")
            # 4) 索引
            for idx, ddl in [
                ('idx_category', "ADD INDEX idx_category (category)"),
                ('idx_status', "ADD INDEX idx_status (status)"),
            ]:
                if not has_index(cur, 'tb_hazard', idx):
                    cur.execute(f"ALTER TABLE tb_hazard {ddl}")
                    print(f"ADD INDEX {idx}")
        conn.commit()
        # 验证
        with conn.cursor() as cur:
            cur.execute("SHOW COLUMNS FROM tb_hazard")
            print("--- tb_hazard 列 ---")
            for r in cur.fetchall():
                print(f"   {r[0]:<12} {r[1]:<18} NULL={'YES' if r[2].upper()=='YES' else 'NO'}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
