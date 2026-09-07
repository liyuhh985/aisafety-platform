"""补充法规：占道+1、井盖/道路+1、消防通道+2（真实官方来源）。只插入不存在的 (category,law_name,article)。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymysql
from db_config import DB_CONFIG

REGULATIONS = [
    ("井盖/道路", "城市道路管理条例", "第42条",
     "违反本条例第二十七条规定，或者有下列行为之一的，由市政工程行政主管部门或者其他有关部门责令限期改正，可以处以2万元以下的罚款；造成损失的，应当依法承担赔偿责任：（一）未对设在城市道路上的各种管线的检查井、箱盖或者城市道路附属设施的缺损及时补缺或者修复的；（二）未在城市道路施工现场设置明显标志和安全防围设施的；（三）占用城市道路期满或者挖掘城市道路后，不及时清理现场的；（四）依附于城市道路建设各种管线、杆线等设施，不按照规定办理批准手续的；（五）紧急抢修埋设在城市道路下的管线，不按照规定补办批准手续的；（六）未按照批准的位置、面积、期限占用或者挖掘城市道路，或者需要移动位置、扩大面积、延长时间，未提前办理变更审批手续的。",
     "城市道路 检查井 箱盖 缺损 占道 挖掘 罚则 围挡",
     "责令限期改正，可处以2万元以下罚款；造成损失的依法承担赔偿责任。",
     "https://ycs.gov.cn/jczwgk/zhzf/szgygl/content_8292"),

    ("占道", "城市道路管理条例", "第33条",
     "因工程建设需要挖掘城市道路的，应当提交城市规划部门批准签发的文件和有关设计文件，经市政工程行政主管部门和公安交通管理部门批准，方可按照规定挖掘。新建、扩建、改建的城市道路交付使用后5年内、大修的城市道路竣工后3年内不得挖掘；因特殊情况需要挖掘的，须经县级以上城市人民政府批准。",
     "挖掘 城市道路 审批 占道 施工 5年",
     "未经批准擅自挖掘城市道路的，依据本条例第42条责令限期改正、可处2万元以下罚款。",
     "https://xzfg.moj.gov.cn/front/law/detail?LawID=1163"),

    ("消防通道", "GB 50016 建筑设计防火规范", "第7.1.8条",
     "消防车道应符合下列要求：1 车道的净宽度和净空高度均不应小于4.0m；2 转弯半径应满足消防车转弯的要求；3 消防车道与建筑之间不应设置妨碍消防车操作的树木、架空管线等障碍物；4 消防车道边缘距离可燃材料堆场、易燃可燃液体储罐等不宜小于5m；5 消防车道与建筑外墙的水平距离应满足消防车安全通行的要求，位于建筑消防扑救面一侧兼作消防救援场地的消防车道应满足消防救援作业的要求。",
     "消防车道 净宽 4米 净高 转弯半径 障碍物",
     "建设工程不符合消防技术标准的责令整改；违反消防法按第28条、第60条处罚。",
     "http://zfcxjw.cq.gov.cn/zwxx_166/gsgg/202511/P020251111333056281354.pdf"),

    ("消防通道", "福建省消防条例", "第36条",
     "任何单位、个人不得违法划定停车泊位和设置其他设施、障碍物，占用、阻塞公共疏散通道、安全出口、消防车通道、消防车登高操作场地。",
     "福建 消防 疏散通道 安全出口 消防车通道 登高场地 占用 阻塞",
     "违反本条例的，由消防救援机构责令改正，依法给予处罚。",
     "https://www.fujian.gov.cn/zwgk/flfg/dfxfg/202306/t20230624_6191403.htm"),
]


def run():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT category, law_name, article FROM tb_regulation")
            existing = set(cur.fetchall())
            new = [r for r in REGULATIONS if (r[0], r[1], r[2]) not in existing]
            if new:
                sql = ("INSERT INTO tb_regulation "
                       "(category, law_name, article, content, keywords, penalty, source_url) "
                       "VALUES (%s,%s,%s,%s,%s,%s,%s)")
                cur.executemany(sql, new)
                print(f"[法规补充] 插入 {len(new)} 条")
            else:
                print("[法规补充] 无新增")
        conn.commit()
        with conn.cursor() as cur:
            print("--- 法规库 4 类分布 ---")
            cur.execute("SELECT category, COUNT(*) FROM tb_regulation GROUP BY category ORDER BY category")
            for r in cur.fetchall():
                print("   ", r[0], "=", r[1])
    finally:
        conn.close()


if __name__ == "__main__":
    run()
