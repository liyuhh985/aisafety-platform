"""多类别版自适应槽位核心测试（替代旧单类别 test_adaptive_slots）。"""
from langchain_core.messages import HumanMessage
import core.assistant_graph as ag
from core.assistant_graph import _infer_categories, _pick_keyword, _merge_categories


def test_infer_categories_zhandao_no_llm(monkeypatch):
    monkeypatch.setattr(ag, "_llm_classify", lambda t: (_ for _ in ()).throw(AssertionError("清晰场景不应调 LLM")))
    cats = _infer_categories("长期占着盲道完全堵死")
    assert "占道" in cats


def test_infer_categories_weifang_no_llm(monkeypatch):
    monkeypatch.setattr(ag, "_llm_classify", lambda t: (_ for _ in ()).throw(AssertionError("清晰场景不应调 LLM")))
    cats = _infer_categories("危房有裂缝，很危险")
    assert "危房" in cats


def test_infer_categories_two_hits_no_llm(monkeypatch):
    monkeypatch.setattr(ag, "_llm_classify", lambda t: (_ for _ in ()).throw(AssertionError("双命中不该调 LLM")))
    cats = _infer_categories("消防被堵，长期占道")
    assert "消防通道" in cats and "占道" in cats
    assert cats.index("消防通道") < cats.index("占道")  # 优先级消防(1)<占道(5)


def test_pick_keyword_category():
    kw = _pick_keyword("危房", {"structure": "裂缝"})
    assert "危房" in kw and "裂缝" in kw


def test_merge_categories_dedupe_sort():
    merged = _merge_categories(["占道", "消防通道"], ["占道", "危房"])
    assert merged[0] == "危房"
    assert merged.count("占道") == 1
    assert merged[-1] == "占道"


def test_existing_category_not_duplicated():
    # 已存在的类别再次识别，合并后不重复
    cats = _merge_categories(["占道"], ["占道", "消防通道"])
    assert cats.count("占道") == 1
    assert cats == ["消防通道", "占道"]


def test_cross_slot_map_has_blocked_to_impact():
    assert ag.CROSS_SLOT_MAP.get(("占道", "blocked")) == ("消防通道", "impact")