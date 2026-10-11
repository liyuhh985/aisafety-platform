# -*- coding: utf-8 -*-
"""「增量」判据的纯函数单测：不联网、不调模型。

这些指标是**评测用**的，用来把「有没有重复 / 有没有矛盾」变成可以看的数字；
它们不参与生产兜底（内容重复没有客观判据，见模块注释里的诚实说明）。
"""
import pytest

from eval.eval_increment import (bigrams, citation_report, duplicated_sentence_ratio,
                            overlap_ratio, regulation_citations, sentences)


# ---------- 重合度 ----------

def test_identical_text_overlaps_completely():
    assert overlap_ratio("消防通道被私家车占用", "消防通道被私家车占用") == 1.0


def test_unrelated_text_has_no_overlap():
    assert overlap_ratio("消防通道被私家车占用", "燃气管道老化漏气") == 0.0


def test_partial_overlap_is_between_zero_and_one():
    ratio = overlap_ratio("楼下消防通道被杂物长期占用，属于违法行为。",
                          "通道被杂物占用，仍需确认占用物。")
    assert 0.0 < ratio < 1.0


def test_empty_input_is_zero_not_an_error():
    assert overlap_ratio("", "有内容") == 0.0
    assert overlap_ratio("有内容", "") == 0.0
    assert overlap_ratio(None, None) == 0.0


def test_punctuation_and_whitespace_do_not_count():
    assert overlap_ratio("通道被占。", "通道 被占！") == 1.0


def test_bigrams_of_a_single_character():
    assert bigrams("占") == {"占"}
    assert bigrams("") == set()


# ---------- 法规引用 ----------

def test_citations_extract_book_title_with_article():
    found = regulation_citations("依据《中华人民共和国消防法》第28条，任何人不得占用消防通道。")
    assert found == ["《中华人民共和国消防法》第28条"]


def test_citations_without_article():
    assert regulation_citations("见《城市道路管理条例》") == ["《城市道路管理条例》"]


def test_citations_are_deduped_and_ordered():
    text = "《消防法》第28条 说过；另外《消防法》第28条 再提一次；还有《民法典》第1254条。"
    assert regulation_citations(text) == ["《消防法》第28条", "《民法典》第1254条"]


def test_no_citation_returns_empty():
    assert regulation_citations("通道被占了，建议尽快清理。") == []


def test_citation_report_splits_shared_and_unique():
    report = citation_report("《消防法》第28条", "《消防法》第28条 与 《城市道路管理条例》第2条")
    assert report["shared"] == ["《消防法》第28条"]
    assert report["only_first"] == []
    assert report["only_second"] == ["《城市道路管理条例》第2条"]


def test_citation_report_flags_a_missing_reference():
    report = citation_report("《消防法》第28条 与 《民法典》第1254条", "《消防法》第28条")
    assert report["only_first"] == ["《民法典》第1254条"]
    assert report["only_second"] == []

# ---------- 逐句重复率 ----------

def test_sentences_split_on_chinese_punctuation():
    assert sentences("通道被占。建议清理！长期堆放？") == ["通道被占。", "建议清理！", "长期堆放？"]


def test_duplicated_sentence_ratio_counts_restated_sentences():
    first = "楼下消防通道被杂物占用，属于违法行为。建议先拍照留证。"
    second = "楼下消防通道被杂物占用，属于违法行为。建议先拍照留证。本轮新增：可拨打 12345。"
    stat = duplicated_sentence_ratio(first, second)
    assert stat["total"] == 3
    assert stat["duplicated"] == 2
    assert 0.6 < stat["ratio"] < 0.7


def test_rewording_is_not_counted_as_duplication():
    """这是这个指标的已知盲区，写成测试是为了别把它当硬指标用。

    实测（db/eval_increment_turns.txt）：第 2 轮把同一份分析换个说法重讲，
    整篇重合度 0.162、逐句重复率 0.00 —— 两个客观指标都抓不住内容重复。
    """
    first = "楼下消防通道被杂物占用，属于违法行为。"
    second = "消防车通道被物品堵住，这事儿是违法的。"
    assert duplicated_sentence_ratio(first, second)["duplicated"] == 0
    assert overlap_ratio(first, second) < 0.5


def test_empty_second_text_is_zero():
    stat = duplicated_sentence_ratio("有内容。", "")
    assert stat == {"total": 0, "duplicated": 0, "ratio": 0.0, "hits": []}
