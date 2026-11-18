"""状态文案契约：短、非空、不自夸，且每个图节点都要有文案。

最后一条是防回归 —— 拆节点/加节点时忘了补 STATUS_TEXT，前端就会拿到空状态。
"""
import pytest

from core import assistant_graph as ag
from core.hazard_taxonomy import SUBCATEGORY_LABELS

GRAPH_SPECIAL = {"__start__", "__end__"}


def _graph_node_names():
    return set(ag.build_graph().get_graph().nodes) - GRAPH_SPECIAL


def test_every_graph_node_has_status_text():
    missing = sorted(_graph_node_names() - set(ag.STATUS_TEXT))
    assert missing == [], "这些节点没有状态文案，前端会拿到空状态：" + str(missing)


def test_status_text_has_no_orphan_keys():
    orphan = sorted(set(ag.STATUS_TEXT) - _graph_node_names())
    assert orphan == [], "这些文案对应的节点已经不存在：" + str(orphan)


@pytest.mark.parametrize("node", sorted(ag.STATUS_TEXT))
def test_status_text_is_short_and_non_empty(node):
    text = ag.status_text(node, {})
    assert text.strip()
    assert len(text) <= ag.STATUS_MAX_LENGTH, (node, text, len(text))


@pytest.mark.parametrize("node", sorted(ag.STATUS_TEXT))
def test_status_text_has_no_marketing_words(node):
    text = ag.status_text(node, {})
    for banned in ag.STATUS_BANNED_WORDS:
        assert banned not in text, (node, banned)


def test_retrieve_status_carries_the_category_label():
    text = ag.status_text("retrieve", {"category_results": {"fire_lane_blocked": {}}})
    assert SUBCATEGORY_LABELS["fire_lane_blocked"] in text


def test_retrieve_status_survives_missing_context():
    text = ag.status_text("retrieve", {})
    assert text.strip()
    assert "{" not in text
    assert len(text) <= ag.STATUS_MAX_LENGTH


def test_retrieve_status_fits_with_the_longest_label():
    longest_code = max(SUBCATEGORY_LABELS, key=lambda code: len(SUBCATEGORY_LABELS[code]))
    text = ag.status_text("retrieve", {"category_results": {longest_code: {}}})
    assert len(text) <= ag.STATUS_MAX_LENGTH


def test_unknown_node_falls_back_instead_of_raising():
    assert ag.status_text("no_such_node", {}) == "处理中..."


def test_reply_nodes_each_have_their_own_text():
    for node in ("boundary_reply", "smalltalk_reply", "answer_reply", "fallback_reply"):
        assert ag.STATUS_TEXT[node].strip()
