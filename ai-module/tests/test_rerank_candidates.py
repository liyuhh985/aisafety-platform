import pytest
from core.hazard_taxonomy import major_code_for_category

from tools.hybrid_search import HybridSearcher, RetrievalTimeout


class FakeSearcher(HybridSearcher):
    def __init__(self, vector_results=None, keyword_results=None, error=None):
        self.vector_results = vector_results or []
        self.keyword_results = keyword_results or []
        self.error = error
        self.vector_calls = []
        self.keyword_calls = []

    def vector_search(self, query, table, top_k=3, cancellation=None, deadline=None):
        self.vector_calls.append((query, table, top_k))
        if self.error:
            raise self.error
        return [dict(item) for item in self.vector_results]

    def keyword_search(self, keyword, table, limit=3, cancellation=None, timeout_seconds=None):
        self.keyword_calls.append((keyword, table, limit))
        return [dict(item) for item in self.keyword_results]


def test_retrieve_candidates_expands_window_and_deduplicates():
    searcher = FakeSearcher(
        vector_results=[
            {"id": 1, "title": "v1"},
            {"id": 2, "title": "v2"},
        ],
        keyword_results=[
            {"id": 2, "title": "k2"},
            {"id": 3, "title": "k3"},
        ],
    )

    result = searcher.retrieve_candidates(
        "query", "tb_hazard_case", vector_k=10, keyword_k=10
    )

    assert [item["id"] for item in result] == [1, 2, 3]
    assert searcher.vector_calls == [("query", "tb_hazard_case", 10)]
    assert searcher.keyword_calls == [("query", "tb_hazard_case", 10)]


def test_retrieve_candidates_propagates_vector_errors():
    searcher = FakeSearcher(error=RetrievalTimeout("timeout"))

    with pytest.raises(RetrievalTimeout):
        searcher.retrieve_candidates("query", "tb_hazard_case")

def test_retrieve_rerank_candidates_filters_major_and_keeps_all_unique():
    searcher = FakeSearcher(
        vector_results=[
            {"id": 1, "category": "建筑安全/墙体开裂/倾斜"},
            {"id": 2, "category": "交通与通行/车辆占道"},
            {"id": 3, "category": "建筑安全/高空坠物"},
            {"id": 4, "category": "建筑安全/危房"},
            {"id": 5, "category": "建筑安全/外立面脱落"},
        ],
        keyword_results=[
            {"id": 1, "category": "建筑安全/墙体开裂/倾斜"},
            {"id": 6, "category": "建筑安全/违规搭建"},
            {"id": 7, "category": "建筑安全/墙体开裂/倾斜"},
            {"id": 8, "category": "建筑安全/墙体开裂/倾斜"},
            {"id": 9, "category": "建筑安全/墙体开裂/倾斜"},
        ],
    )

    result = searcher.retrieve_rerank_candidates(
        "query", "tb_hazard_case", major_code="building", vector_k=5, keyword_k=5
    )

    assert [item["id"] for item in result] == [1, 6, 3, 7, 4, 8, 5, 9]
    assert searcher.vector_calls == [("query", "tb_hazard_case", 5)]
    assert searcher.keyword_calls == [("query", "tb_hazard_case", 5)]


def test_retrieve_rerank_candidates_drops_missing_or_unknown_category():
    searcher = FakeSearcher(
        vector_results=[
            {"id": 1},
            {"id": 2, "category": "未知/未知"},
            {"id": 3, "category": "建筑安全/危房"},
        ],
    )

    result = searcher.retrieve_rerank_candidates(
        "query", "tb_hazard_case", major_code="building"
    )

    assert [item["id"] for item in result] == [3]


def test_retrieve_rerank_candidates_rejects_unknown_major():
    searcher = FakeSearcher()

    with pytest.raises(ValueError, match="major"):
        searcher.retrieve_rerank_candidates(
            "query", "tb_hazard_case", major_code="unknown"
        )


@pytest.mark.parametrize("value,expected", [
    ("交通与通行/占道经营/乱堆乱放", "traffic"),
    ("建筑安全/墙体开裂/倾斜", "building"),
    ("消防安全/消防设施故障", "fire"),
    ("building/wall_crack_lean", "building"),
    ("building/墙体开裂/倾斜", "building"),
    ("building/unknown_sub", "building"),
    ("unknown/消防设施故障", "fire"),
    ("消防安全", "fire"),
    ("building", "building"),
    ("占道", "traffic"),
    ("消防通道", "fire"),
    ("井盖/道路", "municipal"),
    ("", None),
    ("unknown/value", None),
])
def test_major_code_for_category(value, expected):
    assert major_code_for_category(value) == expected


def test_retrieve_rerank_candidates_rejects_missing_major():
    searcher = FakeSearcher()

    with pytest.raises(ValueError, match="major"):
        searcher.retrieve_rerank_candidates(
            "query", "tb_hazard_case", major_code=""
        )


def test_retrieve_rerank_candidates_canonicalizes_ids_before_dedupe():
    searcher = FakeSearcher(
        vector_results=[
            {"id": "1", "category": "建筑安全/危房"},
            {"id": True, "category": "建筑安全/危房"},
            {"id": "bad", "category": "建筑安全/危房"},
            {"id": 2, "category": "建筑安全/危房"},
        ],
        keyword_results=[
            {"id": 1, "category": "建筑安全/危房"},
            {"id": 3, "category": "建筑安全/危房"},
        ],
    )

    result = searcher.retrieve_rerank_candidates(
        "query", "tb_hazard_case", major_code="building"
    )

    assert [item["id"] for item in result] == [1, 3, 2]
