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
        "category": "fire_lane_blocked",
        "slot": "blocker",
        "slot_class": "A",
        "entailed": ("消防通道长期被私家车占用", "私家车", "私家车"),
        "entailed_weak": ("消防通道长期被一辆私家车占用", "车辆", "私家车"),
        "neutral": ("消防通道旁停着一辆自行车，门口还放着纸箱", "私家车", "纸箱"),
        "contradicted": ("消防通道限高3米，现场没有车辆进入", "限高5米", "限高3米"),
        "contradicted_weak": ("消防通道内只停放着自行车", "私家车", "只停放着自行车"),
    },
    {
        "category": "fire_lane_blocked",
        "slot": "impact",
        "slot_class": "B",
        "entailed": ("消防车无法进入小区", "无法进入", "无法进入"),
        "entailed_weak": ("消防车无法进入小区", "通行受阻", "无法进入"),
        "neutral": ("消防车从小区东门进入，通道畅通", "无法通行", "小区东门"),
        "contradicted": ("消防车可以正常通过，现场测试完成", "无法通行", "正常通过"),
        "contradicted_weak": ("消防车可以正常通过，现场测试完成", "无法通行", "正常通过"),
    },
    {
        "category": "dangerous_building",
        "slot": "structure",
        "slot_class": "A",
        "entailed": ("房屋整体向一侧倾斜", "倾斜", "倾斜"),
        "entailed_weak": ("房屋整体向一侧倾斜", "墙体倾斜", "整体向一侧倾斜"),
        "neutral": ("房屋外墙有裂缝，室内家具摆放整齐", "倾斜", "家具摆放整齐"),
        "contradicted": ("房屋经复核结构稳定，没有倾斜", "倾斜", "没有倾斜"),
        "contradicted_weak": ("房屋经复核结构稳定，整体笔直", "墙体倾斜", "整体笔直"),
    },
    {
        "category": "road_occupancy",
        "slot": "persistence",
        "slot_class": "A",
        "entailed": ("摊贩每天从早到晚占着道路", "长期", "每天从早到晚"),
        "entailed_weak": ("摊贩每天从早到晚占着道路", "长期占道", "每天从早到晚"),
        "neutral": ("摊贩今天临时停在路边，已经离开", "长期", "已经离开"),
        "contradicted": ("摊贩只是临时摆放，十分钟后就离开", "长期", "临时摆放"),
        "contradicted_weak": ("摊贩只是临时摆放，十分钟后就离开", "长期占道", "十分钟后就离开"),
    },
    {
        "category": "manhole_damage",
        "slot": "defect",
        "slot_class": "A",
        "entailed": ("井盖已经破损，边缘翘起", "破损", "破损"),
        "entailed_weak": ("井盖已经破损，边缘翘起", "井盖损坏", "破损"),
        "neutral": ("井盖旁有一摊积水，路面有些湿", "破损", "积水"),
        "contradicted": ("井盖完好，没有破损", "破损", "没有破损"),
        "contradicted_weak": ("井盖表面平整，边缘完整", "破损", "边缘完整"),
    },
    {
        "category": "exposed_wire",
        "slot": "source",
        "slot_class": "A",
        "entailed": ("墙边有一截裸露电线", "裸露电线", "裸露电线"),
        "entailed_weak": ("墙边有一截裸露电线", "电线裸露", "裸露电线"),
        "neutral": ("配电箱旁放着维修工具", "裸露电线", "维修工具"),
        "contradicted": ("电线绝缘层完好，没有裸露", "裸露电线", "没有裸露"),
        "contradicted_weak": ("电线绝缘层完好，表面完整", "裸露电线", "绝缘层完好"),
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
            source, value, quote = template[variant]
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
