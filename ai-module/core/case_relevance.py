"""检索结果的类别相关性过滤。

语料只覆盖 4 个旧类别（消防通道/占道/施工/井盖道路），而对话能识别 8 大类 31 小类。
检索是纯文本+向量匹配、不按类别过滤，所以对库里根本没有的隐患（户内燃气、危房、
裸露电线…）会返回"语义邻近但类别不同"的条目。

把它写进「类似案例」/「责任归属依据」是误导——比写「库内暂未检索到」更糟，
因为它看起来有依据。这里按大类把不同类的条目剔掉。
"""
import re

from core.hazard_taxonomy import normalize_taxonomy

_BLOCK = re.compile(r"(?=【(?:结果|法规)\d+】)")
_CATEGORY = re.compile(r"类别[:：]\s*([^\s|｜]+)")
_HAS_BLOCK = re.compile(r"【(?:结果|法规)\d+】")
NO_MATCH = "库内暂未检索到同类别的内容（检索到的条目属于其他类别，已剔除，不作为依据）"


def _major_of(label: str) -> str:
    pair = normalize_taxonomy(label)
    return pair[0] if pair else ""


def filter_by_major(text: str, major_code: str) -> str:
    """只保留与当前隐患同大类的结果块；一条都没剩就明确说没有。"""
    if not text or not major_code:
        return text
    if not _HAS_BLOCK.search(text):
        return text                      # 不是结果格式（报错/超时/空结果）→ 原样返回
    blocks = [b for b in _BLOCK.split(text) if b.strip()]
    # 只有带【结果N】/【法规N】的才算条目；前面那行标题不参与判定
    kept = []
    for block in blocks:
        found = _CATEGORY.search(block)
        # 判不出类别的一律不保留：不能确认同大类的东西，不许当依据
        if found and _major_of(found.group(1)) == major_code:
            kept.append(block)
    if not kept:
        return NO_MATCH
    return "".join(kept).strip()
