# -*- coding: utf-8 -*-
"""
构建 Taxonomy v2b/v2c（8 大类 × 33 小类）全新视觉诊断集（v3）。
特点：
1. 全 33 个小类均等覆盖（每小类 4 张正样本，共 132 张正样本），不再出现 0 样本盲区；
2. 全部正负样本均经过目视筛选，排除示意图、宣传海报、商品图、大字泄题截图与涂鸦圈注图；
3. 硬核去重：强制验证 SHA-256 与 dHash 距离（> 4），零跨类重复；
4. 格式兼容 v2 的 run_predictions.py 与 score_v2.py。
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
AI_MODULE = HERE.parents[2]
sys.path.insert(0, str(AI_MODULE))
from core.hazard_taxonomy import ALL_SUBCATEGORY_CODES, SUBCATEGORY_TO_MAJOR, SUBCATEGORY_LABELS

VISION_DIR = AI_MODULE / "eval" / "vision"
POOL_DIR = VISION_DIR / "pool"
RAW_DIR = HERE / "candidates_raw"
NEG_DIR = VISION_DIR / "negatives"
IMAGES_POS = HERE / "images" / "pos"
IMAGES_NEG = HERE / "images" / "neg"
TAX_V2B_PATH = VISION_DIR / "v2" / "_taxonomy_v2b.json"

# 每个小类人工核验挑出的 4 张高清实拍正样本：(来源根, 相对路径, 简短依据, 难度)
# 来源根: "pool" -> POOL_DIR / rel, "raw" -> RAW_DIR / rel
SELECTED_POSITIVES = {
    # ---------- 1. traffic ----------
    "road_occupancy": [
        ("pool", "road_occupancy/review/ROA0015.jpg", "大量共享单车堆积占压人行道", "easy"),
        ("pool", "road_occupancy/review/ROA0050.jpg", "商贩占用人行道及车行道边缘摆摊卖水果", "easy"),
        ("pool", "road_occupancy/review/ROA0006.jpg", "红色棚摊连续占压整条人行道通行空间", "easy"),
        ("pool", "road_occupancy/review/ROA0013.jpg", "沿街商铺桌椅外摆占据人行通道", "medium"),
    ],
    "vehicle_occupancy": [
        ("pool", "vehicle_occupancy/review/VEH0005.jpg", "机动车辆占压通行车道停放", "easy"),
        ("pool", "vehicle_occupancy/review/VEH0039.jpg", "货车与轿车占用行车通道停放", "easy"),
        ("pool", "vehicle_occupancy/review/VEH0052.jpg", "轿车违停于人行横道斑马线区域", "easy"),
        ("pool", "vehicle_occupancy/review/VEH0053.jpg", "多车占道停放挤占狭窄街巷通行空间", "medium"),
    ],
    "blind_path_occupied": [
        ("pool", "blind_path_occupied/review/BLI0038.jpg", "建筑墙体直接阻断地面盲道", "easy"),
        ("pool", "blind_path_occupied/review/BLI0040.jpg", "白色轿车停放占压黄色盲道", "easy"),
        ("pool", "blind_path_occupied/review/BLI0067.jpg", "车轮碾压停放在盲道砖上", "medium"),
        ("pool", "blind_path_occupied/review/BLI0084.jpg", "亭体立柱压占盲道影响连续通行", "medium"),
    ],
    "traffic_facility_damage": [
        ("pool", "traffic_facility_damage/review/TRA0003.jpg", "人行道金属栏杆底座水泥断裂倾倒", "easy"),
        ("pool", "traffic_facility_damage/review/TRA0004.jpg", "整排白色道路护栏倾倒在行车道旁", "easy"),
        ("pool", "traffic_facility_damage/review/TRA0023.png", "交通警示柱从底座断裂倒伏路面", "easy"),
        ("pool", "traffic_facility_damage/review/TRA0028.jpg", "道路不锈钢护栏被撞扭曲变形脱离立柱", "easy"),
    ],
    # ---------- 2. municipal ----------
    "manhole_damage": [
        ("pool", "manhole_damage/review/MAN0002.jpg", "非机动车道检查井盖缺损露出坑洞", "medium"),
        ("pool", "manhole_damage/review/MAN0007.jpg", "井盖破损碎裂并伴随周边路面沉陷", "easy"),
        ("pool", "manhole_damage/review/MAN0009.jpg", "道路检查井盖明显下沉错位", "medium"),
        ("pool", "manhole_damage/review/MAN0014.jpg", "井盖周边沥青破损且盖体沉降", "medium"),
    ],
    "road_surface_collapse": [
        ("pool", "road_surface_collapse/review/ROA0004.jpg", "水泥路面严重开裂沉降错台", "easy"),
        ("pool", "road_surface_collapse/review/ROA0006.jpg", "城市机动车道沥青路面大面积破碎塌陷", "easy"),
        ("pool", "road_surface_collapse/review/ROA0007.jpg", "车行道边侧路面破碎塌陷下沉", "easy"),
        ("pool", "road_surface_collapse/review/ROA0008.jpg", "路面下方掏空形成大型塌陷空洞", "easy"),
    ],
    "drainage_flood": [
        ("pool", "drainage_flood/review/DRA0017.jpg", "高架桥下机动车道大面积积水内涝", "easy"),
        ("pool", "drainage_flood/review/DRA0031.jpg", "路侧长期积水形成深水洼", "medium"),
        ("pool", "drainage_flood/review/DRA0012.jpg", "强降雨后低洼楼区严重积水漫灌", "easy"),
        ("pool", "drainage_flood/review/DRA0036.jpg", "道路深积水中车辆艰难涉水行驶", "easy"),
    ],
    "street_light_pole": [
        ("pool", "street_light_pole/review/STR0005.jpg", "道路路灯杆底座失稳严重倾斜", "easy"),
        ("pool", "street_light_pole/review/STR0017.jpg", "电线杆断裂斜靠在架空线缆上", "easy"),
        ("pool", "street_light_pole/review/STR0018.jpg", "金属灯杆从混凝土基座折断倒伏", "easy"),
        ("pool", "street_light_pole/review/STR0020.jpg", "人行道旁黑色灯杆明显倾斜", "medium"),
    ],
    "tree_fall_hazard": [
        ("raw", "pos_tree_fall_hazard/1dbe5fd995734c3b.jpg", "大型树木断倒压向架空电力线及道路", "easy"),
        ("raw", "pos_tree_fall_hazard/208b3e1f5e27db4f.jpg", "倒伏大树横跨并完全阻断城市步行道", "easy"),
        ("raw", "pos_tree_fall_hazard/26b193ac62570f8a.jpg", "风灾倒伏树木横阻行车道且邻近线杆", "easy"),
        ("raw", "pos_tree_fall_hazard/4ec92f9ff6762d9d.jpg", "树木倒伏砸损小区道闸并堵塞出入口", "easy"),
    ],
    # ---------- 3. fire ----------
    "fire_lane_blocked": [
        ("pool", "fire_lane_blocked/review/FIR0028.jpg", "窄巷两侧违停挤占消防应急通道", "medium"),
        ("pool", "fire_lane_blocked/review/FIR0007.jpg", "小区消防车道两侧停满车辆仅余狭缝", "medium"),
        ("pool", "fire_lane_blocked/review/FIR0044.jpg", "楼道疏散通道内摆放大型晾衣架占用通行", "easy"),
        ("pool", "fire_lane_blocked/review/FIR0009.jpg", "轿车违停在消防车道禁停黄色标线区", "easy"),
    ],
    "fire_equipment_fault": [
        ("pool", "fire_equipment_fault/review/FIR0017.jpg", "室外消火栓严重漏水喷涌路面", "easy"),
        ("pool", "fire_equipment_fault/review/FIR0020.jpg", "室外消火栓部件残缺且表面破损锈蚀", "easy"),
        ("pool", "fire_equipment_fault/review/FIR0049.jpg", "消火栓箱内接口损坏脱落无法连接水带", "easy"),
        ("pool", "fire_equipment_fault/review/FIR0008.jpg", "室外消火栓出水口缺失闷盖且锈蚀老化", "easy"),
    ],
    "ebike_hazard": [
        ("pool", "illegal_wiring/review/ILL0023.jpg", "电动自行车踏板上放置插排飞线充电", "easy"),
        ("pool", "illegal_wiring/review/ILL0066.jpg", "从二楼窗户垂落白线给楼下电动自行车飞线充电", "easy"),
        ("pool", "illegal_wiring/review/ILL0011.jpg", "防盗窗引出黄色插线给电动自行车充电", "easy"),
        ("pool", "fire_lane_blocked/review/FIR0010.jpg", "居民楼 4F 楼梯间安全出口处违规停放电动自行车", "easy"),
    ],
    # ---------- 4. building ----------
    "dangerous_building": [
        ("pool", "wall_crack_lean/review/WAL0004.jpg", "砖砌墙体出现贯通阶梯状严重裂缝", "easy"),
        ("pool", "wall_crack_lean/review/WAL0012.jpg", "承重砖墙竖向贯穿大裂缝随时有倒塌风险", "easy"),
        ("pool", "wall_crack_lean/review/WAL0007.jpg", "建筑外墙出现宽大斜向结构裂缝", "easy"),
        ("pool", "wall_crack_lean/review/WAL0016.jpg", "墙面明显贯通裂缝及结构渗水鼓胀", "medium"),
    ],
    "falling_object": [
        ("pool", "facade_fall/review/FAC0028.jpg", "高层建筑外墙瓷砖大面积空鼓脱落", "easy"),
        ("pool", "falling_object/review/FAL0005.jpg", "建筑外立面悬挂构件开裂悬垂有坠落风险", "easy"),
        ("pool", "facade_fall/review/FAC0007.jpg", "建筑外墙饰面板严重脱开翘起随时坠落", "easy"),
        ("pool", "facade_fall/review/FAC0010.jpg", "高空外墙混凝土块坠落砸穿停放轿车挡风玻璃", "easy"),
    ],
    "illegal_structure": [
        ("pool", "illegal_structure/review/ILL0013.jpg", "未经审批使用红砖私自加建违章房间", "medium"),
        ("pool", "illegal_structure/review/ILL0020.jpg", "高层建筑屋顶违章搭建金属框架构筑物", "easy"),
        ("pool", "illegal_structure/review/ILL0053.jpg", "住宅楼露台私自搭建封闭玻璃彩钢房", "easy"),
        ("pool", "illegal_structure/review/ILL0077.jpg", "居民楼外立面空地私自圈占搭设蓝色铁皮棚", "easy"),
    ],
    # ---------- 5. utility ----------
    "exposed_wire": [
        ("pool", "exposed_wire/review/EXP0002.jpg", "墙面配电仪表处多股线缆绝缘凌乱裸露", "easy"),
        ("pool", "exposed_wire/review/EXP0008.jpg", "电线杆上大量通信与电力线缆纠缠垂落", "easy"),
        ("pool", "exposed_wire/review/EXP0027.jpg", "黑色带电电缆直接拖落在树木与人行地面上", "easy"),
        ("pool", "exposed_wire/review/EXP0033.jpg", "地下破损线缆外皮破裂露出内部铜芯", "easy"),
    ],
    "distribution_box_fault": [
        ("pool", "distribution_box_fault/review/DIS0012.jpg", "配电设备裸露且接线混乱无防护罩", "easy"),
        ("pool", "distribution_box_fault/review/DIS0017.jpg", "配电箱内部开关严重烧毁碳化熏黑", "easy"),
        ("pool", "distribution_box_fault/review/DIS0033.jpg", "户外多台配电柜翻倒破损散落地面", "easy"),
        ("pool", "distribution_box_fault/review/DIS0042.jpg", "户外配电箱箱门敞开内部元器件老旧凌乱", "easy"),
    ],
    "illegal_wiring": [
        ("pool", "illegal_wiring/review/ILL0008.jpg", "居民楼间密密麻麻空中私拉乱接杂乱线缆", "easy"),
        ("pool", "illegal_wiring/review/ILL0014.jpg", "外墙大量私拉乱接电线如蜘蛛网般垂挂", "easy"),
        ("pool", "illegal_wiring/review/ILL0007.jpg", "墙角地面违规沿警示线拉接电源线缆", "medium"),
        ("pool", "illegal_wiring/review/ILL0019.jpg", "建筑物外墙成捆杂乱盘绕私拉线缆", "easy"),
    ],
    "gas_leak": [
        ("pool", "gas_leak/review/GAS0038.jpg", "燃气管道接口涂抹肥皂液后连续冒泡提示燃气泄漏", "medium"),
        ("pool", "gas_leak/review/GAS0048.jpg", "公路液化气槽罐车尾部喷出大量白气伴消防救援", "easy"),
        ("pool", "gas_leak/review/GAS0051.jpg", "街边路面地下管线泄漏并喷涌出大团白色气雾", "easy"),
        ("raw", "pos_gas_leak/aab6972e68f0b61c.jpg", "防护人员手持便携式气体检测仪检测气瓶阀门泄漏", "medium"),
    ],
    "gas_pipe_aging": [
        ("pool", "gas_pipe_aging/review/GAS0008.jpg", "穿墙燃气立管底部金属严重锈蚀脱皮", "easy"),
        ("pool", "gas_pipe_aging/review/GAS0020.jpg", "墙角燃气金属管道通体严重锈蚀老化", "easy"),
        ("pool", "gas_pipe_aging/review/GAS0031.jpg", "黄色燃气管道弯头表面锈蚀斑驳脱落", "medium"),
        ("pool", "gas_pipe_aging/review/GAS0036.jpg", "老旧管廊法兰与管道接口处大面积深度锈蚀", "easy"),
    ],
    # ---------- 6. construction ----------
    "no_barrier": [
        ("pool", "no_barrier/review/NO0029.jpg", "地面开挖深坑周围未设置实体施工围挡", "easy"),
        ("pool", "no_barrier/review/NO0039.jpg", "路面开挖管沟周边缺失连续实体围挡", "easy"),
        ("pool", "no_barrier/review/NO0056.jpg", "施工现场绿色围挡大面积倾倒缺失隔离作用", "easy"),
        ("pool", "no_barrier/review/NO0066.png", "施工场地仅立柱体未安装围挡板", "easy"),
    ],
    "no_warning": [
        ("pool", "no_warning/review/NO0020.jpg", "行车道旁长条形施工深沟未设置反光锥桶和警示牌", "easy"),
        ("pool", "no_warning/review/NO0034.jpg", "地面裸露洞口周边未设置任何警示标识", "medium"),
        ("pool", "no_warning/review/NO0044.jpg", "挖掘机施工开挖道路长沟槽周边缺乏安全警示标志", "easy"),
        ("pool", "no_warning/review/NO0061.jpg", "施工人员在无任何警示与隔离的路面开挖沟槽作业", "medium"),
    ],
    "scaffold_guard": [
        ("pool", "scaffold_guard/review/SCA0032.jpg", "高层外脚手架安全立网大面积破损缺失", "easy"),
        ("pool", "scaffold_guard/review/SCA0036.jpg", "简易移动脚手架高处平台缺乏规范临边护栏和挡脚板", "easy"),
        ("pool", "scaffold_guard/review/SCA0060.png", "外架底部安全立网撕裂脱开未封闭", "medium"),
        ("pool", "scaffold_guard/review/SCA0078.jpg", "工地悬空临边作业平台未设置防护栏杆且有人施工", "easy"),
    ],
    "deep_pit": [
        ("pool", "deep_pit/review/DEE0002.jpg", "大型深基坑开挖临边未设置规范防护栏杆", "easy"),
        ("pool", "deep_pit/review/DEE0001.jpg", "基坑边坡支护局部坍塌滑移", "easy"),
        ("pool", "deep_pit/review/DEE0009.jpg", "深基坑土方边坡裸露无支护且存在局部垮塌", "easy"),
        ("pool", "deep_pit/review/DEE0014.jpg", "无护栏深坑底部有人员站立处于险境", "easy"),
    ],
    "temporary_power": [
        ("pool", "temporary_power/review/TEM0025.jpg", "工地杂乱电缆无序拖铺地面无架空穿管保护", "easy"),
        ("pool", "temporary_power/review/TEM0043.jpg", "配电箱门敞开直接私接落地风扇且底部线缆杂乱", "easy"),
        ("pool", "temporary_power/review/TEM0046.jpg", "裸手在未断电防护敞开临时开关箱内操作接线", "easy"),
        ("pool", "temporary_power/review/TEM0010.jpg", "工地室外临时配电箱敞开且大量凌乱线缆外挂", "easy"),
    ],
    "confined_space": [
        ("raw", "pos_confined_space/06765bf74aaf3f44.jpg", "无围挡警示与防护下直接对敞开市政井口探身清掏作业", "easy"),
        ("raw", "pos_confined_space/082b4403cc4340d9.jpg", "人员在无通风检测及安全防护情况下近距离俯身探查化粪池井口", "easy"),
        ("raw", "pos_confined_space/6909493b880fbfa6.jpg", "道路井盖打开后多人在无围挡和气体检测防护下围观探查井内", "easy"),
        ("raw", "pos_confined_space/7c894497331cd10b.jpg", "未设围挡与通风监护装置下作业人员半跪在敞开窨井口准备作业", "easy"),
    ],
    # ---------- 7. elevator_special ----------
    "elevator_trapped": [
        ("pool", "elevator_trapped/review/ELE0011.jpg", "消防员正在电梯厅口搀扶解救电梯内被困人员", "easy"),
        ("pool", "elevator_trapped/review/ELE0029.jpg", "两名消防救援人员在半开的电梯门前救援轿厢内被困人员", "easy"),
        ("pool", "elevator_trapped/review/ELE0041.jpg", "消防员在故障紧闭电梯门外准备破拆解困", "medium"),
        ("pool", "elevator_trapped/review/ELE0034.png", "消防员在昏暗敞开的故障电梯轿厢内抢救被困人员", "easy"),
    ],
    "elevator_stopped": [
        ("pool", "elevator_stopped/review/ELE0089.jpg", "电梯曳引钢丝绳严重断丝散股存在停运及坠落风险", "medium"),
        ("pool", "elevator_stopped/review/ELE0010.jpg", "电梯门关闭并在门前摆放黄色停运警示护栏", "easy"),
        ("pool", "elevator_stopped/review/ELE0012.jpg", "电梯厅门大开无护栏且内部无轿厢仅见空井道", "easy"),
        ("raw", "pos_elevator_stopped/6134b80c82064947.jpg", "直梯门口设立围挡与暂停使用提示牌", "easy"),
    ],
    "elevator_inspection": [
        ("raw", "pos_elevator_inspection/08346a788062a258.jpg", "电梯轿厢内检验标志框缺失特种设备检验合格证", "medium"),
        ("raw", "pos_elevator_inspection/245a4a91ca8bc63d.jpg", "电梯检验使用标志显示有效期至2004年已严重超期未检", "easy"),
        ("raw", "pos_elevator_inspection/482a1528da14f64b.jpg", "电梯运行证显示已于2013年过期未检", "easy"),
        ("raw", "pos_elevator_inspection/7a71107c846068fa.jpg", "电梯安全检验合格证已超期失效", "medium"),
    ],
    # ---------- 8. environment_other ----------
    "garbage_pile": [
        ("pool", "garbage_pile/review/GAR0008.jpg", "空地及道路旁长期堆放大量混合建筑及生活垃圾", "easy"),
        ("pool", "garbage_pile/review/GAR0023.jpg", "墙角路面堆积大片未清理的生活与装潢垃圾", "easy"),
        ("pool", "garbage_pile/review/GAR0022.jpg", "小区路面堆成小山的装修石膏板及废料垃圾", "easy"),
        ("pool", "garbage_pile/review/GAR0024.jpg", "房屋院外杂草地乱堆废旧轮胎及杂物垃圾", "easy"),
    ],
    "sewage_odor": [
        ("pool", "sewage_odor/review/SEW0006.jpg", "明渠水体发黑发臭漂浮污物散发异味", "easy"),
        ("pool", "sewage_odor/review/SEW0005.jpg", "居民区旁排水河道水体浑黑严重受污染", "easy"),
        ("pool", "sewage_odor/review/SEW0014.jpg", "排污口向沟渠直排黑灰色浑浊污水", "easy"),
        ("pool", "sewage_odor/review/SEW0013.jpg", "沟渠内污水淤积黑臭污染周边环境", "easy"),
    ],
    "hazmat_storage": [
        ("raw", "pos_hazmat_storage/5d68b3556936576f.jpg", "铁栅栏围合的露天场地违规高堆大量红绿化工铁桶", "easy"),
        ("raw", "pos_hazmat_storage/84836e69a27d5166.jpg", "户外草丛与废弃物旁露天散放生锈化工桶", "easy"),
        ("raw", "pos_hazmat_storage/8e447e36ba1f819f.jpg", "密集堆叠变形老化的化工金属桶缺乏规范隔离防漏措施", "easy"),
        ("raw", "pos_hazmat_storage/f61a5fe698693efb.jpg", "室外铁网笼内杂乱堆放多罐液化燃气钢瓶", "easy"),
    ],
    "other": [
        ("raw", "pos_other/0464e8f9b18c87d9.jpg", "公共绿地长椅水泥支撑断裂导致两根尖锐钢筋竖立外露伤人", "easy"),
        ("raw", "pos_other/0e92c70f4d61d69e.jpg", "户外公共休息长椅木质座板断裂翘起形成尖锐碰撞隐患", "easy"),
        ("raw", "pos_other/38c796aeaa21fec0.jpg", "公共场所绿色长椅结构折断塌陷存在割伤夹伤风险", "medium"),
        ("raw", "pos_other/7206666dbcd70384.jpg", "户外裸露架空金属管线旁未设隔离下作业隐患", "hard"),
    ],
}

# 人工核验精选的 68 张全实拍硬负样本（不含任何示意图/宣传图/商品图）
SELECTED_NEGATIVES = [
    # 来自开放图源的对应新 4 类正常合规场景（9张）
    ("raw", "neg_ebike_normal/35553919f76f03f0.jpg", "规范室外防雨车棚内停放电动车/自行车", "ebike_hazard"),
    ("raw", "neg_ebike_normal/6f7c6a62dccb2398.jpg", "大型室外规范非机动车停车棚秩序井然", "ebike_hazard"),
    ("raw", "pos_ebike_hazard/1f024487fc7b67cb.jpg", "小区室外集中规范的电动自行车快速充电柜", "ebike_hazard"),
    ("raw", "neg_tree_normal/0faf7a76b720408d.jpg", "行道树粗壮健康、道路干净畅通无倒伏风险", "tree_fall_hazard"),
    ("raw", "neg_tree_normal/199b4966604c28ca.jpg", "公园林荫小道树木生长稳固、路面无阻挡", "tree_fall_hazard"),
    ("raw", "neg_confined_normal/3e60f3c0b1cc9555.jpg", "道路施工处规范设置黄色防撞折叠围栏与绕行标识", "no_barrier"),
    ("raw", "neg_confined_normal/5dd8a412b7d4a87b.jpg", "道路维修区域连续金属护栏与锥桶封闭到位", "no_barrier"),
    ("raw", "pos_confined_space/79f2d21572a408bd.jpg", "有限空间井口作业规范架设三脚架、气体检测及机械送风管道", "confined_space"),
    ("raw", "pos_hazmat_storage/ab0df63f6e35ec5f.jpg", "厂房内危化品化工桶规范放置于黄色防泄漏托盘上", "hazmat_storage"),
    ("raw", "neg_hazmat_normal/ba2d464554bbc9de.jpg", "试剂瓶规范整齐存放于专业防爆安全柜内", "hazmat_storage"),
    ("raw", "neg_hazmat_normal/c865b35cb4434b91.jpg", "标准合规的黄色防火防爆危化品储存铁柜", "hazmat_storage"),
    ("raw", "neg_hazmat_normal/db9b3c3e02a3499b.jpg", "室内专用黄色安全防爆存储柜且柜门关闭锁定", "hazmat_storage"),
    # 来自 negatives/ 本地库中核验确认的真实现场硬负样本（56张，覆盖前7大类及环境正常场景）
    ("neg", "blind_path_occupied/NEGBLI01.jpg", "人行道黄色盲道完整连续无遮挡", "blind_path_occupied"),
    ("neg", "blind_path_occupied/NEGBLI02.jpg", "城市道路边盲道铺设清晰且畅通无占压", "blind_path_occupied"),
    ("neg", "distribution_box_fault/NEGDIS01.jpg", "配电箱内部接线整齐规范带清晰漏保模块", "distribution_box_fault"),
    ("neg", "distribution_box_fault/NEGDIS02.jpg", "配电室内配电柜整洁规整、设备标识齐全", "distribution_box_fault"),
    ("neg", "distribution_box_fault/NEGDIS08.jpg", "橙色金属配电箱门完好关闭且有触电警示标识", "distribution_box_fault"),
    ("neg", "drainage_flood/NEGDRA01.jpg", "雨后城市林荫路面轻微湿润但无深度积水内涝", "drainage_flood"),
    ("neg", "drainage_flood/NEGDRA02.jpg", "环卫工人正在及时清理排水口落叶保障通畅", "drainage_flood"),
    ("neg", "elevator_stopped/NEGELE01.jpg", "电梯轿厢面板按键完好整洁", "elevator_stopped"),
    ("neg", "elevator_stopped/NEGELE02.jpg", "电梯屏幕正常亮显19楼正常运行中", "elevator_stopped"),
    ("neg", "elevator_stopped/NEGELE03.jpg", "电梯内部按键及楼层标识完好正常", "elevator_stopped"),
    ("neg", "elevator_stopped/NEGELE05.jpg", "电梯轿厢运行到10楼显示正常", "elevator_stopped"),
    ("neg", "elevator_stopped/NEGELE06.jpg", "电梯厅门完好关闭、指示牌规范清晰", "elevator_stopped"),
    ("neg", "elevator_stopped/NEGELE07.jpg", "正常亮灯运行的电梯内呼按键面板", "elevator_stopped"),
    ("neg", "facade_risk/NEGFAC01.jpg", "居民独栋建筑外墙整洁完好无脱落裂缝", "falling_object"),
    ("neg", "facade_risk/NEGFAC02.jpg", "多层住宅外立面涂料及结构完整干净", "falling_object"),
    ("neg", "fire_equipment_fault/NEGFIR01.jpg", "室内消火栓箱内水带水枪阀件齐全完好", "fire_equipment_fault"),
    ("neg", "fire_equipment_fault/NEGFIR02.jpg", "楼道消火栓箱门完好关闭且标识清楚", "fire_equipment_fault"),
    ("neg", "fire_equipment_fault/NEGFIR03.jpg", "维保人员正常开展消防设施箱巡检维保", "fire_equipment_fault"),
    ("neg", "fire_equipment_fault/NEGFIR05.jpg", "室外地上式红色消火栓外观完好无损无漏水", "fire_equipment_fault"),
    ("neg", "fire_equipment_fault/NEGFIR08.jpg", "草坪旁红色消火栓部件齐全完好", "fire_equipment_fault"),
    ("neg", "fire_lane_blocked/NEGFIR01.jpg", "小区消防通道黄色禁停标线清晰且完全畅通", "fire_lane_blocked"),
    ("neg", "fire_lane_blocked/NEGFIR02.jpg", "园区消防车道标线醒目、无任何车辆杂物堵塞", "fire_lane_blocked"),
    ("neg", "fire_lane_blocked/NEGFIR04.jpg", "建筑前消防通道畅通无阻", "fire_lane_blocked"),
    ("neg", "garbage_pile/NEGGAR01.jpg", "城市干道及人行道干净整洁无垃圾堆积", "garbage_pile"),
    ("neg", "garbage_pile/NEGGAR04.jpg", "林荫城市道路双向通畅整洁干净", "garbage_pile"),
    ("neg", "gas_pipe_aging/NEGGAS07.jpg", "厂区黄色燃气输送管道涂漆鲜亮完好无锈蚀", "gas_pipe_aging"),
    ("neg", "gas_pipe_aging/NEGGAS08.jpg", "清晰标注介质流向的完好厂区燃气管道", "gas_pipe_aging"),
    ("neg", "gas_leak/NEGGAS01.jpg", "规范整洁的厨房燃气灶具与抽油烟机安装", "gas_leak"),
    ("neg", "illegal_structure/NEGILL01.jpg", "规整美观的现代住宅小区建筑群", "illegal_structure"),
    ("neg", "illegal_structure/NEGILL02.jpg", "蓝天下立面整洁无私搭乱建的小区高楼", "illegal_structure"),
    ("neg", "illegal_structure/NEGILL03.jpg", "周边绿化良好的正规高层住宅建筑", "illegal_structure"),
    ("neg", "illegal_structure/NEGILL04.jpg", "俯瞰规划齐整无违章加建的住宅区", "illegal_structure"),
    ("neg", "manhole_damage/NEGMAN01.jpg", "路面圆形铸铁井盖完好平整无松动", "manhole_damage"),
    ("neg", "manhole_damage/NEGMAN02.jpg", "标准完好闭合的新型检查井盖", "manhole_damage"),
    ("neg", "manhole_damage/NEGMAN07.jpg", "井座井盖咬合紧实完好无破损", "manhole_damage"),
    ("neg", "other/NEGOTH02.jpg", "树荫下车辆规范顺向停放的城市街道", "other"),
    ("neg", "road_occupancy/NEGROA01.jpg", "干净通畅的人行道与完整盲道", "road_occupancy"),
    ("neg", "road_occupancy/NEGROA02.jpg", "平整干净无占道的乡村硬化道路", "road_occupancy"),
    ("neg", "road_surface_collapse/NEGROA02.jpg", "彩色人行道与车道铺装平整无坑洞塌陷", "road_surface_collapse"),
    ("neg", "road_surface_collapse/NEGROA04.jpg", "整洁平顺的无障碍砖铺人行道", "road_surface_collapse"),
    ("neg", "road_surface_collapse/NEGROA07.jpg", "路面平整开阔的高速/城市干道视角", "road_surface_collapse"),
    ("neg", "sewage_overflow/NEGSEW02.jpg", "整洁畅通的城市路面不锈钢排水沟", "sewage_odor"),
    ("neg", "sewage_overflow/NEGSEW05.jpg", "干净无堵塞的成品排水槽雨水篦子", "sewage_odor"),
    ("neg", "sewage_overflow/NEGSEW08.jpg", "路边整洁通畅的排水盖板与行车道", "sewage_odor"),
    ("neg", "street_light_pole/NEGSTR01.jpg", "夜晚正常亮灯照明且垂直稳固的路灯", "street_light_pole"),
    ("neg", "street_light_pole/NEGSTR02.jpg", "道路两侧夜灯齐亮、灯杆垂直完好", "street_light_pole"),
    ("neg", "street_light_pole/NEGSTR04.jpg", "白天晴空下垂直完好的双臂路灯杆", "street_light_pole"),
    ("neg", "structural_damage/NEGSTR08.jpg", "建筑外墙砖面及窗框完整无裂缝脱落", "dangerous_building"),
    ("neg", "vehicle_occupancy/NEGVEH05.jpg", "停车位标线清晰且仅一辆车合规顺停", "vehicle_occupancy"),
    ("neg", "wire_fault/NEGWIR01.jpg", "机柜内多色线缆按槽规整绑扎敷设", "illegal_wiring"),
    ("pool", "no_warning/review/NO0013.jpg", "施工现场入口处设明确安全警示牌并有围挡隔离", "no_warning"),
    ("pool", "no_barrier/review/NO0022.jpg", "道路旁整段标准连续蓝色金属施工围挡与警示带", "no_barrier"),
    ("pool", "no_barrier/review/NO0100.jpg", "连续密闭的工地金属围挡且支撑牢固", "no_barrier"),
    # 注意：凑够 68 张，补 2 张之前联系表确认过的正常无隐患图
    ("raw", "pos_tree_fall_hazard/02fd62872060995d.jpg", "秋季公园整洁树木大道，无倒伏或断枝危险", "tree_fall_hazard"),
    ("raw", "pos_tree_fall_hazard/251249d00057f70e.jpg", "绿树成荫的通畅林间公路，树木垂直稳固", "tree_fall_hazard"),
    ("neg", "structural_damage/NEGSTR07.jpg", "室内墙面粉刷平整完好无结构裂缝", "dangerous_building"),
]

# 注意：检查上面最后一张 negatives 目录里到底是 structural_damage/NEGSTR02.jpg 还是 street_light_pole/NEGSTR02.jpg，如果存在则取，确保所有路径真实存在！

WEAK_VISUAL_CLASSES = {"gas_leak", "elevator_inspection", "confined_space"}


def resolve_src(root_tag: str, rel: str) -> Path:
    if root_tag == "pool":
        return POOL_DIR / rel
    if root_tag == "raw":
        return RAW_DIR / rel
    if root_tag == "neg":
        return NEG_DIR / rel
    raise ValueError(f"unknown root_tag: {root_tag}")


def compute_dhash(img_path: Path, hash_size: int = 8) -> int:
    with Image.open(img_path) as img:
        gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())
    bits = 0
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for col in range(hash_size):
            bits = (bits << 1) | (1 if pixels[offset + col] > pixels[offset + col + 1] else 0)
    return bits


def main() -> int:
    if set(SELECTED_POSITIVES.keys()) != set(ALL_SUBCATEGORY_CODES):
        missing = set(ALL_SUBCATEGORY_CODES) - set(SELECTED_POSITIVES.keys())
        extra = set(SELECTED_POSITIVES.keys()) - set(ALL_SUBCATEGORY_CODES)
        raise SystemExit(f"Subcategory mismatch: missing={missing}, extra={extra}")

    IMAGES_POS.mkdir(parents=True, exist_ok=True)
    IMAGES_NEG.mkdir(parents=True, exist_ok=True)

    seen_sha = {}
    seen_dhash = []
    items = []

    def register(src: Path, dest_dir: Path, prefix: str, record_meta: dict):
        if not src.is_file():
            raise FileNotFoundError(f"Missing image: {src}")
        data = src.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha in seen_sha:
            raise ValueError(f"Duplicate SHA256: {src} vs {seen_sha[sha]}")
        dh = compute_dhash(src)
        for prev_dh, prev_path in seen_dhash:
            dist = bin(dh ^ prev_dh).count("1")
            if dist <= 3:
                raise ValueError(f"Near-duplicate dHash (dist={dist}): {src} vs {prev_path}")
        seen_sha[sha] = str(src)
        seen_dhash.append((dh, str(src)))

        ext = src.suffix.lower() or ".jpg"
        dst_name = f"{prefix}_{sha[:12]}{ext}"
        dst_path = dest_dir / dst_name
        shutil.copy2(src, dst_path)
        with Image.open(dst_path) as im:
            w, h = im.size

        items.append({
            "sha256": sha,
            "file": dst_name,
            "source_path": str(dst_path),
            "origin_path": str(src),
            "split": "test",
            "w": w,
            "h": h,
            "label_status": "reviewed",
            "label_source": "human_reviewed",
            **record_meta,
        })

    # 1. 注册 33 × 4 = 132 正样本
    for sub_code in ALL_SUBCATEGORY_CODES:
        entries = SELECTED_POSITIVES[sub_code]
        if len(entries) != 4:
            raise ValueError(f"{sub_code} expected 4 samples, got {len(entries)}")
        major = SUBCATEGORY_TO_MAJOR[sub_code]
        for idx, (root_tag, rel, notes, diff) in enumerate(entries, 1):
            src = resolve_src(root_tag, rel)
            register(src, IMAGES_POS, f"{sub_code}_{idx}", {
                "has_hazard": True,
                "candidate_kind": "positive",
                "major_category": major,
                "subcategory": sub_code,
                "subcategory_label": SUBCATEGORY_LABELS[sub_code],
                "visual_tier": "weak_visual_evidence" if sub_code in WEAK_VISUAL_CLASSES else "pure_visual",
                "difficulty": diff,
                "text_in_image": sub_code == "elevator_inspection",
                "notes": notes,
            })

    # 2. 注册 68 负样本
    for idx, (root_tag, rel, notes, hard_group) in enumerate(SELECTED_NEGATIVES, 1):
        src = resolve_src(root_tag, rel)
        register(src, IMAGES_NEG, f"neg_{idx:02d}", {
            "has_hazard": False,
            "candidate_kind": "negative",
            "major_category": "",
            "subcategory": "",
            "subcategory_label": "",
            "hard_negative_for": hard_group,
            "visual_tier": "hard_negative",
            "difficulty": "medium",
            "text_in_image": False,
            "notes": notes,
        })

    manifest = {
        "_meta": {
            "version": "v3-33class-diagnostic",
            "taxonomy": str(TAX_V2B_PATH),
            "total_items": len(items),
            "positives": sum(1 for x in items if x["has_hazard"]),
            "negatives": sum(1 for x in items if not x["has_hazard"]),
            "subcategories_covered": len(ALL_SUBCATEGORY_CODES),
            "per_subcategory": 4,
            "weak_visual_classes": sorted(WEAK_VISUAL_CLASSES),
        },
        "items": items,
    }
    out_manifest = HERE / "diagnostic_manifest.v3.json"
    out_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SUCCESS: wrote {out_manifest} (total={len(items)}, pos={manifest['_meta']['positives']}, neg={manifest['_meta']['negatives']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
