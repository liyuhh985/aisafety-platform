"""Canonical two-level hazard taxonomy shared by dialogue and task creation."""

HAZARD_TAXONOMY = (
    {
        "code": "traffic",
        "label": "交通与通行",
        "subcategories": (
            ("road_occupancy", "占道经营/乱堆乱放"),
            ("vehicle_occupancy", "车辆占道"),
            ("blind_path_occupied", "盲道占用"),
            ("traffic_facility_damage", "交通设施损坏"),
        ),
    },
    {
        "code": "municipal",
        "label": "市政设施",
        "subcategories": (
            ("manhole_damage", "井盖缺失/破损"),
            ("road_surface_collapse", "路面塌陷"),
            ("drainage_flood", "排水/积水"),
            ("street_light_pole", "路灯/线杆损坏"),
            ("tree_fall_hazard", "树木倒伏/断枝风险"),
        ),
    },
    {
        "code": "fire",
        "label": "消防安全",
        "subcategories": (
            ("fire_lane_blocked", "消防通道占用"),
            ("fire_equipment_fault", "消防设施故障"),
            ("ebike_hazard", "电动自行车违规停放/充电"),
        ),
    },
    {
        "code": "building",
        "label": "建筑安全",
        "subcategories": (
            ("dangerous_building", "危房"),
            ("falling_object", "高空坠物"),
            ("illegal_structure", "违规搭建"),
        ),
    },
    {
        "code": "utility",
        "label": "电气与燃气",
        "subcategories": (
            ("exposed_wire", "裸露/老化电线"),
            ("distribution_box_fault", "配电设施故障"),
            ("illegal_wiring", "私拉乱接"),
            ("gas_leak", "燃气泄漏"),
            ("gas_pipe_aging", "燃气管道老化"),
        ),
    },
    {
        "code": "construction",
        "label": "施工安全",
        "subcategories": (
            ("no_barrier", "未设置围挡"),
            ("no_warning", "无安全警示"),
            ("scaffold_guard", "脚手架/临边防护"),
            ("deep_pit", "深基坑风险"),
            ("temporary_power", "施工临时用电"),
            ("confined_space", "有限空间作业风险"),
        ),
    },
    {
        "code": "elevator_special",
        "label": "电梯与特种设备",
        "subcategories": (
            ("elevator_trapped", "电梯困人"),
            ("elevator_stopped", "停运/异响"),
            ("elevator_inspection", "超期未检"),
        ),
    },
    {
        "code": "environment_other",
        "label": "环境与其他",
        "subcategories": (
            ("garbage_pile", "垃圾堆积"),
            ("sewage_odor", "污水/异味"),
            ("hazmat_storage", "危化品/易燃易爆违规存运"),
            ("other", "其他"),
        ),
    },
)

HAZARD_TYPE_MAX_LENGTH = 64

MAJOR_LABELS = {item["code"]: item["label"] for item in HAZARD_TAXONOMY}
MAJOR_LABEL_TO_CODE = {label: code for code, label in MAJOR_LABELS.items()}
SUBCATEGORY_LABELS = {
    sub_code: sub_label
    for item in HAZARD_TAXONOMY
    for sub_code, sub_label in item["subcategories"]
}
SUBCATEGORY_LABEL_TO_CODE = {
    label: code for code, label in SUBCATEGORY_LABELS.items()
}
SUBCATEGORY_TO_MAJOR = {
    sub_code: item["code"]
    for item in HAZARD_TAXONOMY
    for sub_code, _ in item["subcategories"]
}
HIGH_RISK_SUBCATEGORIES = frozenset({
    "fire_lane_blocked", "fire_equipment_fault", "ebike_hazard",
    "dangerous_building", "falling_object",
    "exposed_wire", "distribution_box_fault", "illegal_wiring", "gas_leak", "gas_pipe_aging",
    "road_surface_collapse", "scaffold_guard", "deep_pit", "temporary_power",
    "confined_space", "elevator_trapped", "hazmat_storage",
})
MEDIUM_RISK_SUBCATEGORIES = frozenset({
    "road_occupancy", "vehicle_occupancy", "blind_path_occupied", "traffic_facility_damage",
    "manhole_damage", "drainage_flood", "street_light_pole", "tree_fall_hazard",
    "illegal_structure", "no_barrier", "no_warning",
    "elevator_stopped", "elevator_inspection", "sewage_odor", "other",
})
LOW_RISK_SUBCATEGORIES = frozenset({"garbage_pile"})
SUBCATEGORY_DEFAULT_RISK = {
    **{code: "high" for code in HIGH_RISK_SUBCATEGORIES},
    **{code: "medium" for code in MEDIUM_RISK_SUBCATEGORIES},
    **{code: "low" for code in LOW_RISK_SUBCATEGORIES},
}
assert set(SUBCATEGORY_DEFAULT_RISK) == set(SUBCATEGORY_LABELS)

ALL_SUBCATEGORY_CODES = frozenset(SUBCATEGORY_LABELS)

LEGACY_CATEGORY_MAP = {
    "占道": ("traffic", "road_occupancy"),
    "井盖/道路": ("municipal", "manhole_damage"),
    "消防通道": ("fire", "fire_lane_blocked"),
    "消防设施": ("fire", "fire_equipment_fault"),
    "危房": ("building", "dangerous_building"),
    "高空坠物": ("building", "falling_object"),
    "电气": ("utility", "exposed_wire"),
    "施工": ("construction", "no_barrier"),
    "其他": ("environment_other", "other"),
}


def _normalize_subcategory(value: str):
    code = (value or "").strip()
    if not code:
        return None
    if code in SUBCATEGORY_LABELS:
        return code
    return SUBCATEGORY_LABEL_TO_CODE.get(code)


def normalize_taxonomy(value: str):
    """Resolve a legacy label, label, code, or major/sub value to canonical codes."""
    text = (value or "").strip()
    if not text:
        return None
    if text in LEGACY_CATEGORY_MAP:
        return LEGACY_CATEGORY_MAP[text]
    if "/" in text:
        _, subcategory = text.split("/", 1)
        sub_code = _normalize_subcategory(subcategory)
        if sub_code:
            return SUBCATEGORY_TO_MAJOR[sub_code], sub_code
    sub_code = _normalize_subcategory(text)
    if sub_code:
        return SUBCATEGORY_TO_MAJOR[sub_code], sub_code
    return None


def format_hazard_type(major_code: str, subcategory_code: str) -> str:
    pair = normalize_taxonomy(f"{major_code}/{subcategory_code}")
    if not pair:
        return ""
    return f"{pair[0]}/{pair[1]}"


def parse_hazard_type(value: str):
    return normalize_taxonomy(value)
