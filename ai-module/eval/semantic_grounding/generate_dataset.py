# -*- coding: utf-8 -*-
"""Deterministically materialize the template-based calibration dataset.

This generator is not a source of human gold labels.  It creates balanced
construction targets only; model consensus is the calibration reference.
"""

from pathlib import Path

from core.slot_schemas import get_slot_schema
from eval.semantic_grounding.protocol import dump_jsonl

ROOT = Path(__file__).parent

TEMPLATES = [
    {
        "category": "fire_lane_blocked", "slot": "blocker", "slot_class": "A",
        "values": (
            "私家车", "电动自行车", "废旧沙发", "纸箱堆", "建筑木板",
            "塑料周转箱", "旧床垫", "共享单车", "三轮车", "装修垃圾",
            "广告展架", "垃圾桶", "花盆", "快递包裹", "泡沫箱",
            "水泥袋", "废旧家电", "儿童推车", "菜筐", "金属货架",
            "折叠椅", "水桶", "手推车", "煤气罐", "木托盘",
        ),
        "source_template": "消防通道被{value}占用",
        "weak_value": "通道障碍物",
        "neutral_quote": "消防通道旁装有应急照明灯",
        "contradicted_prefix": "现场没有发现",
        "weak_contradiction_quote": "现场画面显示通道畅通",
    },
    {
        "category": "fire_lane_blocked", "slot": "impact", "slot_class": "B",
        "values": (
            "无法进入", "无法转弯", "无法靠近", "无法展开水带", "通行空间不足",
            "需要倒车绕行", "只能单侧通过", "人员无法疏散", "救援设备难以进入",
            "消防车被挡住", "通道宽度不足", "车辆掉头困难", "担架无法通过",
            "破拆工具难送达", "水枪射程受阻", "登高车无法展开", "消防员需步行进入",
            "应急车辆受阻", "现场调度困难", "救援路径中断", "出口被封闭",
            "车辆只能停在外围", "通道出现瓶颈", "消防车通行延误", "人员通行受阻",
        ),
        "source_template": "消防车{value}",
        "weak_value": "通行受到影响",
        "neutral_quote": "消防车从东门进入后停在车位",
        "contradicted_prefix": "现场显示并非",
        "weak_contradiction_quote": "现场画面显示车辆正常通过",
    },
    {
        "category": "dangerous_building", "slot": "structure", "slot_class": "A",
        "values": (
            "墙体倾斜", "承重墙开裂", "地基下沉", "梁柱变形", "屋面塌陷",
            "外墙脱落", "楼板裂缝", "结构位移", "墙面鼓包", "楼梯断裂",
            "阳台下沉", "围护墙倒塌", "砖体松动", "屋顶漏水塌边", "门窗整体变形",
            "柱体倾斜", "墙体贯穿裂缝", "楼体偏移", "基础掏空", "局部坍塌",
            "烟囱倾斜", "雨棚断裂", "女儿墙开裂", "地下室渗水沉降", "框架节点损坏",
        ),
        "source_template": "房屋{value}",
        "weak_value": "房屋结构异常",
        "neutral_quote": "楼道墙面新刷了白漆",
        "contradicted_prefix": "经核查房屋没有",
        "weak_contradiction_quote": "现场画面显示楼体笔直稳定",
    },
    {
        "category": "road_occupancy", "slot": "persistence", "slot_class": "A",
        "values": (
            "每天从早到晚占道", "连续占用三个月", "每周五天固定摆摊",
            "早晚高峰持续占用", "半年内一直没有撤离", "从清晨六点占到深夜",
            "长期固定摊位占路", "连续两个季度未清理", "每天固定时段阻塞",
            "周末全天占用", "工作日早晚均占用", "已经持续一个多月",
            "长期停放不移动", "从月初一直占用至今", "摊位连续数周未撤",
            "每天都在同一位置摆放", "固定商户长期外摆", "每天营业时间全程占道",
            "持续半年以上", "常年堆放在路边", "早市结束后仍未清理",
            "连续多日占压盲道", "固定时段反复占用", "长时间摆放货物",
            "持续占用道路通行空间",
        ),
        "source_template": "路边摊贩{value}",
        "weak_value": "长期占道",
        "neutral_quote": "摊主正在收拾收款二维码",
        "contradicted_prefix": "摊贩并非",
        "weak_contradiction_quote": "现场画面显示摊主已经收摊离开",
    },
    {
        "category": "manhole_damage", "slot": "defect", "slot_class": "A",
        "values": (
            "井盖缺失", "井盖破损", "井盖松动", "井盖下沉", "井盖周边塌陷",
            "井盖翘起", "井盖裂纹", "井盖断裂", "井盖倾斜", "井盖移位",
            "井盖被压坏", "井盖边缘脱落", "井盖与井口错位", "井盖中央塌陷",
            "井盖盖板破损", "井盖周边空洞", "井盖固定件丢失", "井盖表面碎裂",
            "井盖承重不足", "井盖被掀起", "井盖边框损坏", "井盖整体翻转",
            "井盖下方悬空", "井盖密封圈脱落", "井盖被异物卡住",
        ),
        "source_template": "道路上的{value}",
        "weak_value": "井盖损坏",
        "neutral_quote": "井盖旁边放了两个交通锥",
        "contradicted_prefix": "现场确认井盖没有",
        "weak_contradiction_quote": "现场画面显示井盖完整平整",
    },
    {
        "category": "exposed_wire", "slot": "source", "slot_class": "A",
        "values": (
            "裸露电线", "绝缘层破损", "接线盒敞开", "电线接头外露", "电缆护套开裂",
            "插座面板缺失", "线路直接暴露", "配电箱门未关", "导线铜芯外露",
            "临时线未穿管", "插排绝缘破损", "电缆端头裸露", "灯具接线外露",
            "开关面板脱落", "线路私拉乱接", "电线浸泡在水中", "配电箱接线外露",
            "明线未做保护", "接地线断开", "电线缠绕金属件", "插座打火烧黑",
            "电缆表皮破损", "接线端子裸露", "临时接线裸露", "配电箱盖板缺失",
        ),
        "source_template": "墙边发现{value}",
        "weak_value": "电线裸露",
        "neutral_quote": "配电箱旁挂着维修工具袋",
        "contradicted_prefix": "现场确认没有",
        "weak_contradiction_quote": "现场画面显示电线绝缘层完整",
    },
]

SITE_CONTEXTS = (
    "阳光花园东门", "幸福里北区", "建设路三巷", "河滨小区南门", "学府家园二号楼",
    "城北市场西侧", "青云街道便民点", "康宁小区地下车库", "人民公园东侧",
    "江滨花园五号楼", "锦绣华庭西门", "和平社区活动中心", "东湖新村三排",
    "南湖小区消防通道", "站前广场北侧", "绿洲家园六号楼", "金桂小区幼儿园旁",
    "梧桐里商业街", "望江社区旧改工地", "安居苑十二栋", "滨河路沿街商铺",
    "育才路公交站旁", "龙湖天街后巷", "新华小区配电房", "老城隍庙步行街",
)

BOUNDARY_CASES = (
    {"boundary_kind": "synonym", "category": "fire_lane_blocked", "slot": "blocker",
     "value": "杂物", "quote": "废旧家具", "source_text": "消防通道被废旧家具堵住",
     "expected_label": "entailed"},
    {"boundary_kind": "synonym", "category": "dangerous_building", "slot": "structure",
     "value": "墙体倾斜", "quote": "明显歪向一侧", "source_text": "楼体明显歪向一侧",
     "expected_label": "entailed"},
    {"boundary_kind": "synonym", "category": "road_occupancy", "slot": "persistence",
     "value": "长期占道", "quote": "每天早晚高峰", "source_text": "每天早晚高峰都在这里摆摊",
     "expected_label": "entailed"},
    {"boundary_kind": "synonym", "category": "manhole_damage", "slot": "defect",
     "value": "井盖破损", "quote": "裂开一大块", "source_text": "井盖裂开一大块",
     "expected_label": "entailed"},
    {"boundary_kind": "synonym", "category": "exposed_wire", "slot": "source",
     "value": "电线裸露", "quote": "露在外面", "source_text": "墙里的电线露在外面",
     "expected_label": "entailed"},
    {"boundary_kind": "negation", "category": "fire_lane_blocked", "slot": "blocker",
     "value": "被占用", "quote": "没有被占用", "source_text": "消防通道没有被占用",
     "expected_label": "contradicted"},
    {"boundary_kind": "negation", "category": "dangerous_building", "slot": "structure",
     "value": "倾斜", "quote": "没有倾斜", "source_text": "房屋没有倾斜",
     "expected_label": "contradicted"},
    {"boundary_kind": "negation", "category": "manhole_damage", "slot": "defect",
     "value": "破损", "quote": "没有破损", "source_text": "井盖没有破损",
     "expected_label": "contradicted"},
    {"boundary_kind": "negation", "category": "exposed_wire", "slot": "source",
     "value": "裸露电线", "quote": "没有裸露", "source_text": "电线没有裸露",
     "expected_label": "contradicted"},
    {"boundary_kind": "negation", "category": "fire_lane_blocked", "slot": "persistence",
     "value": "长期", "quote": "并非长期占用", "source_text": "消防通道并非长期占用",
     "expected_label": "contradicted"},
    {"boundary_kind": "number", "category": "fire_lane_blocked", "slot": "blocker",
     "value": "限高5米", "quote": "限高3米", "source_text": "消防通道限高3米",
     "expected_label": "contradicted"},
    {"boundary_kind": "number", "category": "manhole_damage", "slot": "defect",
     "value": "承重20吨", "quote": "承重10吨", "source_text": "井盖承重10吨",
     "expected_label": "contradicted"},
    {"boundary_kind": "number", "category": "no_barrier", "slot": "site",
     "value": "高度2.5米", "quote": "高度1.8米", "source_text": "施工围挡高度1.8米",
     "expected_label": "contradicted"},
    {"boundary_kind": "number", "category": "exposed_wire", "slot": "source",
     "value": "电压380伏", "quote": "电压220伏", "source_text": "电线电压220伏",
     "expected_label": "contradicted"},
    {"boundary_kind": "number", "category": "deep_pit", "slot": "site",
     "value": "坑深3米", "quote": "坑深2米", "source_text": "施工坑深2米",
     "expected_label": "contradicted"},
    {"boundary_kind": "multi_turn", "category": "fire_lane_blocked", "slot": "blocker",
     "value": "共享单车", "quote": "一排共享单车", "source_text": "后来看清是一排共享单车",
     "turns": ["消防通道有东西挡着", "后来看清是一排共享单车"], "expected_label": "entailed"},
    {"boundary_kind": "multi_turn", "category": "dangerous_building", "slot": "structure",
     "value": "墙体倾斜", "quote": "墙面已经歪了", "source_text": "补充一句，墙面已经歪了",
     "turns": ["那栋老楼看着不对", "补充一句，墙面已经歪了"], "expected_label": "entailed"},
    {"boundary_kind": "multi_turn", "category": "road_occupancy", "slot": "persistence",
     "value": "长期", "quote": "已经半年了", "source_text": "物业说这种情况已经半年了",
     "turns": ["路边一直有人停车", "物业说这种情况已经半年了"], "expected_label": "entailed"},
    {"boundary_kind": "multi_turn", "category": "manhole_damage", "slot": "defect",
     "value": "破损", "quote": "裂了一个口子", "source_text": "走近看是裂了一个口子",
     "turns": ["楼下井盖有问题", "走近看是裂了一个口子"], "expected_label": "entailed"},
    {"boundary_kind": "multi_turn", "category": "exposed_wire", "slot": "source",
     "value": "裸露电线", "quote": "铜线露出来了", "source_text": "后来又看到铜线露出来了",
     "turns": ["配电箱旁边不太对", "后来又看到铜线露出来了"], "expected_label": "entailed"},
    {"boundary_kind": "vision", "category": "fire_lane_blocked", "slot": "blocker",
     "value": "纸箱", "quote": "纸箱", "source_text": "[视觉分析] 消防通道内堆放纸箱",
     "expected_label": "entailed"},
    {"boundary_kind": "vision", "category": "dangerous_building", "slot": "structure",
     "value": "倾斜", "quote": "倾斜", "source_text": "[视觉分析] 楼房外墙明显倾斜",
     "expected_label": "entailed"},
    {"boundary_kind": "vision", "category": "manhole_damage", "slot": "defect",
     "value": "缺盖", "quote": "缺盖", "source_text": "[视觉分析] 井口缺盖",
     "expected_label": "entailed"},
    {"boundary_kind": "vision", "category": "no_barrier", "slot": "site",
     "value": "无围挡", "quote": "无围挡", "source_text": "[视觉分析] 施工区域无围挡",
     "expected_label": "entailed"},
    {"boundary_kind": "vision", "category": "exposed_wire", "slot": "source",
     "value": "裸露电线", "quote": "裸露电线", "source_text": "[视觉分析] 墙面有裸露电线",
     "expected_label": "entailed"},
    {"boundary_kind": "assistant_misuse", "category": "fire_lane_blocked", "slot": "blocker",
     "value": "私家车", "quote": "私家车", "source_text": "我理解为消防通道被私家车占用",
     "expected_label": "neutral"},
    {"boundary_kind": "assistant_misuse", "category": "dangerous_building", "slot": "structure",
     "value": "倾斜", "quote": "倾斜", "source_text": "我理解为房屋已经倾斜",
     "expected_label": "neutral"},
    {"boundary_kind": "assistant_misuse", "category": "road_occupancy", "slot": "persistence",
     "value": "长期", "quote": "长期", "source_text": "我推断这是长期占道",
     "expected_label": "neutral"},
    {"boundary_kind": "assistant_misuse", "category": "manhole_damage", "slot": "defect",
     "value": "破损", "quote": "破损", "source_text": "我替用户判断井盖已经破损",
     "expected_label": "neutral"},
    {"boundary_kind": "assistant_misuse", "category": "exposed_wire", "slot": "source",
     "value": "裸露电线", "quote": "裸露电线", "source_text": "我先写下墙边有裸露电线",
     "expected_label": "neutral"},
)


def build_base_rows():
    rows = []
    variants = ("entailed", "entailed_weak", "neutral", "neutral",
                "contradicted", "contradicted_weak")
    expected_labels = {
        "entailed": "entailed", "entailed_weak": "entailed",
        "neutral": "neutral", "contradicted": "contradicted",
        "contradicted_weak": "contradicted",
    }
    for group_index in range(25):
        group = "qv-src-%03d" % (group_index + 1)
        split = "dev" if group_index < 15 else "test"
        for row_index, variant in enumerate(variants):
            template = TEMPLATES[(row_index + group_index) % len(TEMPLATES)]
            base_value = template["values"][group_index]
            base_source = template["source_template"].format(value=base_value)
            if variant == "entailed":
                value, quote, source = base_value, base_value, base_source
            elif variant == "entailed_weak":
                value, quote, source = template["weak_value"], base_value, base_source
            elif variant == "neutral":
                quote = template["neutral_quote"]
                value = base_value
                source = "%s，%s" % (base_source, quote)
            elif variant == "contradicted":
                value = base_value
                quote = template["contradicted_prefix"] + base_value
                source = quote
            else:
                value = base_value
                quote = template["weak_contradiction_quote"]
                source = quote
            source = "在%s，%s" % (SITE_CONTEXTS[group_index], source)
            rows.append({
                "id": "qv-%03d" % (len(rows) + 1),
                "source_group_id": group,
                "category": template["category"],
                "slot": template["slot"],
                "slot_class": template["slot_class"],
                "value": value,
                "quote": quote,
                "source_text": source,
                "split": split,
                "expected_label": expected_labels[variant],
            })
    return rows


def build_boundary_rows(base_rows):
    rows = []
    for index, case in enumerate(BOUNDARY_CASES):
        schema = {slot.key: slot for slot in get_slot_schema(case["category"])}
        kind = case["boundary_kind"]
        source_kind = "assistant" if kind == "assistant_misuse" else (
            "vision" if kind == "vision" else "user"
        )
        source_ref = (
            "a%d" % (index + 1) if source_kind == "assistant"
            else "v%d" % (index + 1) if source_kind == "vision"
            else "u1"
        )
        row = {
            "id": "qv-boundary-%03d" % (index + 1),
            "source_group_id": "qv-boundary-src-%03d" % (index + 1),
            "category": case["category"],
            "slot": case["slot"],
            "slot_class": schema[case["slot"]].value_class,
            "value": case["value"],
            "quote": case["quote"],
            "source_text": case["source_text"],
            "split": "boundary",
            "expected_label": case["expected_label"],
            "boundary_kind": kind,
            "source_kind": source_kind,
            "source_ref": source_ref,
        }
        if "turns" in case:
            row["turns"] = list(case["turns"])
        rows.append(row)
    return rows


def main():
    base = build_base_rows()
    boundary = build_boundary_rows(base)
    dump_jsonl(ROOT / "dataset" / "qv-pseudo-v1.jsonl", base)
    dump_jsonl(ROOT / "dataset" / "boundary.jsonl", boundary)


if __name__ == "__main__":
    main()
