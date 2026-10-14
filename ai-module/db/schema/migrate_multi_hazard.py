# -*- coding: utf-8 -*-
"""工单支持"一次上报多个隐患类别"：加 hazard_types 列 + 回填存量。

为什么要新加一列，而不是把 hazard_type 改成多值：
  所有按 major/sub **精确解析**的地方（前端 resolveHazard/matchHazardFilter、详情展示、
  以后任何解析）会同时崩 —— 改一个漏一个。加列是增量、可回滚，存量数据不受影响。

语义（写在一处，避免两套真相）：
  hazard_types = 唯一写入，逗号分隔的 canonical `major/subcategory` 列表，最多 3 条；
  hazard_type  = 主类别，语义不变（= 列表第一项）。

幂等：列已存在就跳过 ALTER；回填只补空值。可重复执行。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymysql
from db_config import DB_CONFIG

COLUMN_DDL = (
    "ALTER TABLE tb_hazard ADD COLUMN hazard_types VARCHAR(255) NULL "
    "COMMENT '全部隐患类别，逗号分隔的 major/sub，最多3条' AFTER hazard_type"
)


def run():
    conn = pymysql.connect(**DB_CONFIG, autocommit=True)
    try:
        with conn.cursor() as cur:
            print("[1/3] 检查 hazard_types 列...")
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE()"
                " AND table_name = 'tb_hazard' AND column_name = 'hazard_types'"
            )
            if cur.fetchone()[0]:
                print("  -> 已存在，跳过 ALTER")
            else:
                cur.execute(COLUMN_DDL)
                print("  -> 已添加 hazard_types VARCHAR(255) NULL")

            print("[2/3] 回填存量（hazard_types = hazard_type）...")
            cur.execute(
                "UPDATE tb_hazard SET hazard_types = hazard_type"
                " WHERE (hazard_types IS NULL OR hazard_types = '')"
                " AND hazard_type IS NOT NULL AND hazard_type <> ''"
            )
            print("  -> 回填行数 =", cur.rowcount)

            print("[3/3] 校验：主类别非空但列表还空的行数...")
            cur.execute(
                "SELECT COUNT(*) FROM tb_hazard WHERE hazard_type IS NOT NULL"
                " AND hazard_type <> '' AND (hazard_types IS NULL OR hazard_types = '')"
            )
            left = cur.fetchone()[0]
            print("  -> 剩余 =", left)
            if left:
                raise SystemExit("回填不完整，请检查")
    finally:
        conn.close()
    print("migrate_multi_hazard: done")


if __name__ == "__main__":
    run()
