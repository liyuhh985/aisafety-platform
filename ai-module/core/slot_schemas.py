# -*- coding: utf-8 -*-
"""Shared hazard slot definitions for dialogue routing and planning.

槽位按「缺了它，什么会错」分三类，替代原来的 critical 布尔：

  A 决策级 — 缺了它，**风险等级或用户/系统该采取的动作会判错**
            （包括该不该立即处置、该找谁处置） → 追问（进 missing）
  B 报告级 — 结论与动作不变，但**法规适用/责任归属/处罚档次**会不同
            → 不追问，进报告的「仍需确认」条件分支（阶段 4 消费）
  C 装饰级 — 结论、动作、法规都不变（或已被其它字段覆盖） → 不问、不提

逐槽判据见 docs/superpowers/specs/2026-09-27-slot-value-classes-design.md。
**这是初判，需要人工复核**：A/B 的边界（「动作会错」vs「责任归属不同」）
本身是判断，不是事实。

要求「至少 5 个小类的逐槽样例」，见 spec；这里给出三套作为速查：

  占道 / road_occupancy        behavior=B（管辖主体与法规不同）
                               persistence=A（长期→上报处置；临时→现场劝离）
                               blocked=A（完全堵死→通行中断，需立即处置）
  危房 / dangerous_building    structure=A（整体倾斜 vs 局部开裂，危险程度不同）
                               occupancy=A（有人住→需疏散；无人→围挡隔离）
                               risk=C（与规划器已返回的 immediate_danger 重复）
  消防通道 / fire_lane_blocked blocker=A（可燃堆物→火灾风险高；车辆→阻碍通行）
                               persistence=A（长期占用→需执法；临时→可劝离）
                               impact=B（是否影响消防车通行 → 整改要求不同）
"""

from dataclasses import dataclass

from core.hazard_taxonomy import MAJOR_LABELS, SUBCATEGORY_TO_MAJOR, normalize_taxonomy

DECISION_CLASS = "A"
REPORT_CLASS = "B"
DECORATIVE_CLASS = "C"
VALUE_CLASSES = (DECISION_CLASS, REPORT_CLASS, DECORATIVE_CLASS)
REPORT_CLASSES = (DECISION_CLASS, REPORT_CLASS)


@dataclass
class Slot:
    key: str
    question: str
    value_class: str = DECISION_CLASS

    def __post_init__(self) -> None:
        if self.value_class not in VALUE_CLASSES:
            raise ValueError(
                "unknown slot value_class: %r (slot=%s, expected one of %s)"
                % (self.value_class, self.key, "/".join(VALUE_CLASSES))
            )

    @property
    def critical(self) -> bool:
        """兼容旧调用点与既有测试：A 类 == 旧的 critical=True。

        迁移说明：生产路径已改成显式的 A/B 类判定（missing_decision_slots /
        missing_report_slots），保留这个属性只为让旧读取点语义不变。
        """
        return self.value_class == DECISION_CLASS


SLOT_SCHEMAS: dict[str, list[Slot]] = {
    "占道": [
        Slot("behavior", "具体是什么占道？摆摊、还是车辆停放？", REPORT_CLASS),
        Slot("persistence", "是长期占压还是临时停放？"),
        Slot("blocked", "是完全堵死还是部分占用？"),
    ],
    "危房": [
        Slot("structure", "房屋有没有裂缝、倾斜或沉降？"),
        Slot("occupancy", "现在有人在里面居住或使用吗？"),
        Slot("risk", "有没有明显的即时坍塌风险？", DECORATIVE_CLASS),
    ],
    "消防通道": [
        Slot("blocker", "被什么东西占用了？"),
        Slot("persistence", "是长期还是临时？"),
        Slot("impact", "是否影响消防车或人员通行？", REPORT_CLASS),
    ],
    "消防设施": [
        Slot("facility_type", "具体是哪一类消防设施，例如消火栓、喷淋、报警器还是灭火器？"),
        Slot("condition", "目前是老旧、损坏还是完全无法使用？"),
        Slot("function_impact", "是否影响整栋建筑的消防报警或灭火功能？", REPORT_CLASS),
    ],
    "高空坠物": [
        Slot("source", "是从哪掉落的（外墙/阳台/广告牌）？"),
        Slot("target", "下面是人行道还是车行道？", REPORT_CLASS),
        Slot("exposure", "有没有围挡或警告标志？", REPORT_CLASS),
    ],
    "井盖/道路": [
        Slot("defect", "井盖是缺失、破损还是松动？"),
        Slot("traffic", "是否影响行人或车辆通行？", REPORT_CLASS),
    ],
    "电气": [
        Slot("source", "是漏电、裸露电线还是设备故障？"),
        Slot("contact", "是否可能被人或车辆接触到？"),
        Slot("risk", "有没有冒烟或火花等迹象？", DECORATIVE_CLASS),
    ],
    "施工": [
        Slot("site", "施工区域是否做了围挡？"),
        Slot("safety", "有无安全警示或防护？", REPORT_CLASS),
        Slot("impact", "是否影响行人或车辆通行？", REPORT_CLASS),
    ],
    "其他": [
        Slot("describe", "能再具体描述一下这个安全隐患是什么吗？"),
    ],
}


SUBCATEGORY_SLOT_SCHEMAS: dict[str, list[Slot]] = {
    "fire_lane_blocked": SLOT_SCHEMAS["消防通道"],
    "fire_equipment_fault": [
        Slot("facility_type", "具体是哪一类消防设施，例如消火栓、喷淋、报警器还是灭火器？"),
        Slot("condition", "目前是老旧、损坏还是完全无法使用？"),
        Slot("function_impact", "是否影响整栋建筑的消防报警或灭火功能？", REPORT_CLASS),
    ],
    "dangerous_building": SLOT_SCHEMAS["危房"],
    "wall_crack_lean": SLOT_SCHEMAS["危房"],
    "facade_fall": SLOT_SCHEMAS["高空坠物"],
    "falling_object": SLOT_SCHEMAS["高空坠物"],
    "illegal_structure": SLOT_SCHEMAS["其他"],
    "manhole_damage": SLOT_SCHEMAS["井盖/道路"],
    "road_surface_collapse": SLOT_SCHEMAS["井盖/道路"],
    "drainage_flood": SLOT_SCHEMAS["井盖/道路"],
    "street_light_pole": SLOT_SCHEMAS["其他"],
    "road_occupancy": SLOT_SCHEMAS["占道"],
    "vehicle_occupancy": SLOT_SCHEMAS["占道"],
    "blind_path_occupied": SLOT_SCHEMAS["占道"],
    "traffic_facility_damage": SLOT_SCHEMAS["其他"],
    "exposed_wire": SLOT_SCHEMAS["电气"],
    "distribution_box_fault": SLOT_SCHEMAS["电气"],
    "illegal_wiring": SLOT_SCHEMAS["电气"],
    "gas_leak": SLOT_SCHEMAS["其他"],
    "gas_pipe_aging": SLOT_SCHEMAS["其他"],
    "no_barrier": SLOT_SCHEMAS["施工"],
    "no_warning": SLOT_SCHEMAS["施工"],
    "scaffold_guard": SLOT_SCHEMAS["施工"],
    "deep_pit": SLOT_SCHEMAS["施工"],
    "temporary_power": SLOT_SCHEMAS["电气"],
    "elevator_trapped": SLOT_SCHEMAS["其他"],
    "elevator_stopped": SLOT_SCHEMAS["其他"],
    "elevator_inspection": SLOT_SCHEMAS["其他"],
    "garbage_pile": SLOT_SCHEMAS["其他"],
    "sewage_odor": SLOT_SCHEMAS["其他"],
    "other": SLOT_SCHEMAS["其他"],
}


def get_slot_schema(value: str) -> list[Slot]:
    """Resolve a slot profile from a subcategory code, legacy label, or major."""
    key = (value or "").strip()
    if key in SUBCATEGORY_SLOT_SCHEMAS:
        return SUBCATEGORY_SLOT_SCHEMAS[key]
    if key in SLOT_SCHEMAS:
        return SLOT_SCHEMAS[key]
    pair = normalize_taxonomy(key)
    if pair:
        subcategory = pair[1]
        if subcategory in SUBCATEGORY_SLOT_SCHEMAS:
            return SUBCATEGORY_SLOT_SCHEMAS[subcategory]
        major_label = MAJOR_LABELS.get(pair[0])
        if major_label in SLOT_SCHEMAS:
            return SLOT_SCHEMAS[major_label]
    return SLOT_SCHEMAS["其他"]


def _is_filled(filled, key: str) -> bool:
    return bool(str((filled or {}).get(key) or "").strip())


def unfilled_slots(value: str, filled, classes=REPORT_CLASSES) -> list[Slot]:
    """按 schema 书写顺序返回未填的槽位，只取指定类别。

    书写顺序 = 追问优先级（既有约定，见 dialogue_policy._question_for_missing）。
    """
    wanted = set(classes)
    return [
        slot for slot in get_slot_schema(value)
        if slot.value_class in wanted and not _is_filled(filled, slot.key)
    ]


def missing_decision_slots(value: str, filled) -> list[Slot]:
    """A 类（决策级）缺失 —— 决定要不要追问。"""
    return unfilled_slots(value, filled, (DECISION_CLASS,))


def missing_report_slots(value: str, filled) -> list[Slot]:
    """A+B 类缺失 —— 报告「仍需确认」的条件分支材料（阶段 4 消费）。"""
    return unfilled_slots(value, filled, REPORT_CLASSES)


def major_for_subcategory(subcategory_code: str) -> str:
    return SUBCATEGORY_TO_MAJOR.get(subcategory_code, "")
