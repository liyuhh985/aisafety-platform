import unittest

from tools.hybrid_search import HybridSearcher


class FakeSearcher(HybridSearcher):
    def __init__(self, vector_results=None, keyword_results=None):
        self.vector_results = vector_results or []
        self.keyword_results = keyword_results or []
        self.vector_calls = []
        self.keyword_calls = []

    def vector_search(self, query, table, top_k=3):
        self.vector_calls.append((query, table, top_k))
        return [dict(result) for result in self.vector_results]

    def keyword_search(self, keyword, table, limit=3):
        self.keyword_calls.append((keyword, table, limit))
        return [dict(result) for result in self.keyword_results]


class RetrievalContractTests(unittest.TestCase):
    def test_hybrid_search_preserves_sections_and_deduplicates_ids(self):
        searcher = FakeSearcher(
            vector_results=[
                {"id": 7, "title": "同一案例", "description": "语义结果"},
                {"id": 8, "title": "语义案例", "description": "另一个结果"},
            ],
            keyword_results=[
                {
                    "id": 7,
                    "title": "同一案例",
                    "description": "关键词结果",
                    "category": "施工",
                    "city": "成都",
                    "severity": "一般",
                    "cause": "原因",
                    "rectification": "整改",
                    "regulation_ref": "法规",
                    "verdict": "判决",
                }
            ],
        )

        result = searcher.hybrid_search("临时用电", "tb_hazard_case", vector_k=2, keyword_k=1)

        self.assertIn("=== 混合检索结果", result)
        self.assertIn("【结果1】", result)
        self.assertEqual(result.count("同一案例"), 1)
        self.assertEqual(searcher.vector_calls, [("临时用电", "tb_hazard_case", 2)])
        self.assertEqual(searcher.keyword_calls, [("临时用电", "tb_hazard_case", 1)])

    def test_empty_sources_return_non_empty_no_result_message(self):
        searcher = FakeSearcher()

        result = searcher.hybrid_search("不存在的内容", "tb_regulation")

        self.assertTrue(result.strip())
        self.assertIn("未找到", result)

    def test_keyword_results_remain_available_when_vector_branch_is_empty(self):
        searcher = FakeSearcher(
            keyword_results=[
                {
                    "id": 11,
                    "title": "消防安全规定",
                    "description": "保持消防通道畅通",
                    "category": "消防",
                }
            ]
        )

        result = searcher.hybrid_search("消防通道", "tb_regulation")

        self.assertIn("【法规1】", result)
        self.assertIn("消防安全规定", result)

    def test_invalid_table_is_rejected_before_database_branches(self):
        searcher = FakeSearcher()

        with self.assertRaises(ValueError):
            searcher.hybrid_search("任意查询", "tb_unknown")

        self.assertEqual(searcher.vector_calls, [])
        self.assertEqual(searcher.keyword_calls, [])


if __name__ == "__main__":
    unittest.main()
