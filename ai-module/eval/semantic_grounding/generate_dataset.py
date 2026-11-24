# -*- coding: utf-8 -*-
"""Deterministically materialize the template-based calibration dataset.

This generator is not a source of human gold labels.  It creates balanced
construction targets only; model consensus is the calibration reference.
"""

from pathlib import Path

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

BOUNDARY_KINDS = (
    "synonym", "synonym", "synonym", "synonym", "synonym",
    "negation", "negation", "negation", "negation", "negation",
    "number", "number", "number", "number", "number",
    "multi_turn", "multi_turn", "multi_turn", "multi_turn", "multi_turn",
    "vision", "vision", "vision", "assistant_misuse", "assistant_misuse",
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
    for index, kind in enumerate(BOUNDARY_KINDS):
        seed = base_rows[(index * 6) % len(base_rows)]
        row = dict(seed)
        row["id"] = "qv-boundary-%03d" % (index + 1)
        row["source_group_id"] = "qv-boundary-src-%03d" % (index + 1)
        row["split"] = "boundary"
        row["boundary_kind"] = kind
        if kind == "assistant_misuse":
            row["source_kind"] = "assistant"
        elif kind == "vision":
            row["source_kind"] = "vision"
        else:
            row["source_kind"] = "user"
        rows.append(row)
    return rows


def main():
    base = build_base_rows()
    boundary = build_boundary_rows(base)
    dump_jsonl(ROOT / "dataset" / "qv-pseudo-v1.jsonl", base)
    dump_jsonl(ROOT / "dataset" / "boundary.jsonl", boundary)


if __name__ == "__main__":
    main()
