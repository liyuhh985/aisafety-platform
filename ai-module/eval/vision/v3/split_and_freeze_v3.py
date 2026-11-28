# -*- coding: utf-8 -*-
"""
生成洁净版 dev_manifest.v3.json（200张）并独立构建、冻结 frozen_test_manifest.v3.json（120张，33类×2正+54实拍硬负）。
严格校验 dev 与 frozen_test 之间 SHA-256 零重叠、dHash 距离 > 3 零近似重复。
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
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
TAX_V2B_PATH = VISION_DIR / "v2" / "_taxonomy_v2b.json"

TEST_IMAGES_POS = HERE / "frozen_images" / "pos"
TEST_IMAGES_NEG = HERE / "frozen_images" / "neg"
DEV_IMAGES_NEG = HERE / "images" / "neg"

WEAK_VISUAL_CLASSES = {"gas_leak", "elevator_inspection", "confined_space"}

# 替换掉原 v3_dev 中自身确有瑕疵的 4 条负样本（用 neg_unused 干净图替换）
DEV_NEG_REPLACEMENTS = {
    "neg_09_ab0df63f6e35.jpg": ("neg", "blind_path_occupied/NEGBLI03.jpg", "城市人行道盲道铺设完整连续无占压", "blind_path_occupied"),
    "neg_16_fc2861c4cd11.jpg": ("neg", "facade_risk/NEGFAC03.jpg", "现代多层住宅建筑外立面及窗框完整整洁", "falling_object"),
    "neg_36_a410d8ba8700.jpg": ("neg", "garbage_pile/NEGGAR02.jpg", "干净通畅的城市主干道与绿化带街景", "garbage_pile"),
    "neg_56_9cd5ae6b6b18.jpg": ("neg", "illegal_structure/NEGILL05.jpg", "现代小区规范绿化广场及住宅外立面", "illegal_structure"),
}

# 全新 33 类 × 2 张 = 66 张正样本（绝对不与 v3_dev 或 v2b 测试集重复）
FROZEN_TEST_POSITIVES = {
    "road_occupancy": [
        ("pool", "road_occupancy/review/ROA0003.jpg", "商户摊位占满人行道及路面通道", "easy"),
        ("pool", "road_occupancy/review/ROA0004.jpg", "占道水果摊及三轮车挤占斑马线旁通行空间", "easy"),
    ],
    "vehicle_occupancy": [
        ("pool", "vehicle_occupancy/review/VEH0034.jpg", "红色轿车占用路侧行车道违停", "easy"),
        ("pool", "vehicle_occupancy/review/VEH0079.jpg", "两辆机动车并排违停占压非机动车道", "easy"),
    ],
    "blind_path_occupied": [
        ("pool", "blind_path_occupied/review/BLI0086.jpg", "隔离桩横穿占压人行道黄色盲道", "easy"),
        ("pool", "blind_path_occupied/review/BLI0092.jpg", "金属立杆直接竖立在盲道砖中央阻断通行", "easy"),
    ],
    "traffic_facility_damage": [
        ("pool", "traffic_facility_damage/review/TRA0032.jpg", "道路金属隔离护栏衔接端断裂脱出", "easy"),
        ("pool", "traffic_facility_damage/review/TRA0042.jpg", "白色道路安全护栏立柱底部锈断悬空", "easy"),
    ],
    "manhole_damage": [
        ("pool", "manhole_damage/review/MAN0015.jpg", "检查井盖缺失外框且盖面破裂杂草堵塞", "medium"),
        ("pool", "manhole_damage/review/MAN0016.jpg", "路面井盖破出不规则黑洞且相邻轮胎压边", "easy"),
    ],
    "road_surface_collapse": [
        ("pool", "road_surface_collapse/review/ROA0014.jpg", "混凝土路面纵向断裂塌陷形成错台深缝", "easy"),
        ("pool", "road_surface_collapse/review/ROA0023.jpg", "城市主干道路面严重塌陷导致车辆坠入深坑", "easy"),
    ],
    "drainage_flood": [
        ("pool", "drainage_flood/review/DRA0027.jpg", "暴雨内涝路段车辆半浸在深积水中", "easy"),
        ("pool", "drainage_flood/review/DRA0051.jpg", "小区及辅路大面积积水漫过道路标线", "easy"),
    ],
    "street_light_pole": [
        ("pool", "street_light_pole/review/STR0023.jpg", "水泥线杆倾斜与树枝缠绕存在倒杆隐患", "medium"),
        ("pool", "street_light_pole/review/STR0028.jpg", "夜间路灯杆连根折断倒伏地面灯头破碎", "easy"),
    ],
    "tree_fall_hazard": [
        ("raw", "pos_tree_fall_hazard/26800524ddc3e0e8.jpg", "风折大树倒伏横跨并阻断整条步行道", "easy"),
        ("raw", "pos_tree_fall_hazard/46caf8953f6729ba.jpg", "大型树干及树冠断裂砸中停放轿车", "easy"),
    ],
    "fire_lane_blocked": [
        ("pool", "fire_lane_blocked/review/FIR0040.jpg", "消防通道禁止停车标识牌下方停满车辆杂物", "easy"),
        ("pool", "fire_lane_blocked/review/FIR0062.jpg", "白色轿车停放在标有消防通道黄线的通道中央", "easy"),
    ],
    "fire_equipment_fault": [
        ("pool", "fire_equipment_fault/review/FIR0021.jpg", "室外消火栓严重破损向路面持续喷水", "easy"),
        ("pool", "fire_equipment_fault/review/FIR0040.jpg", "室外消火栓破损漏水导致周边地面长期积水", "easy"),
    ],
    "ebike_hazard": [
        ("pool", "illegal_wiring/review/ILL0004.jpg", "居民楼外墙引出飞线正在给电动自行车充电", "easy"),
        ("pool", "illegal_wiring/review/ILL0010.jpg", "楼道消火栓旁停放电动车并挂充电器充电", "easy"),
    ],
    "dangerous_building": [
        ("pool", "wall_crack_lean/review/WAL0008.jpg", "老旧墙体多道严重结构开裂且存在倾斜风险", "easy"),
        ("pool", "dangerous_building/review/DAN0023.jpg", "砖混危房外墙出现多处贯穿大裂缝濒临坍塌", "easy"),
    ],
    "falling_object": [
        ("pool", "facade_fall/review/FAC0013.jpg", "高空坠落碎石与瓷砖砸损路边停放电动车", "easy"),
        ("pool", "facade_fall/review/FAC0016.jpg", "高层建筑外墙立面保温饰面层大块剥落坠落", "easy"),
    ],
    "illegal_structure": [
        ("pool", "illegal_structure/review/ILL0004.jpg", "高层天井内违规搭建封顶杂物彩钢棚", "easy"),
        ("pool", "illegal_structure/review/ILL0009.jpg", "建筑顶层露台擅自加建封闭式玻璃铁皮屋", "easy"),
    ],
    "exposed_wire": [
        ("pool", "exposed_wire/review/EXP0039.jpg", "电线绝缘层烧蚀破损露出现状铜芯", "easy"),
        ("pool", "exposed_wire/review/EXP0046.jpg", "地面破损电缆外皮开裂暴露彩色芯线", "easy"),
    ],
    "distribution_box_fault": [
        ("pool", "distribution_box_fault/review/DIS0050.jpg", "户外配电柜柜门变形脱开倾倒损毁", "easy"),
        ("pool", "distribution_box_fault/review/DIS0054.png", "室内配电箱内部电气元件严重烧毁发黑", "easy"),
    ],
    "illegal_wiring": [
        ("pool", "illegal_wiring/review/ILL0025.jpg", "外墙从楼上窗户私拉黄色电线垂落地面", "easy"),
        ("pool", "illegal_wiring/review/ILL0033.jpg", "窗口旁私自缠绕引出多股杂乱电源线", "medium"),
    ],
    "gas_leak": [
        ("pool", "gas_leak/review/GAS0003.jpg", "燃气管线突发泄漏喷出大量白色气雾伴消防水雾稀释", "easy"),
        ("pool", "gas_leak/review/GAS0004.jpg", "工业燃气管道接缝出现泄漏应急带压封堵迹象", "medium"),
    ],
    "gas_pipe_aging": [
        ("pool", "gas_pipe_aging/review/GAS0040.jpg", "金属燃气管道接口处严重生锈腐蚀变形", "easy"),
        ("pool", "gas_pipe_aging/review/GAS0054.jpg", "管道内壁及管口严重锈蚀剥落老化", "medium"),
    ],
    "no_barrier": [
        ("pool", "no_barrier/review/NO0080.jpg", "挖掘机施工开挖深沟周边完全未设围挡", "easy"),
        ("pool", "no_barrier/review/NO0007.jpg", "道路施工堆土区外侧围挡大面积缺口缺失封闭", "easy"),
    ],
    "no_warning": [
        ("pool", "no_warning/review/NO0019.jpg", "巷道施工物料及未围蔽区无安全警示标识", "medium"),
        ("pool", "no_warning/review/NO0063.jpg", "车行道中央开挖大深坑周边无警示牌与锥桶", "easy"),
    ],
    "scaffold_guard": [
        ("pool", "scaffold_guard/review/SCA0080.jpg", "建筑工地临边区域仅设稀疏立杆缺乏规范护栏与立网", "easy"),
        ("pool", "scaffold_guard/review/SCA0086.jpg", "外脚手架上部大段安全立网缺失裸露悬空", "easy"),
    ],
    "deep_pit": [
        ("pool", "deep_pit/review/DEE0012.jpg", "超大型深基坑周边缺少规范硬质防护栏杆", "easy"),
        ("pool", "deep_pit/review/DEE0018.jpg", "深基坑土方边坡裸露且仅用简易铁丝网缺乏支护", "easy"),
    ],
    "temporary_power": [
        ("pool", "temporary_power/review/TEM0031.jpg", "工地现场临时配电箱插满工业插头且周边线缆垂地杂乱", "easy"),
        ("pool", "temporary_power/review/TEM0050.jpg", "楼道/作业区竖井内大量临时施工线缆杂乱堆垂", "medium"),
    ],
    "confined_space": [
        ("raw", "pos_confined_space/ba49f7dca71b0ae3.jpg", "人员从敞开市政马路井口直接探身下井作业缺乏围挡与三脚架", "easy"),
        ("raw", "pos_confined_space/c0ec8c4291dbb8e8.jpg", "作业人员无安全防护装备与机械通风设备直接进入狭窄地下井底", "easy"),
    ],
    "elevator_trapped": [
        ("pool", "elevator_trapped/review/ELE0015.jpg", "消防员正在非平层停梯门缝处俯身施救电梯内被困人员", "easy"),
        ("pool", "elevator_trapped/review/ELE0017.jpg", "故障电梯轿厢内两名人员伸手按紧急报警按键求助被困", "easy"),
    ],
    "elevator_stopped": [
        ("pool", "elevator_stopped/review/ELE0011.jpg", "电梯呼梯面板熄灭且显示停用并贴有封条", "easy"),
        ("pool", "elevator_stopped/review/ELE0037.png", "停运电梯门前放置黄色推车阻挡禁止使用", "easy"),
    ],
    "elevator_inspection": [
        ("raw", "pos_elevator_inspection/cbc53c7b6a66e733.jpg", "电梯轿厢内临时运行许可证书标注已于2019年过期", "easy"),
        ("raw", "pos_elevator_inspection/dc1bf1e5416fa853.jpg", "电梯检验使用标志显示检验已严重超期未更新", "easy"),
    ],
    "garbage_pile": [
        ("pool", "garbage_pile/review/GAR0026.jpg", "路边空地堆放大量废弃建筑与塑料生活垃圾成山", "easy"),
        ("pool", "garbage_pile/review/GAR0028.jpg", "绿地及空地上大面积乱倒废弃衣物及杂物垃圾", "easy"),
    ],
    "sewage_odor": [
        ("pool", "sewage_odor/review/SEW0019.jpg", "河道及排水沟渠水体发黑发浑涉嫌污水污染", "easy"),
        ("pool", "sewage_odor/review/SEW0032.jpg", "污水溢流覆盖地面形成墨绿色浑浊脏水潭", "easy"),
    ],
    "hazmat_storage": [
        ("raw", "pos_hazmat_storage/50b5fb465df68219.jpg", "户外路面蓝色危险化学品塑料桶倾倒待防护处置", "easy"),
        ("raw", "extra_hazmat/37f6662a7f47eb44.jpg", "林地间生锈危险废物金属桶露天散置伴随泄漏风险", "easy"),
    ],
    "other": [
        ("raw", "extra_other/183162cf4a795059.jpg", "公共户外混凝土楼梯支撑断裂塌斜悬空存在重大坠落伤人风险", "easy"),
        ("raw", "extra_other2/8d770213209a92e0.jpg", "公园户外木质长椅完全散架碎裂裸露尖锐折断木条", "easy"),
    ],
}

# 54 张全新实拍硬负样本（未入 v3_dev 与 v2b，均为目视核验过的干净实拍）
FROZEN_TEST_NEGATIVES = [
    ("raw", "neg_ebike_normal/cd5915f3dc6359b8.jpg", "规范设置的防雨非机动车停车棚与停放秩序", "ebike_hazard"),
    ("raw", "neg_ebike_normal/cef1a8c8ef034e4b.jpg", "室外带雨棚的规范非机动车充电停放区", "ebike_hazard"),
    ("raw", "neg_ebike_normal/eae1be1997122c5b.jpg", "城市广场规范整齐的共享单车/电动助力车停放箱", "ebike_hazard"),
    ("raw", "neg_tree_normal/41b52890bcd2c7b6.jpg", "城市公园林荫步道树木挺拔生长稳固", "tree_fall_hazard"),
    ("raw", "neg_tree_normal/42113ddece261f8b.jpg", "行道树整齐健康、步行道干净畅通", "tree_fall_hazard"),
    ("raw", "neg_tree_normal/4c8fcc5ac42ee104.jpg", "双排健康行道树与通畅整洁市政人行道", "tree_fall_hazard"),
    ("raw", "neg_tree_normal/557576fdf99b37a1.jpg", "道路旁正常生长且修剪规整的行道树与盲道", "tree_fall_hazard"),
    ("neg", "blind_path_occupied/NEGBLI04.jpg", "广场铺设清晰的黄色无障碍盲道无任何占用", "blind_path_occupied"),
    ("neg", "blind_path_occupied/NEGBLI05.jpg", "公园步道与护栏旁连续畅通的盲道", "blind_path_occupied"),
    ("neg", "blind_path_occupied/NEGBLI07.jpg", "不锈钢盲道凸起导向砖完整无遮挡", "blind_path_occupied"),
    ("neg", "blind_path_occupied/NEGBLI08.jpg", "红色步道旁黄色盲道整洁笔直通畅", "blind_path_occupied"),
    ("neg", "construction_prot/NEGCON06.jpg", "规范施工工地混凝土浇筑作业人员佩戴安全帽协同作业", "scaffold_guard"),
    ("neg", "construction_prot/NEGCON07.jpg", "规范设置安全护坡和围挡的市政管道施工开挖现场", "no_barrier"),
    ("neg", "construction_prot/NEGCON08.jpg", "厂房内挖掘机规范施工且周边地面整洁人员戴帽安全站位", "no_warning"),
    ("neg", "deep_pit/NEGDEE04.jpg", "规范做好支护挡墙与防水措施的合规基坑工程", "deep_pit"),
    ("neg", "deep_pit/NEGDEE05.jpg", "人员佩戴安全帽且基坑支护规范的合规工地", "deep_pit"),
    ("neg", "deep_pit/NEGDEE06.jpg", "标准化支撑梁与连续护坡结构稳固的规范深基坑", "deep_pit"),
    ("neg", "distribution_box_fault/NEGDIS03.jpg", "规范安装的电表箱内部走线清晰工整", "distribution_box_fault"),
    ("neg", "distribution_box_fault/NEGDIS04.jpg", "橙色金属工业配电箱外壳完好且带清晰警示标志", "distribution_box_fault"),
    ("neg", "distribution_box_fault/NEGDIS06.jpg", "洁净配电柜内部开关排列整齐导线捆扎规范", "distribution_box_fault"),
    ("neg", "elevator_stopped/NEGELE04.jpg", "完好关闭运行正常的现代化金属电梯厅门", "elevator_stopped"),
    ("neg", "elevator_stopped/NEGELE08.jpg", "楼层显示屏和呼梯面板正常工作的电梯门厅", "elevator_stopped"),
    ("neg", "facade_risk/NEGFAC05.jpg", "崭新整洁的白灰外墙建筑无任何裂缝剥落", "falling_object"),
    ("neg", "facade_risk/NEGFAC06.jpg", "多层居民楼洁净外墙饰面层完好无空鼓脱落", "falling_object"),
    ("neg", "facade_risk/NEGFAC07.jpg", "现代多层住宅外墙立面完整干净", "falling_object"),
    ("neg", "facade_risk/NEGFAC08.jpg", "建筑外墙瓷砖铺贴规整完好", "falling_object"),
    ("neg", "fire_equipment_fault/NEGFIR04.jpg", "室内消火栓箱内接口与消防水带完整规范", "fire_equipment_fault"),
    ("neg", "fire_equipment_fault/NEGFIR06.jpg", "消火栓箱内部卷盘、水带与阀门完整清洁", "fire_equipment_fault"),
    ("neg", "fire_equipment_fault/NEGFIR07.jpg", "建筑外墙规范安装的消防栓箱完好无损", "fire_equipment_fault"),
    ("neg", "fire_lane_blocked/NEGFIR03.jpg", "园区消防通道黄色禁停标线清晰且完全畅通", "fire_lane_blocked"),
    ("neg", "fire_lane_blocked/NEGFIR08.jpg", "小区消防通道严禁占用立牌醒目且通道空旷", "fire_lane_blocked"),
    ("neg", "garbage_pile/NEGGAR03.jpg", "清晨干净整洁的城市双向道路街景", "garbage_pile"),
    ("neg", "garbage_pile/NEGGAR05.jpg", "整洁林荫人行道与规整花箱景观", "garbage_pile"),
    ("neg", "garbage_pile/NEGGAR06.jpg", "晴空下干净通畅的城市绿化带与道路", "garbage_pile"),
    ("neg", "garbage_pile/NEGGAR08.jpg", "整洁干净的人行步道与绿化带", "garbage_pile"),
    ("neg", "manhole_damage/NEGMAN08.jpg", "规范整齐放置的全新绿色检查井盖构件", "manhole_damage"),
    ("neg", "gas_pipe_aging/NEGGAS05.jpg", "防腐完好的地上黄色燃气调压设施与阀门", "gas_pipe_aging"),
    ("neg", "gas_pipe_aging/NEGGAS06.jpg", "建筑外墙规范固定刷漆的黄色燃气立管", "gas_pipe_aging"),
    ("neg", "gas_leak/NEGGAS05.jpg", "户内规范安装贴墙固定的黄色燃气表管道", "gas_leak"),
    ("neg", "gas_leak/NEGGAS06.jpg", "户内规范安装运行的燃气热水器与黄色软管", "gas_leak"),
    ("neg", "illegal_structure/NEGILL06.jpg", "规划整洁的现代住宅社区及内部道路", "illegal_structure"),
    ("neg", "illegal_structure/NEGILL07.jpg", "水景园林与规整现代住宅楼宇景观", "illegal_structure"),
    ("neg", "illegal_structure/NEGILL08.jpg", "社区绿地与规范住宅楼群外观", "illegal_structure"),
    ("neg", "manhole_damage/NEGMAN03.jpg", "全新标准铸铁检查井盖与规范井座", "manhole_damage"),
    ("neg", "manhole_damage/NEGMAN04.jpg", "人行道方形金属检查井盖严密平整无破损", "manhole_damage"),
    ("neg", "manhole_damage/NEGMAN06.jpg", "路面上嵌合平整完好的圆形检查井盖", "manhole_damage"),
    ("neg", "other/NEGOTH04.jpg", "洁净开阔的城市多车道干道正常通行场景", "other"),
    ("neg", "other/NEGOTH05.jpg", "建筑群间干净通畅无杂物的内部道路", "other"),
    ("neg", "other/NEGOTH06.jpg", "树影斑驳干净整洁的城市林荫大道", "other"),
    ("neg", "road_occupancy/NEGROA03.jpg", "畅通整洁的城市石砖人行道", "road_occupancy"),
    ("neg", "road_occupancy/NEGROA06.jpg", "干净通畅带绿化隔离的城区双车道人行道", "road_occupancy"),
    ("neg", "road_occupancy/NEGROA05.jpg", "绿化带旁整洁无占道的新修人行道", "road_occupancy"),
    ("neg", "road_surface_collapse/NEGROA05.jpg", "平整开阔的城市双车道柏油路面", "road_surface_collapse"),
    ("neg", "road_occupancy/NEGROA08.jpg", "路面平整整洁的城市林荫商业人行道", "road_surface_collapse"),
]


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


def label_sha(item: dict) -> str:
    payload = {
        "has_hazard": item.get("has_hazard"),
        "major_category": item.get("major_category", ""),
        "subcategory": item.get("subcategory", ""),
        "difficulty": item.get("difficulty", ""),
        "text_in_image": item.get("text_in_image"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_clean_dev() -> tuple[dict, set[str], list[tuple[int, str]]]:
    old = json.loads((HERE / "diagnostic_manifest.v3.json").read_text(encoding="utf-8"))
    new_items = []
    dev_shas = set()
    dev_dhashes = []

    for it in old["items"]:
        item = dict(it)
        item["split"] = "dev"
        if item["file"] in DEV_NEG_REPLACEMENTS:
            old_p = Path(item["source_path"])
            if old_p.is_file():
                old_p.unlink()
            root_tag, rel, notes, hard_group = DEV_NEG_REPLACEMENTS[item["file"]]
            src = resolve_src(root_tag, rel)
            if not src.is_file():
                raise FileNotFoundError(f"Missing dev replacement: {src}")
            sha = hashlib.sha256(src.read_bytes()).hexdigest()
            dst_name = f"{item['file'][:6]}_{sha[:12]}{src.suffix.lower() or '.jpg'}"
            dst = DEV_IMAGES_NEG / dst_name
            shutil.copy2(src, dst)
            with Image.open(dst) as im:
                w, h = im.size
            item.update({
                "sha256": sha,
                "file": dst_name,
                "source_path": str(dst),
                "origin_path": str(src),
                "w": w,
                "h": h,
                "hard_negative_for": hard_group,
                "notes": notes,
            })
        p = Path(item["source_path"])
        if item["sha256"] in dev_shas:
            raise ValueError(f"Duplicate sha inside dev: {item['file']}")
        dev_shas.add(item["sha256"])
        dev_dhashes.append((compute_dhash(p), item["file"]))
        new_items.append(item)

    dev_manifest = {
        "_meta": {
            **old["_meta"],
            "version": "v3-dev-diagnostic",
            "split": "dev",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "cleaned_negatives_replaced": sorted(DEV_NEG_REPLACEMENTS.keys()),
        },
        "items": new_items,
    }
    (HERE / "dev_manifest.v3.json").write_text(json.dumps(dev_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dev_manifest, dev_shas, dev_dhashes


def build_frozen_test(dev_shas: set[str], dev_dhashes: list[tuple[int, str]]) -> dict:
    if set(FROZEN_TEST_POSITIVES.keys()) != set(ALL_SUBCATEGORY_CODES):
        raise SystemExit("FROZEN_TEST_POSITIVES must cover all 33 subcategories")

    # 也把 v2b 冻结集的 sha 加入黑名单，确保完全独立
    v2b = json.loads((VISION_DIR / "v2" / "frozen_test_manifest.v2b.json").read_text(encoding="utf-8"))
    v2b_shas = {x["sha256"] for x in v2b["items"] if x.get("sha256")}

    if TEST_IMAGES_POS.exists():
        shutil.rmtree(TEST_IMAGES_POS)
    if TEST_IMAGES_NEG.exists():
        shutil.rmtree(TEST_IMAGES_NEG)
    TEST_IMAGES_POS.mkdir(parents=True, exist_ok=True)
    TEST_IMAGES_NEG.mkdir(parents=True, exist_ok=True)

    test_shas = set()
    test_dhashes = []
    frozen_items = []

    def add_item(src: Path, dest_dir: Path, prefix: str, meta: dict):
        if not src.is_file():
            raise FileNotFoundError(f"Missing frozen test image: {src}")
        sha = hashlib.sha256(src.read_bytes()).hexdigest()
        if sha in dev_shas:
            raise ValueError(f"Leakage into dev (SHA match): {src}")
        if sha in v2b_shas:
            raise ValueError(f"Overlap with v2b test (SHA match): {src}")
        if sha in test_shas:
            raise ValueError(f"Duplicate SHA inside frozen test: {src}")
        dh = compute_dhash(src)
        for prev_dh, prev_name in dev_dhashes:
            if bin(dh ^ prev_dh).count("1") <= 3:
                raise ValueError(f"Near-duplicate with dev ({prev_name}): {src}")
        for prev_dh, prev_name in test_dhashes:
            if bin(dh ^ prev_dh).count("1") <= 3:
                raise ValueError(f"Near-duplicate inside frozen test ({prev_name}): {src}")
        test_shas.add(sha)
        test_dhashes.append((dh, src.name))

        dst_name = f"{prefix}_{sha[:12]}{src.suffix.lower() or '.jpg'}"
        dst = dest_dir / dst_name
        shutil.copy2(src, dst)
        with Image.open(dst) as im:
            w, h = im.size
        rec = {
            "sha256": sha,
            "file_sha256": sha,
            "file": dst_name,
            "source_path": str(dst),
            "origin_path": str(src),
            "split": "test",
            "w": w,
            "h": h,
            "label_status": "reviewed",
            "label_source": "human_reviewed",
            **meta,
        }
        rec["label_sha256"] = label_sha(rec)
        frozen_items.append(rec)

    for code in ALL_SUBCATEGORY_CODES:
        entries = FROZEN_TEST_POSITIVES[code]
        if len(entries) != 2:
            raise ValueError(f"{code} expected 2 test samples, got {len(entries)}")
        major = SUBCATEGORY_TO_MAJOR[code]
        for idx, (root_tag, rel, notes, diff) in enumerate(entries, 1):
            add_item(resolve_src(root_tag, rel), TEST_IMAGES_POS, f"{code}_{idx}", {
                "has_hazard": True,
                "candidate_kind": "positive",
                "major_category": major,
                "subcategory": code,
                "subcategory_label": SUBCATEGORY_LABELS[code],
                "visual_tier": "weak_visual_evidence" if code in WEAK_VISUAL_CLASSES else "pure_visual",
                "difficulty": diff,
                "text_in_image": code == "elevator_inspection",
                "notes": notes,
            })

    for idx, (root_tag, rel, notes, hard_group) in enumerate(FROZEN_TEST_NEGATIVES, 1):
        add_item(resolve_src(root_tag, rel), TEST_IMAGES_NEG, f"neg_{idx:02d}", {
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

    frozen_manifest = {
        "_meta": {
            "version": "v3-frozen-test",
            "protocol_version": "v3-33class-zero-leakage",
            "taxonomy": str(TAX_V2B_PATH),
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "human_reviewed": True,
            "annotation_mode": "human",
            "label_source": "human_reviewed",
            "total_items": len(frozen_items),
            "positives": sum(1 for x in frozen_items if x["has_hazard"]),
            "negatives": sum(1 for x in frozen_items if not x["has_hazard"]),
            "subcategories_covered": len(ALL_SUBCATEGORY_CODES),
            "per_subcategory": 2,
            "weak_visual_classes": sorted(WEAK_VISUAL_CLASSES),
            "disjoint_from_dev_and_v2b": True,
        },
        "items": frozen_items,
    }
    out_path = HERE / "frozen_test_manifest.v3.json"
    out_path.write_text(json.dumps(frozen_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return frozen_manifest


def main() -> int:
    dev_m, dev_shas, dev_dhashes = build_clean_dev()
    frozen_m = build_frozen_test(dev_shas, dev_dhashes)
    print(
        f"BUILT v3_dev={len(dev_m['items'])} (pos={dev_m['_meta']['positives']}, neg={dev_m['_meta']['negatives']}) | "
        f"FROZE v3_test={len(frozen_m['items'])} (pos={frozen_m['_meta']['positives']}, neg={frozen_m['_meta']['negatives']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
