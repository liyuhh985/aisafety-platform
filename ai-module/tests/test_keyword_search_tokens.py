"""keyword_search 分词/打分 + _merge_results 合并顺序的单测：不连数据库。

背景（实测）：
- 改动前 `keyword_search` 是 `LIKE '%整串%'`，生产传进来的是「小类标签 + 槽位值」，
  槽位一多就恒为 0 命中 → 混合检索退化成纯向量检索。
- 现在按空白/顿号切 token 做 OR 召回，宽候选在 Python 里按"命中数 → 标题字段 → id"排序。
- **刻意不丢类别标签 token**：标签命中 category 就是在做同小类过滤，是纯向量给不了的
  精度（实测丢掉后槽位空那组 Hit@5 1.000→0.938、MRR 0.984→0.854）。标签块会占住前排
  的问题改在合并顺序里解决 —— 向量在前、关键词只补尾部名额。
"""
import unittest
from unittest import mock

from tools import hybrid_search
from tools.hybrid_search import (
    _tokenize_keyword,
    _KEYWORD_SCAN_CAP,
    HybridSearcher,
)

CASE_COLUMNS = ("id", "title", "description", "category", "severity", "city",
                "casualties", "cause", "rectification", "regulation_ref", "verdict")


def case_row(case_id=1, title="标题", description="描述", category="消防安全/消防通道占用"):
    return (case_id, title, description, category, "一般", "深圳", "0", "原因",
            "整改", "法规", "判决")


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, list(params or [])))

    def fetchall(self):
        return list(self.rows)

    @property
    def sql(self):
        return self.calls[-1][0] if self.calls else ""

    @property
    def params(self):
        return self.calls[-1][1] if self.calls else []

    @property
    def patterns(self):
        return {p for p in self.params if isinstance(p, str)}


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


class KeywordSearchTokenTests(unittest.TestCase):
    def setUp(self):
        # keyword_search 不用到实例状态，直接绕开 embedding 缓存加载。
        self.searcher = HybridSearcher.__new__(HybridSearcher)
        self.cursor = FakeCursor([case_row()])
        self.conn = FakeConnection(self.cursor)

    def _patch_db(self):
        return mock.patch.object(hybrid_search, "_mysql_connection",
                                return_value=(self.conn, self.conn.close))

    def _forbid_db(self):
        def boom(*args, **kwargs):
            raise AssertionError("不该连数据库（空串 / 无 token）")
        return mock.patch.object(hybrid_search, "_mysql_connection", boom)

    # ---- 分词 ----

    def test_label_token_is_kept(self):
        self.assertEqual(_tokenize_keyword("消防通道占用"),
                         ["消防通道占用"])
        self.assertEqual(_tokenize_keyword("消防通道占用 私家车"),
                         ["消防通道占用", "私家车"])

    def test_punctuation_splits_and_short_tokens_are_dropped(self):
        self.assertEqual(_tokenize_keyword("消防通道占用 私家车、杂物"),
                         ["消防通道占用", "私家车", "杂物"])
        self.assertEqual(_tokenize_keyword("井盖缺失/破损 的 移位"),
                         ["井盖缺失/破损", "移位"])

    def test_slash_inside_a_label_is_not_split(self):
        self.assertEqual(_tokenize_keyword("排水/积水 积水"),
                         ["排水/积水", "积水"])

    def test_tokens_are_deduplicated(self):
        self.assertEqual(_tokenize_keyword("移位 移位 塌陷"), ["移位", "塌陷"])

    # ---- 空串：不连库、返回 [] ----

    def test_empty_keyword_returns_empty_without_touching_db(self):
        with self._forbid_db():
            self.assertEqual(self.searcher.keyword_search("", "tb_hazard_case"), [])
            self.assertEqual(self.searcher.keyword_search("   ", "tb_hazard_case"), [])
            self.assertEqual(self.searcher.keyword_search(None, "tb_hazard_case"), [])
            self.assertEqual(self.searcher.keyword_search(" 的 ", "tb_regulation"), [])

    # ---- SQL 组装 ----

    def test_sql_carries_every_token_including_the_label(self):
        with self._patch_db():
            self.searcher.keyword_search("消防通道占用 私家车", "tb_hazard_case")
        # 案例表 3 个检索字段 × 2 个 token
        self.assertEqual(self.cursor.patterns, {"%消防通道占用%", "%私家车%"})
        self.assertTrue(self.cursor.sql.startswith(
            "SELECT id, title, description, category"))
        self.assertIn("ORDER BY id ASC", self.cursor.sql)
        self.assertEqual(self.cursor.params[-1], _KEYWORD_SCAN_CAP)

    def test_indoor_obligation_hint_is_searched_too(self):
        with self._patch_db():
            self.searcher.keyword_search("燃气泄漏 管道 维护 责任", "tb_hazard_case")
        self.assertEqual(self.cursor.patterns,
                         {"%燃气泄漏%", "%管道%", "%维护%", "%责任%"})

    def test_like_wildcards_in_token_are_escaped(self):
        with self._patch_db():
            self.searcher.keyword_search("消防通道占用 100%_up", "tb_hazard_case")
        self.assertIn("%100\\%\\_up%", self.cursor.patterns)

    def test_regulation_branch_searches_law_name_and_keywords(self):
        self.cursor.rows = [(7, "中华人民共和国消防法", "第六十条", "占用消防通道",
                             "消防", "消防,通道")]
        with self._patch_db():
            rows = self.searcher.keyword_search("消防通道占用 私家车", "tb_regulation")
        self.assertIn("law_name LIKE %s", self.cursor.sql)
        self.assertIn("keywords LIKE %s", self.cursor.sql)
        self.assertEqual(rows, [{"id": 7, "title": "中华人民共和国消防法 第六十条",
                                 "description": "占用消防通道", "category": "消防",
                                 "keywords": "消防,通道"}])

    def test_unknown_table_is_rejected(self):
        with self.assertRaises(ValueError):
            self.searcher.keyword_search("移位", "tb_unknown")

    # ---- 排序与截断 ----

    def test_rows_sorted_by_hit_count_then_title_then_id(self):
        self.cursor.rows = [
            case_row(1, title="普通案例", description="井盖移位了"),
            case_row(2, title="另一个案例", description="井盖移位并塌陷"),
            case_row(3, title="移位塌陷案例", description="与查询无关"),
            case_row(4, title="移位标题", description="与查询无关"),
        ]
        with self._patch_db():
            rows = self.searcher.keyword_search("井盖缺失/破损 移位 塌陷",
                                                "tb_hazard_case", limit=10)
        # 标签 token 在这些行里一个都不命中，所以排序仍由 移位/塌陷 决定：
        # 2 命中且标题命中(3) > 2 命中(2) > 1 命中且标题命中(4) > 1 命中(1)
        self.assertEqual([row["id"] for row in rows], [3, 2, 4, 1])

    def test_limit_is_applied_after_python_sort(self):
        self.cursor.rows = [
            case_row(1, title="普通案例", description="井盖移位了"),
            case_row(2, title="另一个案例", description="井盖移位并塌陷"),
            case_row(3, title="移位塌陷案例", description="与查询无关"),
        ]
        with self._patch_db():
            rows = self.searcher.keyword_search("井盖缺失/破损 移位 塌陷",
                                                "tb_hazard_case", limit=2)
        self.assertEqual([row["id"] for row in rows], [3, 2])

    def test_zero_limit_returns_nothing_but_still_queries(self):
        with self._patch_db():
            rows = self.searcher.keyword_search("井盖缺失/破损 移位", "tb_hazard_case",
                                                limit=0)
        self.assertEqual(rows, [])

    def test_result_shape_is_unchanged_for_cases(self):
        with self._patch_db():
            rows = self.searcher.keyword_search("井盖缺失/破损 移位", "tb_hazard_case")
        self.assertEqual(set(rows[0]), set(CASE_COLUMNS) | {"table"})
        self.assertEqual(rows[0]["table"], "tb_hazard_case")

    def test_connection_is_closed_on_success(self):
        with self._patch_db():
            self.searcher.keyword_search("井盖缺失/破损 移位", "tb_hazard_case")
        self.assertTrue(self.conn.closed)


def item(item_id, match_type=None):
    row = {"id": item_id, "title": "t%d" % item_id}
    if match_type:
        row["match_type"] = match_type
    return row


class MergeResultsTests(unittest.TestCase):
    """锁住合并顺序：向量在前、关键词只补尾部名额；按 id 去重；截断 max(k)+2。"""

    def test_vector_comes_first_and_keyword_fills_the_tail(self):
        keyword = [item(101), item(102)]
        vector = [item(1), item(2), item(3)]
        merged = HybridSearcher._merge_results(keyword, vector, 3, 3)
        self.assertEqual([r["id"] for r in merged], [1, 2, 3, 101, 102])
        self.assertEqual([r["match_type"] for r in merged],
                         ["语义", "语义", "语义", "关键词", "关键词"])

    def test_duplicate_ids_keep_the_vector_copy(self):
        keyword = [item(5, "关键词"), item(9, "关键词")]
        vector = [item(5, "语义"), item(6, "语义")]
        merged = HybridSearcher._merge_results(keyword, vector, 3, 3)
        self.assertEqual([r["id"] for r in merged], [5, 6, 9])
        self.assertEqual(merged[0]["match_type"], "语义")
        self.assertEqual(merged[2]["match_type"], "关键词")

    def test_truncated_to_max_window(self):
        keyword = [item(101), item(102), item(103)]
        vector = [item(1), item(2), item(3)]
        merged = HybridSearcher._merge_results(keyword, vector, 3, 3)
        self.assertEqual(len(merged), 5)
        self.assertEqual([r["id"] for r in merged], [1, 2, 3, 101, 102])

    def test_window_follows_the_larger_k(self):
        keyword = [item(101), item(102), item(103)]
        merged = HybridSearcher._merge_results(keyword, [], 2, 3)
        self.assertEqual([r["id"] for r in merged], [101, 102, 103])

    def test_empty_keyword_branch_is_pure_vector(self):
        vector = [item(1), item(2), item(3)]
        merged = HybridSearcher._merge_results([], vector, 3, 3)
        self.assertEqual([r["id"] for r in merged], [1, 2, 3])
        self.assertTrue(all(r["match_type"] == "语义" for r in merged))

    def test_empty_vector_branch_is_pure_keyword(self):
        keyword = [item(101), item(102)]
        merged = HybridSearcher._merge_results(keyword, [], 3, 3)
        self.assertEqual([r["id"] for r in merged], [101, 102])
        self.assertTrue(all(r["match_type"] == "关键词" for r in merged))


if __name__ == "__main__":
    unittest.main()
