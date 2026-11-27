"""
安全隐患案例库与法规库第二、三批全量真实权威数据融合导入脚本。
执行内容：
1. 自动备份当前 MySQL 中的 tb_hazard_case 和 tb_regulation 数据；
2. 批量导入 CASES_BATCH_2（40条）与 CASES_BATCH_3（64条），按 title 去重；
3. 批量导入 NEW_REGULATIONS_BATCH_2（56条）与 NEW_REGULATIONS_2026（10条），
   按 (law_name, article, category) 去重（两个批次共用同一份清单、同一套去重逻辑）；
4. 打印两级规范分类完整看板与全库统计信息。
"""
import os
import sys
import io
import json
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pymysql
from db_config import DB_CONFIG
from core.hazard_taxonomy import HAZARD_TAXONOMY
from db.seed.data_cases_batch2 import CASES_BATCH_2
from db.seed.data_cases_batch3 import CASES_BATCH_3
from db.seed.data_cases_v2b import CASES_V2B
from db.seed.data_regulations_batch2 import NEW_REGULATIONS_BATCH_2
from db.seed.data_regulations_batch2026 import NEW_REGULATIONS_2026
from db.seed.data_regulations_v2b import REGULATIONS_V2B

# 合并后的法规导入清单。去重逻辑不变：仍按 (law_name, article, category) 跳过已存在。
# 2026-09-29 并入 batch2026：在那之前它是一个"孤立的数据文件"（全仓没有任何脚本引用它），
# 重建库时会得到不完整的法规数据 —— 而"来源可复现"正是当初把它纳入版本控制的理由。
# 幂等性：并入后在现有库上跑必须得到 0 inserted / 10 skipped（见 db/seed/verify_import_idempotent.py）。
ALL_NEW_REGULATIONS = NEW_REGULATIONS_BATCH_2 + NEW_REGULATIONS_2026 + REGULATIONS_V2B

BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backup")


def backup_current_db(conn):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with conn.cursor() as cur:
        # 备份案例
        cur.execute("SELECT id, category, title, description, severity, city, district, occurrence_date, casualties, cause, rectification, regulation_ref, source_url, verdict, create_time FROM tb_hazard_case")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, [(r.isoformat() if isinstance(r, datetime) else r) for r in row])) for row in cur.fetchall()]
        case_backup_path = os.path.join(BACKUP_DIR, f"tb_hazard_case_backup_{stamp}.json")
        with open(case_backup_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"[备份] 成功备份当前案例库 {len(rows)} 条至: {case_backup_path}")

        # 备份法规
        cur.execute("SELECT id, category, law_name, article, content, keywords, penalty, source_url, create_time FROM tb_regulation")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, [(r.isoformat() if isinstance(r, datetime) else r) for r in row])) for row in cur.fetchall()]
        reg_backup_path = os.path.join(BACKUP_DIR, f"tb_regulation_backup_{stamp}.json")
        with open(reg_backup_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"[备份] 成功备份当前法规库 {len(rows)} 条至: {reg_backup_path}")


def import_cases(cur):
    all_new_cases = CASES_BATCH_2 + CASES_BATCH_3 + CASES_V2B
    print(f"\n[案例导入] 准备导入第二批与第三批案例，共 {len(all_new_cases)} 条...")
    inserted = 0
    skipped = 0

    for case in all_new_cases:
        title = case["title"].strip()
        cur.execute("SELECT id FROM tb_hazard_case WHERE title = %s", (title,))
        if cur.fetchone():
            skipped += 1
            continue

        cur.execute("""
            INSERT INTO tb_hazard_case
            (category, title, description, severity, city, district, occurrence_date, casualties, cause, rectification, regulation_ref, source_url, verdict)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            case["category"],
            title,
            case["description"],
            case.get("severity", "中"),
            case.get("city", "三明市"),
            case.get("district", ""),
            case.get("occurrence_date", ""),
            case.get("casualties", ""),
            case.get("cause", ""),
            case.get("rectification", ""),
            case.get("regulation_ref", ""),
            case.get("source_url", ""),
            case.get("verdict", "")
        ))
        inserted += 1

    print(f"[案例导入] 成功插入新增真实案例: {inserted} 条 (跳过已存在: {skipped} 条)")
    return inserted


def import_regulations(cur):
    print(f"\n[法规导入] 准备导入法规批次（batch2 + batch2026），共 {len(ALL_NEW_REGULATIONS)} 条...")
    inserted = 0
    skipped = 0

    for reg in ALL_NEW_REGULATIONS:
        law_name = reg["law_name"].strip()
        article = reg["article"].strip()
        category = reg["category"].strip()

        cur.execute("SELECT id FROM tb_regulation WHERE law_name = %s AND article = %s AND category = %s", (law_name, article, category))
        if cur.fetchone():
            skipped += 1
            continue

        cur.execute("""
            INSERT INTO tb_regulation
            (category, law_name, article, content, keywords, penalty, source_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            category,
            law_name,
            article,
            reg["content"],
            reg.get("keywords", ""),
            reg.get("penalty", ""),
            reg.get("source_url", "")
        ))
        inserted += 1

    print(f"[法规导入] 成功插入新增真实法规: {inserted} 条 (跳过已存在: {skipped} 条)")
    return inserted


def print_taxonomy_summary(cur):
    print("\n" + "=" * 80)
    print("安全隐患案例库与法规库全量两级规范分类分布看板 (8大领域 / 33个细分类)")
    print("=" * 80)

    cur.execute("SELECT category, count(*) FROM tb_hazard_case GROUP BY category")
    case_counts = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT category, count(*) FROM tb_regulation GROUP BY category")
    reg_counts = {r[0]: r[1] for r in cur.fetchall()}

    total_cases = sum(case_counts.values())
    total_regs = sum(reg_counts.values())

    for item in HAZARD_TAXONOMY:
        major_label = item["label"]
        major_code = item["code"]
        subcats = item["subcategories"]

        major_case_sum = sum(case_counts.get(f"{major_label}/{sub_label}", 0) for _, sub_label in subcats)
        major_reg_sum = sum(reg_counts.get(f"{major_label}/{sub_label}", 0) for _, sub_label in subcats)

        print(f"\n【{major_label}】(代码: {major_code})  总计案例: {major_case_sum} 条 | 总计法规: {major_reg_sum} 条")
        for sub_code, sub_label in subcats:
            full_cat = f"{major_label}/{sub_label}"
            c_cnt = case_counts.get(full_cat, 0)
            r_cnt = reg_counts.get(full_cat, 0)
            print(f"  ├── [{sub_code:24s}] {sub_label:14s} -> 案例: {c_cnt:2d} 条 | 法规: {r_cnt:2d} 条")

    print("\n" + "-" * 80)
    print(f"全库案例总数: {total_cases} 条")
    print(f"全库法规总数: {total_regs} 条")
    print("=" * 80)


def main():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        print(">>> 步骤1: 自动备份现有数据库数据...")
        backup_current_db(conn)

        with conn.cursor() as cur:
            print("\n>>> 步骤2: 批量导入 Batch 2 + Batch 3 权威案例...")
            import_cases(cur)

            print("\n>>> 步骤3: 批量导入 Batch 2 + Batch 2026 权威法规...")
            import_regulations(cur)

            conn.commit()

            print("\n>>> 步骤4: 统计全库最新两级规范分类看板...")
            print_taxonomy_summary(cur)

    except Exception as e:
        conn.rollback()
        print(f"[错误] 导入失败，事务已回滚: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
