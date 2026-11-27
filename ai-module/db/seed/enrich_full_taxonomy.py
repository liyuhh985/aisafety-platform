"""
安全隐患案例库与法规库全量融合、清洗与扩充脚本。
执行步骤：
1. 自动备份当前 MySQL 库中的 tb_hazard_case 和 tb_regulation 数据；
2. 对现有数据按两级规范分类树（8大类26细分）进行精准重归类；
3. 唤醒并融合 2026-09-07 备份中的高质量历史案例与法规（燃气、电气、电梯、建筑危房、高空坠物等）；
4. 注入针对 26 个细分类全新搜集的全国真实权威案例与法定条文；
5. 全量去重与数据整洁性校验；
6. 输出详细的两级分类统计分布报告。
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
from core.hazard_taxonomy import HAZARD_TAXONOMY, MAJOR_LABELS, SUBCATEGORY_LABELS
from db.seed.data_cases import NEW_CASES
from db.seed.data_regulations import NEW_REGULATIONS

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup")
CASE_BACKUP_FILE = os.path.join(BACKUP_DIR, "tb_hazard_case_20260907_173844.json")
REG_BACKUP_FILE = os.path.join(BACKUP_DIR, "tb_regulation_20260907_173844.json")


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


def align_existing_cases(cur):
    """把现有 60 条案例中的旧标签精细化对应到两级分类。"""
    mappings = [
        # 盲道相关 -> 交通与通行/盲道占用
        ("盲道", "交通与通行/盲道占用"),
        ("人行道", "交通与通行/占道经营/乱堆乱放"),
        ("摆摊", "交通与通行/占道经营/乱堆乱放"),
        ("店外堆物", "交通与通行/占道经营/乱堆乱放"),
        ("临时停车", "交通与通行/车辆占道"),
        ("违停", "交通与通行/车辆占道"),
        ("减速带", "交通与通行/交通设施损坏"),
        ("限高", "交通与通行/交通设施损坏"),
        ("结冰", "交通与通行/交通设施损坏"),
        ("遮挡视线", "交通与通行/交通设施损坏"),
        # 市政相关
        ("井盖", "市政设施/井盖缺失/破损"),
        ("窨井", "市政设施/井盖缺失/破损"),
        ("塌陷", "市政设施/路面塌陷"),
        ("空洞", "市政设施/路面塌陷"),
        ("积水", "市政设施/排水/积水"),
        ("路灯", "市政设施/路灯/线杆损坏"),
        # 消防相关
        ("消防通道", "消防安全/消防通道占用"),
        ("逃生通道", "消防安全/消防通道占用"),
        ("安全出口", "消防安全/消防通道占用"),
        ("消防车通道", "消防安全/消防通道占用"),
        ("防盗网", "消防安全/消防通道占用"),
        ("防盗窗", "消防安全/消防通道占用"),
        ("消火栓", "消防安全/消防设施故障"),
        ("消防栓", "消防安全/消防设施故障"),
        ("灭火器", "消防安全/消防设施故障"),
        # 施工相关
        ("围挡", "施工安全/未设置围挡"),
        ("脚手架", "施工安全/脚手架/临边防护"),
        ("防护缺失", "施工安全/脚手架/临边防护"),
        ("坠落", "施工安全/脚手架/临边防护"),
        ("临时用电", "施工安全/施工临时用电"),
        ("触电", "施工安全/施工临时用电"),
        ("天然气管道", "电气与燃气/燃气管道老化"),
        ("瓦斯", "电气与燃气/燃气泄漏"),
        ("燃气", "电气与燃气/燃气泄漏"),
        ("电梯", "电梯与特种设备/停运/异响"),
    ]
    cur.execute("SELECT id, title, description, category FROM tb_hazard_case")
    all_rows = cur.fetchall()
    updated = 0
    for row_id, title, desc, cat in all_rows:
        text = f"{title} {desc}"
        matched_cat = None
        for keyword, target_cat in mappings:
            if keyword in text:
                matched_cat = target_cat
                break
        if not matched_cat:
            # 兜底转换
            if cat == "占道":
                matched_cat = "交通与通行/占道经营/乱堆乱放"
            elif cat == "井盖/道路":
                matched_cat = "市政设施/井盖缺失/破损"
            elif cat == "消防通道":
                matched_cat = "消防安全/消防通道占用"
            elif cat == "施工":
                matched_cat = "施工安全/未设置围挡"
        if matched_cat and matched_cat != cat:
            cur.execute("UPDATE tb_hazard_case SET category=%s WHERE id=%s", (matched_cat, row_id))
            updated += 1
    print(f"[清洗] 现有案例重新精细归类完成，共更新 {updated} 条。")


def restore_backup_cases(cur):
    """唤醒历史备份中包含的燃气、电气、电梯、建筑危房、环境安全等真实案例。"""
    if not os.path.exists(CASE_BACKUP_FILE):
        print(f"[跳过] 未找到历史案例备份文件: {CASE_BACKUP_FILE}")
        return 0

    with open(CASE_BACKUP_FILE, encoding="utf-8") as f:
        backup_cases = json.load(f)

    # 历史备份案例对应规范分类
    backup_mapping = {
        "重庆29楼电瓶车入户充电致2名邻居死亡": "消防安全/消防通道占用",
        "湖北枣阳楼栋大厅电动车充电起火烧伤租户": "消防安全/消防通道占用",
        "南昌西湖区蓝天雅居电取暖器火灾致4死": "电气与燃气/私拉乱接",
        "河北承德养老院插排短路火灾致20死": "电气与燃气/裸露/老化电线",
        "荣成市北车小区电气线路火灾（较大事故）": "电气与燃气/裸露/老化电线",
        "广东中山废品收购站火灾消防通道被占群众合力挪车": "消防安全/消防通道占用",
        "深江铁路地面坍塌重大事故致13死": "施工安全/深基坑风险",
        "本溪工业厂房违规拆除坍塌致3死": "建筑安全/危房",
        "围场钢结构立柱焊接不合格致立柱倒塌1死": "施工安全/脚手架/临边防护",
        "深圳雪花科创城电梯井道脚手架坍塌致1死": "施工安全/脚手架/临边防护",
        "重庆万州检修平台坍塌致1死2伤": "施工安全/脚手架/临边防护",
        "中山翠亨电梯井口防护缺失致工人坠落身亡": "施工安全/脚手架/临边防护",
        "河北燕郊地埋天然气管道破损爆燃致7死27伤": "电气与燃气/燃气泄漏",
        "辽宁大石桥商铺液化气罐泄漏闪爆致4伤": "电气与燃气/燃气泄漏",
        "哈尔滨香坊区液化气罐操作不当闪爆1死3伤": "电气与燃气/燃气泄漏",
        "沈阳苏家屯居民家中液化气爆燃1死3伤": "电气与燃气/燃气管道老化",
        "河南洛阳居民房煤气爆炸致丈夫92%烧伤后去世": "电气与燃气/燃气泄漏",
        "南京鼓楼区室内燃气泄漏闪爆1死2伤": "电气与燃气/燃气泄漏",
        "湖南永州老旧居民楼电表箱线路老化短路起火": "电气与燃气/配电设施故障",
        "西安长安区电梯箱维修电气线路短路引发火灾": "电气与燃气/配电设施故障",
        "福建古田老旧移民房线路绝缘层老化多次起火": "电气与燃气/裸露/老化电线",
        "广东佛山民房电线老化短路引燃杂物": "电气与燃气/裸露/老化电线",
        "贵州某市客厅空调内机电线短路引发火灾": "电气与燃气/裸露/老化电线",
        "杭州某小区插座电气线路故障引燃沙发": "电气与燃气/配电设施故障",
        "长春南关区电梯拆除主吊钩脱落致1死2伤": "电梯与特种设备/停运/异响",
        "太原万柏林电梯安装工从28层坠至负二层身亡": "施工安全/脚手架/临边防护",
        "湘潭县电梯拆除轿厢突然下坠致1死": "电梯与特种设备/停运/异响",
        "梅州家用电梯维保挤压致死1人": "电梯与特种设备/超期未检",
        "中国农业大学中控员误入电梯井道坠落身亡": "电梯与特种设备/超期未检",
        "上海嘉定南翔印象城维保工坠落井道身亡": "电梯与特种设备/超期未检",
        "深圳小区地下车库车辆自燃浓烟封堵逃生通道": "消防安全/消防通道占用",
        "北京朝阳小区出入口违停堵塞救护车致病人延误救治": "交通与通行/车辆占道",
        "重庆江北区货车闯入限高老旧小区刮断多根电线": "交通与通行/交通设施损坏",
        "海口小区内未设减速带老人被快递三轮车撞伤": "交通与通行/交通设施损坏",
        "武汉小区停车场出入口视线遮挡致儿童被撞": "交通与通行/交通设施损坏",
        "西安小区地库出入口坡道结冰致多车追尾": "交通与通行/交通设施损坏",
        "杭州某小区化粪池沼气积聚爆炸致窨井盖飞出伤人": "市政设施/井盖缺失/破损",
        "广州某小区二次供水水箱未清洗致居民集体腹泻": "环境与其他/其他",
        "南京某小区外墙瓷砖大面积脱落砸坏多辆汽车": "建筑安全/高空坠物",
        "武汉某小区建筑垃圾临时堆放点粉尘噪音扰民": "环境与其他/垃圾堆积",
        "成都某小区餐饮底商油烟管道泄漏致居民长期投诉": "环境与其他/污水/异味",
        "郑州某小区污水管破裂地面塌陷致车辆陷入": "市政设施/路面塌陷",
        "重庆巴南商业体擅自改造人行道损毁盲道被提起行政公益诉讼": "交通与通行/盲道占用",
        "上海城管依法处置电动车与摊贩占用盲道行为": "交通与通行/盲道占用",
        "文昌市某路段井盖缺损 电动自行车摔倒骨折 道路管理部门担责": "市政设施/井盖缺失/破损",
        "社旗县井盖缺失伤人 镇政府担责30% 农村公路养护中心担责40%": "市政设施/井盖缺失/破损",
        "重庆行人掉落破损窨井致十级伤残 供电公司担责90%": "市政设施/井盖缺失/破损",
        "河南柘城震兴武馆火灾18死11伤 逃生通道不符合要求": "消防安全/消防通道占用",
        "萍乡小区火灾5辆私家车占用消防车通道 5名车主各罚200元": "消防安全/消防通道占用",
        "湖北宜昌某酒店封堵安全出口被罚6010元": "消防安全/消防通道占用",
        "许昌魏都区路坑一侧未设围挡 电动车坠落九级伤残 施工方担责40%": "施工安全/未设置围挡",
        "句容施工入口设警示但未围挡 致人死亡 施工方担责": "施工安全/未设置围挡",
        "南召县施工现场不封闭致5岁男孩受伤 施工队与房主赔偿": "施工安全/未设置围挡",
    }

    inserted = 0
    for case in backup_cases:
        title = case["title"].strip()
        # 查重
        cur.execute("SELECT id FROM tb_hazard_case WHERE title = %s", (title,))
        exist = cur.fetchone()
        canonical_cat = backup_mapping.get(title, "环境与其他/其他")
        if not exist:
            cur.execute("""
                INSERT INTO tb_hazard_case
                (category, title, description, severity, city, district, occurrence_date, casualties, cause, rectification, regulation_ref, source_url, verdict)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                canonical_cat,
                title,
                case.get("description", ""),
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
        else:
            # 更新已有案例的 category
            cur.execute("UPDATE tb_hazard_case SET category=%s WHERE id=%s", (canonical_cat, exist[0]))

    print(f"[唤醒] 成功从历史备份唤醒并导入 {inserted} 条被删案例。")
    return inserted


def insert_new_cases(cur):
    """注入全新补充的 26 个细分类全国真实权威案例。"""
    inserted = 0
    for case in NEW_CASES:
        title = case["title"].strip()
        cur.execute("SELECT id FROM tb_hazard_case WHERE title = %s", (title,))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO tb_hazard_case
                (category, title, description, severity, city, district, occurrence_date, casualties, cause, rectification, regulation_ref, source_url, verdict)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                case["category"],
                title,
                case["description"],
                case["severity"],
                case["city"],
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
        else:
            # 确保 category 是规范值
            cur.execute("UPDATE tb_hazard_case SET category=%s WHERE title=%s", (case["category"], title))
    print(f"[补充] 成功录入全新搜集的全国真实典型事故案例 {inserted} 条。")
    return inserted


def enrich_regulations(cur):
    """全量规范化并扩充法规库。"""
    # 1. 唤醒历史备份中的法规
    restored = 0
    if os.path.exists(REG_BACKUP_FILE):
        with open(REG_BACKUP_FILE, encoding="utf-8") as f:
            backup_regs = json.load(f)
        for r in backup_regs:
            law = r.get("law_name", "").strip()
            art = r.get("article", "").strip()
            cat = r.get("category", "").strip()
            # 映射为两级
            if cat == "消防安全":
                cat = "消防安全/消防设施故障"
            elif cat == "建筑施工":
                cat = "施工安全/脚手架/临边防护"
            elif cat == "电气安全":
                cat = "电气与燃气/裸露/老化电线"
            elif cat == "燃气安全":
                cat = "电气与燃气/燃气泄漏"
            elif cat == "电梯安全":
                cat = "电梯与特种设备/电梯困人"
            elif cat == "交通安全":
                cat = "交通与通行/占道经营/乱堆乱放"
            elif cat == "环境安全":
                cat = "环境与其他/污水/异味"
            elif cat == "占道":
                cat = "交通与通行/占道经营/乱堆乱放"
            elif cat == "井盖/道路":
                cat = "市政设施/井盖缺失/破损"
            elif cat == "消防通道":
                cat = "消防安全/消防通道占用"
            elif cat == "施工":
                cat = "施工安全/未设置围挡"

            cur.execute("SELECT id FROM tb_regulation WHERE law_name=%s AND article=%s", (law, art))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO tb_regulation (category, law_name, article, content, keywords, penalty, source_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    cat, law, art,
                    r.get("content", ""),
                    r.get("keywords", f"{law} {art}"),
                    r.get("penalty", ""),
                    r.get("source_url", "")
                ))
                restored += 1
    print(f"[法规唤醒] 成功从历史备份唤醒并导入法规 {restored} 条。")

    # 2. 插入新扩充的法规条文
    new_reg_count = 0
    for r in NEW_REGULATIONS:
        law = r["law_name"].strip()
        art = r["article"].strip()
        cur.execute("SELECT id FROM tb_regulation WHERE law_name=%s AND article=%s", (law, art))
        exist = cur.fetchone()
        if not exist:
            cur.execute("""
                INSERT INTO tb_regulation (category, law_name, article, content, keywords, penalty, source_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                r["category"], law, art, r["content"], r["keywords"],
                r.get("penalty", ""), r.get("source_url", "")
            ))
            new_reg_count += 1
        else:
            # 增强已有的 keywords 和 category
            cur.execute("""
                UPDATE tb_regulation
                SET category=%s, keywords=CONCAT(keywords, ' ', %s), penalty=%s
                WHERE id=%s
            """, (r["category"], r["keywords"], r.get("penalty", ""), exist[0]))

    # 将所有残存的旧单层标签升级为规范两级标签
    cur.execute("UPDATE tb_regulation SET category='交通与通行/占道经营/乱堆乱放' WHERE category='占道'")
    cur.execute("UPDATE tb_regulation SET category='市政设施/井盖缺失/破损' WHERE category='井盖/道路'")
    cur.execute("UPDATE tb_regulation SET category='消防安全/消防通道占用' WHERE category='消防通道'")
    cur.execute("UPDATE tb_regulation SET category='施工安全/未设置围挡' WHERE category='施工'")
    print(f"[法规补充] 成功录入/更新全新权威法律法规条款 {new_reg_count} 条，并全部规范为两级分类。")


def verify_and_print_summary(conn):
    """输出最终的案例与法规分类统计看板。"""
    with conn.cursor() as cur:
        cur.execute("SELECT category, count(*) FROM tb_hazard_case GROUP BY category ORDER BY count(*) DESC")
        case_stats = cur.fetchall()

        cur.execute("SELECT count(*) FROM tb_hazard_case")
        total_cases = cur.fetchone()[0]

        cur.execute("SELECT category, count(*) FROM tb_regulation GROUP BY category ORDER BY count(*) DESC")
        reg_stats = cur.fetchall()

        cur.execute("SELECT count(*) FROM tb_regulation")
        total_regs = cur.fetchone()[0]

    print("\n" + "=" * 60)
    print(f"安全隐患数据库全量扩充完成！")
    print(f"案例库 (tb_hazard_case) 当前总条数: {total_cases} 条")
    print(f"法规库 (tb_regulation) 当前总条数: {total_regs} 条")
    print("=" * 60)

    print("\n--- 案例库各细分类别分布 ---")
    for cat, cnt in case_stats:
        print(f"  * {cat:<25}: {cnt:>3} 条")

    print("\n--- 法规库各细分类别分布 ---")
    for cat, cnt in reg_stats:
        print(f"  * {cat:<25}: {cnt:>3} 条")
    print("=" * 60)


def main():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        print(">>> 步骤 1: 备份当前数据库...")
        backup_current_db(conn)

        with conn.cursor() as cur:
            print("\n>>> 步骤 2: 清洗现有案例，精细对齐到两级分类...")
            align_existing_cases(cur)

            print("\n>>> 步骤 3: 唤醒并融合历史备份中的真实案例...")
            restore_backup_cases(cur)

            print("\n>>> 步骤 4: 录入全新搜集的 26 个细分类典型事故案例...")
            insert_new_cases(cur)

            print("\n>>> 步骤 5: 全面恢复与扩充法律法规库...")
            enrich_regulations(cur)

        conn.commit()

        print("\n>>> 步骤 6: 校验与生成统计分析报告...")
        verify_and_print_summary(conn)

    except Exception as e:
        conn.rollback()
        print(f"执行出错，已回滚事务: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
