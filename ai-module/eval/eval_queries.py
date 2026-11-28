"""评测查询集：检索评测与分类评测共用同一份，避免两条线的查询漂移。

- QUERY_SET：33 个小类 × 2 种问法
    style="explicit"  直白描述，含类别特征词
    style="colloquial" 口语/同义改写，尽量不含标准类别词（测语义检索）
- NEGATIVE_SET：真无关查询（用于范围护栏与检索空结果率）

金标准标签是"意图归属"，不是"这段文字在库里必须逐字命中"。
"""
from core.hazard_taxonomy import HAZARD_TAXONOMY

QUERY_SET = (
    # ---------- 交通与通行 ----------
    {
        "query": "沿街商铺把货架和纸箱堆到人行道上，行人只能走机动车道",
        "major": "traffic",
        "subcategory": "road_occupancy",
        "style": "explicit",
    },
    {
        "query": "整条街的店门口都摆满了东西，走路的人只能绕到马路中间去",
        "major": "traffic",
        "subcategory": "road_occupancy",
        "style": "colloquial",
    },
    {
        "query": "小区门口机动车道被违停车辆占了一排，通行困难",
        "major": "traffic",
        "subcategory": "vehicle_occupancy",
        "style": "explicit",
    },
    {
        "query": "车横七竖八停了一长溜，把路堵得只剩一条缝",
        "major": "traffic",
        "subcategory": "vehicle_occupancy",
        "style": "colloquial",
    },
    {
        "query": "人行道盲道被共享单车和摊位完全堵死",
        "major": "traffic",
        "subcategory": "blind_path_occupied",
        "style": "explicit",
    },
    {
        "query": "导盲的那条砖上面全是电动车，看不见路的人根本过不去",
        "major": "traffic",
        "subcategory": "blind_path_occupied",
        "style": "colloquial",
    },
    {
        "query": "路口信号灯损坏半个月，一直闪黄灯不切换",
        "major": "traffic",
        "subcategory": "traffic_facility_damage",
        "style": "explicit",
    },
    {
        "query": "那个路口的灯早就不亮了，车和人都不知道什么时候能走",
        "major": "traffic",
        "subcategory": "traffic_facility_damage",
        "style": "colloquial",
    },
    # ---------- 市政设施 ----------
    {
        "query": "暴雨夜雨水井盖缺失移位，行人涉水坠井",
        "major": "municipal",
        "subcategory": "manhole_damage",
        "style": "explicit",
    },
    {
        "query": "马路上一个铁盖子没了，就留个黑洞，晚上看不见掉下去就完了",
        "major": "municipal",
        "subcategory": "manhole_damage",
        "style": "colloquial",
    },
    {
        "query": "主干道路面塌陷出现深坑，下方路基已空洞",
        "major": "municipal",
        "subcategory": "road_surface_collapse",
        "style": "explicit",
    },
    {
        "query": "路中间塌下去一大块，底下都是空的，看着就悬",
        "major": "municipal",
        "subcategory": "road_surface_collapse",
        "style": "colloquial",
    },
    {
        "query": "下穿隧道暴雨严重积水，轿车被淹熄火",
        "major": "municipal",
        "subcategory": "drainage_flood",
        "style": "explicit",
    },
    {
        "query": "一下雨那个桥洞就积起半人深的水，车开进去就趴窝",
        "major": "municipal",
        "subcategory": "drainage_flood",
        "style": "colloquial",
    },
    {
        "query": "小区外路灯连片不亮，线杆底座倾斜开裂",
        "major": "municipal",
        "subcategory": "street_light_pole",
        "style": "explicit",
    },
    {
        "query": "那条路晚上黑得看不见人，旁边的杆子还歪着",
        "major": "municipal",
        "subcategory": "street_light_pole",
        "style": "colloquial",
    },
    {
        "query": "台风过后行道树严重倾斜，大枯枝悬垂在人行道上",
        "major": "municipal",
        "subcategory": "tree_fall_hazard",
        "style": "explicit",
    },
    {
        "query": "路边那棵树歪得很厉害，一根大树枝快掉下来，下面天天有人走",
        "major": "municipal",
        "subcategory": "tree_fall_hazard",
        "style": "colloquial",
    },
    # ---------- 消防安全 ----------
    {
        "query": "高层住宅消防车通道被私家车和杂物长期占用",
        "major": "fire",
        "subcategory": "fire_lane_blocked",
        "style": "explicit",
    },
    {
        "query": "楼下通道全停了车，真着火消防车根本进不来",
        "major": "fire",
        "subcategory": "fire_lane_blocked",
        "style": "colloquial",
    },
    {
        "query": "楼道消火栓箱被上锁、灭火器过期，厂区消防水池水位不足且室外消火栓无水",
        "major": "fire",
        "subcategory": "fire_equipment_fault",
        "style": "explicit",
    },
    {
        "query": "楼里的灭火器没压力，水管箱也锁死了，拧开室外消防龙头一滴水都没有",
        "major": "fire",
        "subcategory": "fire_equipment_fault",
        "style": "colloquial",
    },
    {
        "query": "高层住宅架空层违规停放电动自行车并飞线充电，电池还被带入室内",
        "major": "fire",
        "subcategory": "ebike_hazard",
        "style": "explicit",
    },
    {
        "query": "有人把电动车推进楼道充电，还从楼上拉线下来，电池也拿回家",
        "major": "fire",
        "subcategory": "ebike_hazard",
        "style": "colloquial",
    },
    # ---------- 建筑安全 ----------
    {
        "query": "城中村危房承重墙开裂、房屋整体倾斜，仍有人居住",
        "major": "building",
        "subcategory": "dangerous_building",
        "style": "explicit",
    },
    {
        "query": "那栋老楼早就不行了，墙都是歪的，里头还住着人",
        "major": "building",
        "subcategory": "dangerous_building",
        "style": "colloquial",
    },
    {
        "query": "高层大厦外立面瓷砖脱落砸车，住户还从楼上抛掷红酒瓶砸碎车窗",
        "major": "building",
        "subcategory": "falling_object",
        "style": "explicit",
    },
    {
        "query": "楼上掉下一大块外墙砖，还有人往下扔瓶子，车都被砸了",
        "major": "building",
        "subcategory": "falling_object",
        "style": "colloquial",
    },
    {
        "query": "顶楼住户违规搭建阳光房，并私改承重结构",
        "major": "building",
        "subcategory": "illegal_structure",
        "style": "explicit",
    },
    {
        "query": "顶楼自己在楼顶又盖了个房子出来，还拆了墙",
        "major": "building",
        "subcategory": "illegal_structure",
        "style": "colloquial",
    },
    # ---------- 电气与燃气 ----------
    {
        "query": "小区架空电线绝缘层老化破损，铜芯外露垂落",
        "major": "utility",
        "subcategory": "exposed_wire",
        "style": "explicit",
    },
    {
        "query": "那根电线皮都磨没了，里面的铜丝露在外面晃",
        "major": "utility",
        "subcategory": "exposed_wire",
        "style": "colloquial",
    },
    {
        "query": "小区配电箱箱门缺失、接线端子烧蚀冒烟",
        "major": "utility",
        "subcategory": "distribution_box_fault",
        "style": "explicit",
    },
    {
        "query": "楼下的电表箱子门掉了，里面还冒烟有糊味",
        "major": "utility",
        "subcategory": "distribution_box_fault",
        "style": "colloquial",
    },
    {
        "query": "沿街商铺私拉乱接电线给门头灯箱供电，接线凌乱垂挂外墙",
        "major": "utility",
        "subcategory": "illegal_wiring",
        "style": "explicit",
    },
    {
        "query": "店老板从店里扯了根接线板挂到户外广告牌下面供电，电线缠了一大团",
        "major": "utility",
        "subcategory": "illegal_wiring",
        "style": "colloquial",
    },
    {
        "query": "居民楼燃气管道泄漏，楼道里有明显煤气味",
        "major": "utility",
        "subcategory": "gas_leak",
        "style": "explicit",
    },
    {
        "query": "一进楼道就闻到很大的味儿，像是气漏了",
        "major": "utility",
        "subcategory": "gas_leak",
        "style": "colloquial",
    },
    {
        "query": "老旧小区户外燃气立管锈蚀老化，接口渗漏",
        "major": "utility",
        "subcategory": "gas_pipe_aging",
        "style": "explicit",
    },
    {
        "query": "小区外面那根气管子锈得不成样了，接头地方还渗",
        "major": "utility",
        "subcategory": "gas_pipe_aging",
        "style": "colloquial",
    },
    # ---------- 施工安全 ----------
    {
        "query": "市政施工开挖路面未设置围挡，基坑敞口",
        "major": "construction",
        "subcategory": "no_barrier",
        "style": "explicit",
    },
    {
        "query": "路上挖了个大坑，周围什么也没围，谁都能掉进去",
        "major": "construction",
        "subcategory": "no_barrier",
        "style": "colloquial",
    },
    {
        "query": "道路施工无安全警示标志，夜间无警示灯",
        "major": "construction",
        "subcategory": "no_warning",
        "style": "explicit",
    },
    {
        "query": "修路的地方连个牌子都没有，晚上黑灯瞎火的",
        "major": "construction",
        "subcategory": "no_warning",
        "style": "colloquial",
    },
    {
        "query": "建筑工地脚手架搭设不规范，临边防护栏杆缺失",
        "major": "construction",
        "subcategory": "scaffold_guard",
        "style": "explicit",
    },
    {
        "query": "工地上那个架子感觉随时会塌，边上也没护栏",
        "major": "construction",
        "subcategory": "scaffold_guard",
        "style": "colloquial",
    },
    {
        "query": "深基坑支护桩严重位移开裂，边坡滑移",
        "major": "construction",
        "subcategory": "deep_pit",
        "style": "explicit",
    },
    {
        "query": "楼下挖的坑太深了，边上的土都在往下滑",
        "major": "construction",
        "subcategory": "deep_pit",
        "style": "colloquial",
    },
    {
        "query": "施工现场临时用电线路乱拉，配电箱无漏电保护",
        "major": "construction",
        "subcategory": "temporary_power",
        "style": "explicit",
    },
    {
        "query": "工地上的电是随便接的，箱子也没盖子",
        "major": "construction",
        "subcategory": "temporary_power",
        "style": "colloquial",
    },
    {
        "query": "工人未通风检测就进入污水井作业，发生硫化氢中毒",
        "major": "construction",
        "subcategory": "confined_space",
        "style": "explicit",
    },
    {
        "query": "有人下化粪池清掏，没先通风也没人看着，下去就晕了",
        "major": "construction",
        "subcategory": "confined_space",
        "style": "colloquial",
    },
    # ---------- 电梯与特种设备 ----------
    {
        "query": "客运电梯故障急停困人超过半小时，救援超时",
        "major": "elevator_special",
        "subcategory": "elevator_trapped",
        "style": "explicit",
    },
    {
        "query": "有人被关在电梯里出不来，都半个多小时了",
        "major": "elevator_special",
        "subcategory": "elevator_trapped",
        "style": "colloquial",
    },
    {
        "query": "小区电梯频繁停运并伴随剧烈异响、抖动",
        "major": "elevator_special",
        "subcategory": "elevator_stopped",
        "style": "explicit",
    },
    {
        "query": "我们那栋楼的电梯老是坏，一动就哐当响",
        "major": "elevator_special",
        "subcategory": "elevator_stopped",
        "style": "colloquial",
    },
    {
        "query": "商场自动扶梯超期未检，检验合格标志已过期一年",
        "major": "elevator_special",
        "subcategory": "elevator_inspection",
        "style": "explicit",
    },
    {
        "query": "那个扶梯上面贴的检验牌子早就过期了",
        "major": "elevator_special",
        "subcategory": "elevator_inspection",
        "style": "colloquial",
    },
    # ---------- 环境与其他 ----------
    {
        "query": "小区角落建筑垃圾和生活垃圾长期堆积无人清运",
        "major": "environment_other",
        "subcategory": "garbage_pile",
        "style": "explicit",
    },
    {
        "query": "楼下垃圾堆成山了，一直没人拉走",
        "major": "environment_other",
        "subcategory": "garbage_pile",
        "style": "colloquial",
    },
    {
        "query": "市政管网污水外溢，路面返臭气味刺鼻",
        "major": "environment_other",
        "subcategory": "sewage_odor",
        "style": "explicit",
    },
    {
        "query": "路上的井往外冒臭水，味儿特别大",
        "major": "environment_other",
        "subcategory": "sewage_odor",
        "style": "colloquial",
    },
    {
        "query": "居民区车库存放不明化工桶和易燃溶剂，气味刺鼻且无消防设施",
        "major": "environment_other",
        "subcategory": "hazmat_storage",
        "style": "explicit",
    },
    {
        "query": "小区车库堆着好多没标签的桶，味道很大，旁边就是住户",
        "major": "environment_other",
        "subcategory": "hazmat_storage",
        "style": "colloquial",
    },
    {
        "query": "公园健身器材的连接处断裂，尖锐金属头裸露划伤儿童",
        "major": "environment_other",
        "subcategory": "other",
        "style": "explicit",
    },
    {
        "query": "小区游乐设施坏了个口子，边角特别尖，小孩容易划伤",
        "major": "environment_other",
        "subcategory": "other",
        "style": "colloquial",
    },
)

NEGATIVE_SET = (
    {"query": "今天上海天气怎么样", "note": "无关领域：天气"},
    {"query": "红烧肉怎么做好吃", "note": "无关领域：美食"},
    {"query": "帮我写一首关于秋天的诗", "note": "无关领域：文学创作"},
    {"query": "推荐一部适合周末看的电影", "note": "无关领域：影评"},
    {"query": "Python 列表如何去重", "note": "无关领域：编程"},
    {"query": "今天股市收盘涨了多少", "note": "无关领域：财经"},
    {"query": "减脂期一天该吃多少蛋白质", "note": "无关领域：健身"},
    {"query": "把这句话翻译成英语", "note": "无关领域：翻译"},
    {"query": "最近有什么明星八卦新闻", "note": "无关领域：娱乐"},
    {"query": "国庆去三亚玩几天合适", "note": "无关领域：旅游"},
)


def category_label(major_code: str, subcategory_code: str) -> str:
    """返回库中使用的两级分类标签，例如 消防安全/消防设施故障。"""
    fallback = major_code + "/" + subcategory_code
    for item in HAZARD_TAXONOMY:
        if item["code"] != major_code:
            continue
        for sub_code, sub_label in item["subcategories"]:
            if sub_code == subcategory_code:
                return item["label"] + "/" + sub_label
    return fallback


def covered_subcategories():
    return {(q["major"], q["subcategory"]) for q in QUERY_SET}


def all_subcategories():
    return {
        (item["code"], sub_code)
        for item in HAZARD_TAXONOMY
        for sub_code, _ in item["subcategories"]
    }
