"""
对 tb_hazard_case 和 tb_regulation 数据真实性、时效性、完整性进行全景自查审计。
"""
import os
import sys
import io
import pymysql

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_config import DB_CONFIG

conn = pymysql.connect(**DB_CONFIG)
cur = conn.cursor()

# 1. 案例库全景审计
cur.execute("SELECT count(*) FROM tb_hazard_case")
total_cases = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM tb_hazard_case WHERE verdict IS NOT NULL AND verdict != ''")
has_verdict = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM tb_hazard_case WHERE cause IS NOT NULL AND cause != '' AND rectification IS NOT NULL AND rectification != ''")
has_cause_rect = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM tb_hazard_case WHERE source_url IS NOT NULL AND source_url != ''")
has_source = cur.fetchone()[0]

print("=" * 80)
print(f"【案例库真实度与完整性审计】全库总案例: {total_cases} 条")
print(f"  - 具备事故原因(cause)与整改措施(rectification): {has_cause_rect} 条 ({has_cause_rect/total_cases*100:.1f}%)")
print(f"  - 具备法定调查报告处理结果/法院判决/行政处罚(verdict): {has_verdict} 条 ({has_verdict/total_cases*100:.1f}%)")
print(f"  - 具备官方发布源或官方域名引用(source_url): {has_source} 条 ({has_source/total_cases*100:.1f}%)")

print("\n--- 案例发生的城市/地区覆盖（前15） ---")
cur.execute("SELECT city, count(*) FROM tb_hazard_case GROUP BY city ORDER BY count(*) DESC LIMIT 15")
for city, cnt in cur.fetchall():
    print(f"  * {city}: {cnt} 条")

print("\n--- 代表性重大真实事故与司法判例抽检（前10条代表） ---")
cur.execute("SELECT id, title, occurrence_date, city, verdict FROM tb_hazard_case WHERE verdict != '' ORDER BY id DESC LIMIT 10")
for row in cur.fetchall():
    print(f"  * [ID {row[0]}] ({row[2]} {row[3]}) {row[1]}")
    verdict_summary = row[4][:60] + "..." if len(row[4]) > 60 else row[4]
    print(f"    └─ 权威处置/判决: {verdict_summary}")

# 2. 法规库时效性与权威性审计
cur.execute("SELECT count(*) FROM tb_regulation")
total_regs = cur.fetchone()[0]

print("\n" + "=" * 80)
print(f"【法规库现行有效性与完备性审计】全库总法规: {total_regs} 条")

cur.execute("SELECT law_name, count(*) FROM tb_regulation GROUP BY law_name ORDER BY count(*) DESC")
print("--- 涉及的核心法律、行政法规与国家标准清单 ---")
for law, cnt in cur.fetchall():
    print(f"  * {law}: {cnt} 条")

print("\n--- 最新施行法规条款抽检（如无障碍环境建设法、新安法燃气条款、民法典高空抛物等） ---")
sample_laws = [
    "中华人民共和国无障碍环境建设法",
    "中华人民共和国安全生产法",
    "中华人民共和国民法典",
    "中华人民共和国刑法",
    "高层民用建筑消防安全管理规定",
    "工贸企业有限空间作业安全规定",
    "危险性较大的分部分项工程安全管理规定"
]
for law in sample_laws:
    cur.execute("SELECT article, category, content FROM tb_regulation WHERE law_name = %s", (law,))
    rows = cur.fetchall()
    print(f"\n【{law}】(共 {len(rows)} 条)")
    for art, cat, cont in rows[:2]:
        print(f"  - [{art}] 分类: {cat}")
        print(f"    内容摘要: {cont[:70]}...")

conn.close()
