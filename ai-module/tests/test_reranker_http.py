import pytest

from core.reranker_http import HTTPReranker


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def candidates():
    return [
        {"id": 1, "title": "消防通道", "description": "车辆占用消防通道"},
        {"id": 2, "title": "配电箱", "description": "配电箱门缺失"},
    ]


def test_http_reranker_posts_documents_and_maps_ranked_indices():
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append((url, headers, json, timeout))
        return FakeResponse({
            "results": [
                {"index": 1, "relevance_score": 0.98},
                {"index": 0, "relevance_score": 0.42},
            ]
        })

    reranker = HTTPReranker(
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-rerank-model",
        http_post=fake_post,
    )
    result = reranker.rerank("消防通道被占用", candidates(), final_k=2)

    assert [item["id"] for item in result] == [2, 1]
    assert result[0]["rerank_score"] == 0.98
    assert calls[0][0] == "https://example.test/v1/rerank"
    assert calls[0][1]["Authorization"] == "Bearer secret"
    assert calls[0][2]["model"] == "test-rerank-model"
    assert calls[0][2]["top_n"] == 2
    assert calls[0][3] == 1.0


def test_http_reranker_rejects_invalid_result_shape():
    reranker = HTTPReranker(
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-rerank-model",
        http_post=lambda *args, **kwargs: FakeResponse({"results": "bad"}),
    )

    with pytest.raises(ValueError, match="results"):
        reranker.rerank("消防通道被占用", candidates(), final_k=2)

def test_http_reranker_rejects_boolean_index():
    reranker = HTTPReranker(
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-rerank-model",
        http_post=lambda *args, **kwargs: FakeResponse({
            "results": [{"index": True, "relevance_score": 0.9}]
        }),
    )

    with pytest.raises(ValueError, match="index"):
        reranker.rerank("消防通道被占用", candidates(), final_k=2)


def test_http_reranker_rejects_non_finite_score():
    reranker = HTTPReranker(
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-rerank-model",
        http_post=lambda *args, **kwargs: FakeResponse({
            "results": [{"index": 0, "relevance_score": float("nan")}]
        }),
    )

    with pytest.raises(ValueError, match="score"):
        reranker.rerank("消防通道被占用", candidates(), final_k=2)


def test_http_reranker_rejects_duplicate_index():
    reranker = HTTPReranker(
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-rerank-model",
        http_post=lambda *args, **kwargs: FakeResponse({
            "results": [
                {"index": 0, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.8},
            ]
        }),
    )

    with pytest.raises(ValueError, match="duplicate"):
        reranker.rerank("消防通道被占用", candidates(), final_k=2)

def test_http_reranker_documents_siliconflow_bge_compatibility():
    import core.reranker_http as reranker_http

    assert "SiliconFlow/BGE-compatible" in reranker_http.__doc__
