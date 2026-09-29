"""Assistant 工具单测：验证 search_cases / search_regulation 返回非空且来自真实表"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from tools.assistant_tools import ASSISTANT_TOOLS


def _find(name):
    return next(t for t in ASSISTANT_TOOLS if t.name == name)


def test_tools_registered():
    names = [t.name for t in ASSISTANT_TOOLS]
    assert "search_cases" in names
    assert "search_regulation" in names


def test_search_cases_returns_content():
    tool = _find("search_cases")
    result = tool.execute(keyword="盲道被占")
    assert isinstance(result, str)
    assert "事故" in result or "案例" in result or "检索" in result or "城市" in result or "判决" in result


def test_search_regulation_returns_content():
    tool = _find("search_regulation")
    result = tool.execute(keyword="盲道")
    assert isinstance(result, str)
    assert "法规" in result or "检索" in result or "条例" in result or "法" in result


def test_empty_keyword_guard():
    tool = _find("search_cases")
    result = tool.execute(keyword="")
    assert "关键词为空" in result
