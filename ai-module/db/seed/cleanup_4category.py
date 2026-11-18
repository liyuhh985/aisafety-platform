"""清理并统一为 4 类：只保留占道/井盖·道路/消防通道/施工。

步骤（幂等）：
1) UPDATE 保留行的 category 为 4 类名（按 law_name+article / title 定位，不硬编码 id）。
2) DELETE category 不在 4 类的行（清掉电气/燃气/电梯/环境/高空等旧类别）。
3) 去重：法规按 (law_name, article) 保留 min(id)；案例按 title 保留 min(id)。

运行: python db/seed/cleanup_4category.py
（注意：先已备份到 db/backup/）
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import pymysql
from db_config import DB_CONFIG

KEEP4 = ("占道", "井盖/道路", "消防通道", "施工")

# 保留并改标签（法规）：(law_name, article) -> 新category
REG_RELABEL = {
    ("中华人民共和国消防法", "第16条"): "消防通道",
    ("中华人民共和国消防法", "第28条"): "消防通道",
    ("中华人民共和国消防法", "第60条"): "消防通道",
    ("高层民用建筑消防安全管理规定", "第37条"): "消防通道",
    ("GB 50016 建筑设计防火规范", "第5.5.30条"): "消防通道",
    ("中华人民共和国道路交通安全法", "第56条"): "占道",
    ("城市道路管理条例", "第27条"): "占道",
    ("建设工程安全生产管理条例", "第26条"): "施工",
    ("建设工程安全生产管理条例", "第24条"): "施工",
    ("JGJ 80 建筑施工高处作业安全技术规范", "第4.1.1条"): "施工",
    ("JGJ 80 建筑施工高处作业安全技术规范", "第4.1.2条"): "施工",
    ("JGJ 147 建筑拆除工程安全技术规范", "第5.1.1条"): "施工",
    ("中华人民共和国大气污染防治法", "第69条"): "施工",
}

# 保留并改标签（案例）：title -> 新category
CASE_RELABEL = {
    "广东中山废品收购站火灾消防通道被占群众合力挪车": "消防通道",
    "深圳小区地下车库车辆自燃浓烟封堵逃生通道": "消防通道",
    "北京朝阳小区出入口违停堵塞救护车致病人延误救治": "占道",
    "深江铁路地面坍塌重大事故致13死": "施工",
    "本溪工业厂房违规拆除坍塌致3死": "施工",
    "围场钢结构立柱焊接不合格致立柱倒塌1死": "施工",
    "深圳雪花科创城电梯井道脚手架坍塌致1死": "施工",
    "重庆万州检修平台坍塌致1死2伤": "施工",
    "中山翠亨电梯井口防护缺失致工人坠落身亡": "施工",
    "杭州某小区化粪池沼气积聚爆炸致窨井盖飞出伤人": "井盖/道路",
    "郑州某小区污水管破裂地面塌陷致车辆陷入": "井盖/道路",
}


def run():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            # 1) 改标签（法规）
            upd = 0
            for (law, art), cat in REG_RELABEL.items():
                n = cur.execute(
                    "UPDATE tb_regulation SET category=%s WHERE law_name=%s AND article=%s AND category NOT IN (%s,%s,%s,%s)",
                    (cat, law, art, "占道", "井盖/道路", "消防通道", "施工"),
                )
                upd += n
            print(f"[法规] 改标签 {upd} 行")

            # 1) 改标签（案例）
            cupd = 0
            for title, cat in CASE_RELABEL.items():
                n = cur.execute(
                    "UPDATE tb_hazard_case SET category=%s WHERE title=%s AND category NOT IN (%s,%s,%s,%s)",
                    (cat, title, "占道", "井盖/道路", "消防通道", "施工"),
                )
                cupd += n
            print(f"[案例] 改标签 {cupd} 行")

            # 2) 删除非 4 类
            placeholders = ",".join(["%s"] * len(KEEP4))
            cur.execute(
                "DELETE FROM tb_regulation WHERE category NOT IN (" + placeholders + ")",
                KEEP4,
            )
            del_reg = cur.rowcount
            cur.execute(
                "DELETE FROM tb_hazard_case WHERE category NOT IN (" + placeholders + ")",
                KEEP4,
            )
            del_case = cur.rowcount
            print(f"[删除非4类] 法规 {del_reg} 行, 案例 {del_case} 行")

            # 3) 去重：法规 (law_name, article) 保留 min(id)
            cur.execute("""
                DELETE d FROM tb_regulation d
                JOIN (
                    SELECT law_name, article, MIN(id) AS keep_id
                    FROM tb_regulation GROUP BY law_name, article HAVING COUNT(*) > 1
                ) g ON d.law_name = g.law_name AND d.article = g.article AND d.id <> g.keep_id
            """)
            dedup_reg = cur.rowcount
            # 去重：案例 title 保留 min(id)
            cur.execute("""
                DELETE d FROM tb_hazard_case d
                JOIN (
                    SELECT title, MIN(id) AS keep_id
                    FROM tb_hazard_case GROUP BY title HAVING COUNT(*) > 1
                ) g ON d.title = g.title AND d.id <> g.keep_id
            """)
            dedup_case = cur.rowcount
            print(f"[去重] 法规 {dedup_reg} 行, 案例 {dedup_case} 行")

        conn.commit()

        # 汇总
        with conn.cursor() as cur:
            print("--- 处理后法规库分类 ---")
            cur.execute("SELECT category, COUNT(*) FROM tb_regulation GROUP BY category")
            for r in cur.fetchall():
                print(f"   {r[0]} = {r[1]}")
            print("--- 处理后案例库分类 ---")
            cur.execute("SELECT category, COUNT(*) FROM tb_hazard_case GROUP BY category")
            for r in cur.fetchall():
                print(f"   {r[0]} = {r[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
