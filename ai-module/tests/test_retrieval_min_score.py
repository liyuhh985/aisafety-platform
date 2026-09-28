"""向量检索置信度门槛：把「库内确实没有相关内容」与「检索故障」区分开。"""
import pytest

from tools import hybrid_search


class FakeEmbeddingClient:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


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


class ThresholdSearcher(hybrid_search.HybridSearcher):
    """把落库回查换成内存表，避免测试依赖 MySQL。"""

    def __init__(self, rows=None, **kwargs):
        super().__init__(**kwargs)
        self.rows = {row["id"]: row for row in (rows or [])}
        self.mysql_calls = []

    def _get_rows_by_ids(self, table, ids, cancellation=None, deadline=None):
        return [dict(self.rows[i]) for i in ids if i in self.rows]

    def mysql_vector_search(self, query, table, top_k=3, **kwargs):
        self.mysql_calls.append(table)
        return []


def _searcher(store, **kwargs):
    rows = [
        {"id": 8, "title": "高相似案例", "category": "消防安全/消防通道占用"},
        {"id": 9, "title": "低相似案例", "category": "施工安全/未设置围挡"},
    ]
    return ThresholdSearcher(
        rows=rows,
        vector_backend="milvus",
        milvus_enabled=True,
        vector_store=store,
        embedding_client=FakeEmbeddingClient(),
        **kwargs,
    )


def test_hits_below_threshold_are_dropped():
    store = FakeMilvusStore(hits=[
        {"id": 8, "distance": 0.91},
        {"id": 9, "distance": 0.35},
    ])
    results = _searcher(store).vector_search("楼道被堵", "tb_hazard_case", top_k=3)
    assert [row["id"] for row in results] == [8]


def test_all_hits_below_threshold_return_empty():
    store = FakeMilvusStore(hits=[
        {"id": 8, "distance": 0.47},
        {"id": 9, "distance": 0.31},
    ])
    results = _searcher(store).vector_search("红烧肉怎么做好吃", "tb_hazard_case", top_k=3)
    assert results == []


def test_below_threshold_does_not_trigger_mysql_fallback():
    """低于门槛是「不相关」而不是「故障」，不能兜底把噪声再捞回来。"""
    store = FakeMilvusStore(hits=[{"id": 8, "distance": 0.40}])
    searcher = _searcher(store, milvus_fallback_to_mysql=True)
    results = searcher.vector_search("今天天气怎么样", "tb_hazard_case", top_k=3)
    assert results == []
    assert searcher.mysql_calls == []


def test_real_milvus_failure_still_falls_back():
    """回归护栏：真的故障仍然要兜底，别被阈值改动误伤。"""
    store = FakeMilvusStore(error=RuntimeError("connection refused"))
    searcher = _searcher(store, milvus_fallback_to_mysql=True)
    assert searcher.vector_search("楼道被堵", "tb_hazard_case", top_k=3) == []
    assert searcher.mysql_calls == ["tb_hazard_case"]


def test_mysql_branch_shares_the_same_threshold(monkeypatch):
    """两条向量分支必须用同一个门槛，否则行为随后端漂移。"""
    monkeypatch.setattr(hybrid_search, "RETRIEVAL_MIN_SCORE", 0.5)

    class MysqlSearcher(hybrid_search.HybridSearcher):
        def _embed(self, text, **kwargs):
            if "查询" in text:
                return [1.0, 0.0]
            if "甲" in text:
                return [1.0, 0.0]
            return [0.0, 1.0]

        def _fetch_all(self, table, **kwargs):
            return [(900001, "甲", "高相似内容"), (900002, "乙", "低相似内容")]

        def _get_rows_by_ids(self, table, ids, cancellation=None, deadline=None):
            return [{"id": i} for i in ids]

    searcher = MysqlSearcher(vector_backend="mysql")
    results = searcher.vector_search("查询", "tb_hazard_case", top_k=3)
    assert [row["id"] for row in results] == [900001]


def test_threshold_is_configurable():
    assert 0.0 < hybrid_search.RETRIEVAL_MIN_SCORE < 1.0
