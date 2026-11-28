# -*- coding: utf-8 -*-
"""Shared hazard slot definitions for dialogue routing and planning.

槽位按「缺了它，什么会错」分两类，替代原来的 critical 布尔：

  A 决策级 — 缺了它，**风险等级或用户/系统该采取的动作会判错**
            （包括该不该立即处置、该找谁处置） → 追问（进 missing）
  B 报告级 — 结论与动作不变，但**法规适用/责任归属/处罚档次**会不同
            → 不追问，进报告的「仍需确认」条件分支（阶段 4 消费）
逐槽判据见 docs/superpowers/specs/2026-09-27-slot-value-classes-design.md。
**这是初判，需要人工复核**：A/B 的边界（「动作会错」vs「责任归属不同」）
本身是判断，不是事实。

要求「至少 5 个小类的逐槽样例」，见 spec；这里给出三套作为速查：

  占道 / road_occupancy        behavior=B（管辖主体与法规不同）
                               persistence=A（长期→上报处置；临时→现场劝离）
                               blocked=A（完全堵死→通行中断，需立即处置）
  危房 / dangerous_building    structure=A（整体倾斜 vs 局部开裂，危险程度不同）
                               occupancy=A（有人住→需疏散；无人→围挡隔离）
  消防通道 / fire_lane_blocked blocker=A（可燃堆物→火灾风险高；车辆→阻碍通行）
                               persistence=A（长期占用→需执法；临时→可劝离）
                               impact=B（是否影响消防车通行 → 整改要求不同）
"""

from dataclasses import dataclass

from core.hazard_taxonomy import MAJOR_LABELS, SUBCATEGORY_TO_MAJOR, normalize_taxonomy

DECISION_CLASS = "A"
REPORT_CLASS = "B"
VALUE_CLASSES = (DECISION_CLASS, REPORT_CLASS)
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
        Slot("structure", "房屋有没有墙体开裂、整体倾斜、地基沉降或承重构件变形？"),
        Slot("occupancy", "现在有人在里面居住或使用吗？"),
    ],
    "消防通道": [
        Slot("blocker", "被什么东西占用了？"),
        Slot("persistence", "是长期还是临时？"),
        Slot("impact", "是否影响消防车或人员通行？", REPORT_CLASS),
    ],
    "消防设施": [
        Slot("facility_type", "具体是哪一类消防设施，例如消火栓、喷淋、报警器、灭火器，还是消防水池/管网/室外消火栓？"),
        Slot("condition", "目前是老旧、损坏、无水无压、被埋压，还是完全无法使用？"),
        Slot("function_impact", "是否影响整栋建筑的消防报警或灭火供水功能？", REPORT_CLASS),
    ],
    "高空坠物": [
        Slot("source", "坠落来源是什么：外墙瓷砖/抹灰/幕墙、外挂空调/广告牌/花盆，还是人为高空抛物？"),
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
    "fire_equipment_fault": SLOT_SCHEMAS["消防设施"],
    "dangerous_building": SLOT_SCHEMAS["危房"],
    "ebike_hazard": [
        Slot("hazard_mode", "电动自行车是停在楼道/电梯/架空层并充电、电池带入室内，还是飞线充电？"),
        Slot("charging_state", "现场是否正在通电充电，或有电池发热、冒烟、鼓包、改装迹象？"),
    ],
    "tree_fall_hazard": [
        Slot("tree_state", "树木是已倒伏阻断道路/压线，还是严重倾斜、大枯枝悬垂？"),
        Slot("impact_target", "下方或周边是人行道、车位还是架空线缆？", REPORT_CLASS),
    ],
    "confined_space": [
        Slot("space_type", "具体是化粪池、污水井、地下管廊、泵站还是储罐？"),
        Slot("protection", "作业前是否已强制通风、气体检测并配备监护防护装备？"),
    ],
    "hazmat_storage": [
        Slot("material_info", "现场是不明化工桶、易燃溶剂、液化气瓶还是烟花爆竹，是否密封？"),
        Slot("environment", "存放点通风如何，周边有无居民楼、火源或人员接触风险？"),
    ],
    "falling_object": SLOT_SCHEMAS["高空坠物"],
    "illegal_structure": [
        Slot("structure_detail", "具体搭建了什么、占用在哪个公共部位？"),
        Slot("structural_impact", "是否拆改承重结构、造成超载或影响消防疏散？"),
    ],
    "manhole_damage": SLOT_SCHEMAS["井盖/道路"],
    "road_surface_collapse": [
        Slot("collapse_scale", "塌陷范围多大、深浅如何，下方是否可见空洞？"),
        Slot("isolation", "现场是否已设置警戒线和围挡？"),
    ],
    "drainage_flood": [
        Slot("flood_depth", "积水大概有多深，是否已经阻断通行？"),
        Slot("location_type", "积水点在隧道、普通道路还是地下车库？", REPORT_CLASS),
    ],
    "street_light_pole": [
        Slot("pole_status", "是灯杆倾斜折断，还是路灯不亮？"),
        Slot("electric_risk", "周边是否有积水、漏电或线缆外露风险？"),
    ],
    "road_occupancy": SLOT_SCHEMAS["占道"],
    "vehicle_occupancy": [
        Slot("persistence", "是长期占用还是临时停放？"),
        Slot("blocked", "是完全堵死还是仍可通行？"),
    ],
    "blind_path_occupied": [
        Slot("blocker", "盲道被什么占用，是车辆、摊位还是其他物品？"),
        Slot("blocked", "是完全阻断还是部分占用？"),
    ],
    "traffic_facility_damage": [
        Slot("facility_type", "损坏的是信号灯、护栏、交通标志还是标线？"),
        Slot("condition", "目前是缺失、破损、歪斜还是完全失效？"),
    ],
    "exposed_wire": SLOT_SCHEMAS["电气"],
    "distribution_box_fault": SLOT_SCHEMAS["电气"],
    "illegal_wiring": SLOT_SCHEMAS["电气"],
    "gas_leak": [
        Slot("leak_sign", "是闻到煤气味、听到漏气声，还是看到气泡或结霜？"),
        Slot("ventilation", "现场是否通风，周边有无火源或电气设备？"),
    ],
    "gas_pipe_aging": [
        Slot("pipe_condition", "管道是锈蚀、漆面剥落、接口变形还是已经渗漏？"),
        Slot("leak_suspect", "周边是否有持续气味、气泡或其他疑似漏气迹象？"),
    ],
    "no_barrier": [
        Slot("site", "是完全缺少硬质围挡，还是围挡有破损缺口？"),
        Slot("impact", "施工点紧邻人行道、机动车道还是学校出入口？", REPORT_CLASS),
    ],
    "no_warning": [
        Slot("warning_status", "是完全没有任何警示，还是缺夜间反光灯或围挡标志？"),
        Slot("impact", "路段车速和夜间行人暴露情况如何？", REPORT_CLASS),
    ],
    "scaffold_guard": [
        Slot("defect", "是脚手架连墙件失稳，还是临边护栏/安全网缺失？"),
        Slot("exposure", "现场是否仍有高处作业或下方有行人通行？"),
    ],
    "deep_pit": [
        Slot("pit_status", "是否出现支护位移、渗水或坑边超载堆料？"),
        Slot("isolation", "周边是否已设置防护栏杆和警戒区？"),
    ],
    "temporary_power": SLOT_SCHEMAS["电气"],
    "elevator_trapped": [
        Slot("trapped_state", "轿厢里是否有人被困，是否有受伤、缺氧或恐慌？"),
        Slot("duration", "已经被困多长时间？", REPORT_CLASS),
    ],
    "elevator_stopped": [
        Slot("fault_symptom", "是停运、异响、冲顶蹲底还是停层不准？"),
        Slot("occupancy", "轿厢内是否有人，门是否能正常打开？"),
    ],
    "elevator_inspection": [
        Slot("equipment_status", "检验标志是否过期、缺失，或最近是否长期未维保？"),
        Slot("equipment_type", "是乘客电梯、载货电梯还是自动扶梯？", REPORT_CLASS),
    ],
    "garbage_pile": [
        Slot("waste_type", "堆积的是生活垃圾、建筑垃圾还是可燃杂物？"),
        Slot("impact", "是否堵塞通道、影响消防或产生异味和病媒风险？"),
    ],
    "sewage_odor": [
        Slot("sewage_source", "异味/污水来自下水道、污水井还是经营场所？"),
        Slot("impact", "是否流入公共区域、污染水源或影响行人商户？", REPORT_CLASS),
    ],
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
