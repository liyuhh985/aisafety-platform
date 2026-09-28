# -*- coding: utf-8 -*-
"""「只输出增量」的客观判据（评测用，不进生产路径）。

它回答两个问题：
  1. 第 2 轮报告与第 1 轮的**重合度**是多少（越低越像增量）；
  2. 第 2 轮引用的法规条目与第 1 轮**是否矛盾**。

为什么要单独写它：按统一原则「代码能兜的要有客观判据」，而这里恰恰是**兜不住**的那类 ——
所以它不参与生产兜底，只把「有没有重复 / 有没有矛盾」变成可以看的数字。

诚实说明（别当硬指标用）：字符 bigram 重合度是**脆**的 —— 它把「用词相似」当「内容重复」，
反过来「换个说法把同一份分析重讲一遍」它抓不到。G1 的启发式判定就是前车之鉴
（同一批数据，脚本 3/10、人工 5/10）。所以测量脚本一律同时打印原文，人工复核必须做。
"""
import re

_CITATION = re.compile(r"《[^《》]{2,40}》")
_ARTICLE = re.compile(r"第[0-9一二三四五六七八九十百零]+条")
_PUNCT = re.compile(r"[\s，。、；：！？（）()「」\"'\-—,.!?;:]+")


def normalize(text) -> str:
    return _PUNCT.sub("", str(text or ""))


def bigrams(text) -> set:
    value = normalize(text)
    if len(value) < 2:
        return {value} if value else set()
    return {value[i:i + 2] for i in range(len(value) - 1)}


def overlap_ratio(first, second) -> float:
    """字符 bigram 的 Jaccard 相似度（0~1）。0 = 没有一点共同措辞。"""
    left, right = bigrams(first), bigrams(second)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


_SENTENCE_SPLIT = re.compile(r"[^。！？\n]+[。！？\n]?")


def sentences(text) -> list:
    return [s.strip() for s in _SENTENCE_SPLIT.findall(str(text or "")) if s.strip()]


def duplicated_sentence_ratio(first, second, threshold: float = 0.5) -> dict:
    """第 2 轮里有多少句在重讲第 1 轮：逐句取与第 1 轮各句的最大重合度。

    比整篇重合度好读：它回答「第 2 轮到底有几句话是旧内容」，而不是一个混合了
    篇幅、措辞和结构的单值。阈值默认 0.5 —— 刻意偏高，宁可漏判也不把
    「引用前轮结论的一句话带过」（那正是我们要的行为）算成重复。
    """
    base = sentences(first)
    second_sentences = sentences(second)
    hits = []
    for sentence in second_sentences:
        best = max((overlap_ratio(sentence, item) for item in base), default=0.0)
        if best >= threshold:
            hits.append({"sentence": sentence, "best": round(best, 3)})
    total = len(second_sentences)
    return {
        "total": total,
        "duplicated": len(hits),
        "ratio": (len(hits) / total) if total else 0.0,
        "hits": hits,
    }


def regulation_citations(text) -> list:
    """抽出现文里的法规引用：《…》 以及紧随其后的「第X条」（按出现顺序、去重）。"""
    value = str(text or "")
    found = []
    for match in _CITATION.finditer(value):
        tail = value[match.end():match.end() + 24]
        article = _ARTICLE.search(tail)
        item = match.group(0) + (article.group(0) if article else "")
        if item not in found:
            found.append(item)
    return found


def citation_report(first, second) -> dict:
    """两轮法规引用对照：共同 / 只在第 1 轮 / 只在第 2 轮。"""
    a, b = regulation_citations(first), regulation_citations(second)
    return {
        "first": a,
        "second": b,
        "shared": [x for x in b if x in a],
        "only_first": [x for x in a if x not in b],
        "only_second": [x for x in b if x not in a],
    }