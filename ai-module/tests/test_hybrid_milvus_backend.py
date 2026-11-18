import unittest

from tools.hybrid_search import HybridSearcher


class FakeEmbeddingClient:
    def __init__(self, vector=None):
        self.vector = vector or [0.1, 0.2, 0.3]
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [self.vector for _ in texts]


class FakeMilvusStore:
    def __init__(self, hits=None, error=None):
        self.hits = hits or []
        self.error = error
        self.calls = []

    def search(self, table, query_vector, top_k):
        self.calls.append((table, query_vector, top_k))
        if self.error:
            raise self.error
        return list(self.hits)


class BackendSearcher(HybridSearcher):
    def __init__(self, mysql_results=None, keyword_results=None, **kwargs):
        super().__init__(**kwargs)
        self.mysql_results = mysql_results or []
        self.keyword_results = keyword_results or []
        self.mysql_calls = []
        self.keyword_calls = []
        self.hydrated_rows = {}

    def mysql_vector_search(self, query, table, top_k=3):
        self.mysql_calls.append((query, table, top_k))
        return [dict(result) for result in self.mysql_results]

    def keyword_search(self, keyword, table, limit=3):
        self.keyword_calls.append((keyword, table, limit))
        return [dict(result) for result in self.keyword_results]

    def _get_rows_by_ids(self, table, ids):
        return [self.hydrated_rows[doc_id] for doc_id in ids if doc_id in self.hydrated_rows]


class HybridMilvusBackendTests(unittest.TestCase):
    def test_mysql_backend_uses_existing_mysql_vector_branch(self):
        searcher = BackendSearcher(
            vector_backend="mysql",
            mysql_results=[{"id": 1, "title": "MySQL 案例"}],
        )

        results = searcher.vector_search("查询", "tb_hazard_case", top_k=4)

        self.assertEqual(results, [{"id": 1, "title": "MySQL 案例"}])
        self.assertEqual(searcher.mysql_calls, [("查询", "tb_hazard_case", 4)])

    def test_milvus_backend_searches_then_keeps_mysql_keyword_results(self):
        store = FakeMilvusStore(hits=[{"id": 8, "distance": 0.91, "content_hash": "hash"}])
        searcher = BackendSearcher(
            vector_backend="milvus",
            milvus_enabled=True,
            vector_store=store,
            embedding_client=FakeEmbeddingClient(),
            keyword_results=[
                {
                    "id": 9,
                    "title": "关键词案例",
                    "description": "描述",
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
        searcher.hydrated_rows[8] = {
            "id": 8,
            "title": "Milvus 案例",
            "description": "从 MySQL 回查的最新内容",
            "category": "施工",
            "city": "成都",
            "severity": "一般",
            "cause": "原因",
            "rectification": "整改",
            "regulation_ref": "法规",
            "verdict": "判决",
        }

        result = searcher.hybrid_search("施工", "tb_hazard_case", vector_k=2, keyword_k=1)

        self.assertIn("Milvus 案例", result)
        self.assertIn("关键词案例", result)
        self.assertEqual(len(store.calls), 1)
        self.assertEqual(searcher.keyword_calls, [("施工", "tb_hazard_case", 1)])

    def test_milvus_failure_falls_back_to_mysql_vector_search(self):
        searcher = BackendSearcher(
            vector_backend="milvus",
            milvus_enabled=True,
            milvus_fallback_to_mysql=True,
            vector_store=FakeMilvusStore(error=RuntimeError("connection refused")),
            embedding_client=FakeEmbeddingClient(),
            mysql_results=[{"id": 3, "title": "回退案例"}],
        )

        results = searcher.vector_search("查询", "tb_hazard_case", top_k=3)

        self.assertEqual(results, [{"id": 3, "title": "回退案例"}])
        self.assertEqual(searcher.mysql_calls, [("查询", "tb_hazard_case", 3)])

    def test_empty_milvus_collection_falls_back_to_mysql_vector_search(self):
        searcher = BackendSearcher(
            vector_backend="milvus",
            milvus_enabled=True,
            milvus_fallback_to_mysql=True,
            vector_store=FakeMilvusStore(hits=[]),
            embedding_client=FakeEmbeddingClient(),
            mysql_results=[{"id": 5, "title": "空索引回退案例"}],
        )

        results = searcher.vector_search("查询", "tb_hazard_case", top_k=3)

        self.assertEqual(results, [{"id": 5, "title": "空索引回退案例"}])
        self.assertEqual(searcher.mysql_calls, [("查询", "tb_hazard_case", 3)])

    def test_milvus_failure_without_fallback_returns_clear_error(self):
        searcher = BackendSearcher(
            vector_backend="milvus",
            milvus_enabled=True,
            milvus_fallback_to_mysql=False,
            vector_store=FakeMilvusStore(error=RuntimeError("connection refused")),
        )

        result = searcher.hybrid_search("法规", "tb_regulation")

        self.assertIn("Milvus", result)
        self.assertIn("不可用", result)
        self.assertNotIn("未找到与", result)

    def test_milvus_hit_is_hydrated_from_mysql_before_formatting(self):
        store = FakeMilvusStore(hits=[{"id": 42, "distance": 0.88, "content_hash": "hash"}])
        searcher = BackendSearcher(
            vector_backend="milvus",
            milvus_enabled=True,
            vector_store=store,
            embedding_client=FakeEmbeddingClient(),
        )
        searcher.hydrated_rows[42] = {
            "id": 42,
            "title": "最新法规标题",
            "description": "MySQL 最新法规正文",
            "category": "消防",
        }

        result = searcher.vector_search("消防", "tb_regulation", top_k=1)

        self.assertEqual(result[0]["title"], "最新法规标题")
        self.assertEqual(result[0]["description"], "MySQL 最新法规正文")
        self.assertEqual(result[0]["match_score"], 0.88)


if __name__ == "__main__":
    unittest.main()
