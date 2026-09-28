"""Shared hazard-category boundaries for dialogue and task creation."""

from core.hazard_taxonomy import ALL_SUBCATEGORY_CODES

CONSULT_CATEGORIES = (
    "占道", "危房", "消防通道", "消防设施", "高空坠物", "井盖/道路", "电气", "施工", "其他"
)

SUBMIT_CATEGORIES = tuple(sorted(ALL_SUBCATEGORY_CODES))

VISION_CATEGORY_MAP = {
    "消防安全": "消防通道", "消防": "消防通道",
    "消防设施": "消防设施", "消防设施故障": "消防设施",
    "建筑施工": "施工", "施工": "施工",
    "交通安全": "井盖/道路", "道路交通": "井盖/道路",
    "占道经营": "占道", "占道": "占道",
    "建筑结构": "危房", "危房": "危房",
    "高空坠物": "高空坠物",
    "电气安全": "电气", "用电安全": "电气", "电气": "电气",
}


def normalize_vision_category(category: str) -> str:
    """Map a vision label to a dialogue category without overclaiming support."""
    value = (category or "").strip()
    return VISION_CATEGORY_MAP.get(value, "其他")
