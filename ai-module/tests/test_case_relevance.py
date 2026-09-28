"""检索结果按大类过滤：不相关的条目不能当"类似案例/法规依据"。"""
from core.case_relevance import NO_MATCH, filter_by_major

CASES = """=== 混合检索结果: 「燃气泄漏」===
【结果1】[语义匹配] 施工挖破天然气管道
  类别: 施工 | 城市: 梅州
  描述: 市政施工挖破天然气预留管道造成燃气泄漏
【结果2】[关键词匹配] 小区消防通道被堵
  类别: 消防通道 | 城市: 深圳
  描述: 通道被占延误救援"""

REGS = """=== 混合检索结果: 「燃气泄漏」===
【法规1】[语义匹配] 城镇燃气管理条例
  类别: 施工
  内容: 燃气经营者应当定期检查
【法规2】[关键词匹配] 消防法第二十八条
  类别: 消防通道
  内容: 不得占用疏散通道"""


def test_keeps_the_same_major_block():
    kept = filter_by_major(CASES, "construction")
    assert "施工挖破天然气管道" in kept
    assert "消防通道被堵" not in kept


def test_drops_everything_when_no_block_matches():
    assert filter_by_major(CASES, "building") == NO_MATCH


def test_regulation_format_works_too():
    kept = filter_by_major(REGS, "construction")
    assert "城镇燃气管理条例" in kept
    assert "消防法第二十八条" not in kept


def test_an_unverifiable_category_is_not_used_as_evidence():
    """判不出类别 = 不能确认同大类 → 不保留（宁可写"没检索到"）。"""
    for text in ("【结果1】[语义匹配] 某案例\n  类别: 说不清的类别\n  描述: x",
                 "【结果1】[语义匹配] 某案例\n  描述: 没有类别行"):
        assert filter_by_major(text, "construction") == NO_MATCH


def test_error_and_timeout_text_is_untouched():
    for text in ("[案例检索失败] timeout，请不要重试",
                 "未找到与「燃气泄漏」相关的结果。",
                 "tb_hazard_case retrieval timeout（检索超时），暂未返回结果。"):
        assert filter_by_major(text, "construction") == text


def test_empty_major_leaves_text_alone():
    assert filter_by_major(CASES, "") == CASES


def test_issue_blocks_drops_off_major_retrieval(monkeypatch):
    """接进报告：不同大类的检索结果不能出现在给模型的材料里。"""
    import core.assistant_graph as ag

    captured = {}

    def fake_stream(messages, cancellation=None):
        captured["prompt"] = messages[-1]["content"]
        yield ("chunk", "BODY")

    monkeypatch.setattr(ag._report_llm, "_call_llm_stream_events", fake_stream)
    monkeypatch.setattr(ag, "get_stream_writer", lambda: None)
    ag.report({
        "messages": [],
        "issues": [{"major_code": "utility", "subcategory_code": "gas_leak",
                    "slots": {"source": "管道"}, "missing": []}],
        "categories": ["gas_leak"],
        "category_results": {"gas_leak": {"regulation": REGS, "case": CASES}},
        "missing": [], "report_mode": "full", "premises_scope": "indoor_risk",
    })
    prompt = captured["prompt"]
    assert "城镇燃气管理条例" not in prompt      # 施工类的法规被剔掉
    assert "消防法第二十八条" not in prompt
    assert NO_MATCH in prompt
