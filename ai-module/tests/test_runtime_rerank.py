import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools import hybrid_search as hs


class FakeSearcher(hs.HybridSearcher):
    def __init__(self, vector_results=None, keyword_results=None):
        self.vector_results = vector_results or []
        self.keyword_results = keyword_results or []
        self.vector_calls = []
        self.keyword_calls = []

    def vector_search(self, query, table, top_k=3, cancellation=None, deadline=None):
        self.vector_calls.append((query, table, top_k))
        return [dict(item) for item in self.vector_results]

    def keyword_search(self, keyword, table, limit=3, cancellation=None,
                       timeout_seconds=None):
        self.keyword_calls.append((keyword, table, limit))
        return [dict(item) for item in self.keyword_results]


class ReverseReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        ranked = list(reversed(candidates[:final_k]))
        return [
            {"id": item["id"], "rerank_score": 1.0 - index / 10}
            for index, item in enumerate(ranked)
        ]


class ErrorReranker:
    def rerank(self, query, candidates, final_k, cancellation=None, timeout_seconds=1.0):
        raise RuntimeError("reranker unavailable")


def _case_candidates():
    return [
        {"id": 1, "title": "alpha", "description": "first"},
        {"id": 2, "title": "beta", "description": "second"},
        {"id": 3, "title": "gamma", "description": "third"},
    ]


def test_rerank_disabled_preserves_legacy_retrieval_and_does_not_build_reranker(monkeypatch):
    searcher = FakeSearcher(vector_results=_case_candidates())
    built = []

    monkeypatch.setattr(hs, "RERANK_ENABLED", False)
    monkeypatch.setattr(hs, "_build_runtime_reranker", lambda: built.append(True))

    result = searcher.hybrid_search(
        "query", "tb_hazard_case", vector_k=3, keyword_k=3
    )

    assert searcher.vector_calls == [("query", "tb_hazard_case", 3)]
    assert searcher.keyword_calls == [("query", "tb_hazard_case", 3)]
    assert built == []
    assert result.index("alpha") < result.index("beta") < result.index("gamma")


def test_rerank_enabled_expands_candidates_and_reorders_final_output(monkeypatch):
    searcher = FakeSearcher(vector_results=_case_candidates())

    monkeypatch.setattr(hs, "RERANK_ENABLED", True)
    monkeypatch.setattr(hs, "RERANK_CANDIDATE_K", 5)
    monkeypatch.setattr(hs, "RERANK_FINAL_K", 2)
    monkeypatch.setattr(hs, "_build_runtime_reranker", lambda: ReverseReranker())

    result = searcher.hybrid_search(
        "query", "tb_hazard_case", vector_k=3, keyword_k=3
    )

    assert searcher.vector_calls == [("query", "tb_hazard_case", 5)]
    assert searcher.keyword_calls == [("query", "tb_hazard_case", 5)]
    assert "beta" in result
    assert "alpha" in result
    assert "gamma" not in result
    assert result.index("beta") < result.index("alpha")


def test_rerank_enabled_falls_back_to_original_order_on_error(monkeypatch):
    searcher = FakeSearcher(vector_results=_case_candidates())

    monkeypatch.setattr(hs, "RERANK_ENABLED", True)
    monkeypatch.setattr(hs, "RERANK_CANDIDATE_K", 5)
    monkeypatch.setattr(hs, "RERANK_FINAL_K", 2)
    monkeypatch.setattr(hs, "_build_runtime_reranker", lambda: ErrorReranker())

    result = searcher.hybrid_search(
        "query", "tb_hazard_case", vector_k=3, keyword_k=3
    )

    assert result.index("alpha") < result.index("beta")
    assert "gamma" not in result
    assert "reranker unavailable" not in result


def test_rerank_kill_switch_does_not_call_reranker_builder(monkeypatch):
    searcher = FakeSearcher(vector_results=_case_candidates())

    monkeypatch.setattr(hs, "RERANK_ENABLED", False)

    def fail_if_called():
        pytest.fail("reranker must not be constructed while the kill switch is off")

    monkeypatch.setattr(hs, "_build_runtime_reranker", fail_if_called)

    result = searcher.hybrid_search("query", "tb_hazard_case")

    assert "alpha" in result
    assert searcher.vector_calls == [("query", "tb_hazard_case", 3)]


def test_disabled_default_does_not_import_reranker_modules():
    env = dict(os.environ)
    env["RERANK_ENABLED"] = "false"
    code = (
        'import sys; import tools.hybrid_search as hs; '
        'assert hs.RERANK_ENABLED is False; '
        'assert "core.reranker" not in sys.modules; '
        'assert "core.reranker_http" not in sys.modules'
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

