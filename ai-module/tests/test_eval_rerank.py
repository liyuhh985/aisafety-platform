import pytest
from eval.eval_rerank import evaluate_ranked, gate_result, summarize_records


def test_evaluate_ranked_reports_first_rank_and_mrr():
    result = evaluate_ranked([8, 2, 7, 3], {2, 3, 9}, k=5)

    assert result["top1"] is False
    assert result["hit"] is True
    assert result["first_rank"] == 2
    assert result["mrr"] == 0.5
    assert result["p_at_5"] == 2 / 5
    assert result["recall_at_5"] == 2 / 3


def test_gate_result_rejects_hit_drop():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 0.984, "mrr": 0.920, "top1_hits": 58, "empty_rate": 1.0,
              "added_p95_ms": 100}

    result = gate_result(baseline, rerank)
    assert result["passed"] is False
    assert "Hit@5" in result["reason"]


def test_gate_result_accepts_all_thresholds():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 1.0, "mrr": 0.905, "top1_hits": 55,
              "top1_regressions": 0, "empty_rate": 1.0, "added_p95_ms": 400,
              "rerank_p95_ms": 350, "rerank_successes": 64, "rerank_attempts": 64,
              "rerank_fallbacks": 0, "production_prediction_ok": True}

    result = gate_result(baseline, rerank)
    assert result["passed"] is True

def test_summarize_records_includes_precision_recall_and_p95():
    row1 = evaluate_ranked([1, 9], {1, 2}, k=5)
    row1.update({"latency_ms": 10, "candidate_count": 5})
    row2 = evaluate_ranked([9, 2], {1, 2}, k=5)
    row2.update({"latency_ms": 20, "candidate_count": 7})

    summary = summarize_records([row1, row2], negative_empty=2, negative_total=2)

    assert summary["p_at_5"] == 0.2
    assert summary["recall_at_5"] == 0.5
    assert summary["top1_hits"] == 1
    assert summary["empty_rate"] == 1.0
    assert summary["p95_ms"] == 20
    assert summary["avg_candidate_count"] == 6


def test_gate_result_rejects_noop_mode():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 1.0, "mrr": 0.920, "top1_hits": 58, "empty_rate": 1.0,
              "added_p95_ms": 100}

    result = gate_result(baseline, rerank, reranker_enabled=False)
    assert result["passed"] is False
    assert "Noop" in result["reason"]


def test_evaluate_ranked_rejects_non_positive_k():
    with pytest.raises(ValueError, match="positive"):
        evaluate_ranked([1], {1}, k=0)

def test_gate_result_requires_absolute_hit_at_5_one():
    baseline = {"hit_at_5": 0.984, "mrr": 0.844, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 0.984, "mrr": 0.875, "top1_hits": 55, "empty_rate": 1.0,
              "added_p95_ms": 100}

    result = gate_result(baseline, rerank)
    assert result["passed"] is False
    assert "1.000" in result["reason"]


def test_gate_result_requires_net_top1_gain_of_five():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 1.0, "mrr": 0.905, "top1_hits": 54, "top1_moves": 5,
              "top1_regressions": 0, "empty_rate": 1.0, "added_p95_ms": 400,
              "rerank_p95_ms": 250, "rerank_successes": 64, "rerank_attempts": 64,
              "rerank_fallbacks": 0, "production_prediction_ok": True}

    result = gate_result(baseline, rerank)
    assert result["passed"] is False
    assert "Top-1" in result["reason"]


def test_gate_result_rejects_incomplete_reranker_success():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 1.0, "mrr": 0.905, "top1_hits": 55, "top1_moves": 5,
              "empty_rate": 1.0, "added_p95_ms": 100,
              "rerank_successes": 63, "rerank_attempts": 64}

    result = gate_result(baseline, rerank, reranker_enabled=True)
    assert result["passed"] is False
    assert "success" in result["reason"]


def test_gate_result_rejects_negative_empty_rate_regression():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 1.0, "mrr": 0.905, "top1_hits": 55, "top1_moves": 5,
              "empty_rate": 0.9, "added_p95_ms": 100,
              "rerank_successes": 64, "rerank_attempts": 64}

    result = gate_result(baseline, rerank, reranker_enabled=True)
    assert result["passed"] is False
    assert "EmptyRate" in result["reason"]


def test_summarize_records_reports_separate_latency_percentiles():
    row1 = evaluate_ranked([1, 9], {1, 2}, k=5)
    row1.update({"latency_ms": 10, "retrieval_latency_ms": 8, "rerank_latency_ms": 2})
    row2 = evaluate_ranked([9, 2], {1, 2}, k=5)
    row2.update({"latency_ms": 30, "retrieval_latency_ms": 25, "rerank_latency_ms": 5})

    summary = summarize_records([row1, row2], negative_empty=2, negative_total=2)

    assert summary["retrieval_p95_ms"] == 25
    assert summary["rerank_p95_ms"] == 5


def test_gate_result_rejects_rerank_model_p95_over_350():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 1.0, "mrr": 0.959, "top1_hits": 55, "top1_moves": 10,
              "top1_regressions": 0, "empty_rate": 1.0, "added_p95_ms": 400,
              "rerank_p95_ms": 350.01, "rerank_successes": 64, "rerank_attempts": 64,
              "rerank_fallbacks": 0, "production_prediction_ok": True}

    result = gate_result(baseline, rerank, reranker_enabled=True)
    assert result["passed"] is False
    assert "rerank P95" in result["reason"]


def test_gate_result_rejects_incomplete_production_prediction():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 1.0, "mrr": 0.959, "top1_hits": 55, "top1_moves": 10,
              "top1_regressions": 0, "empty_rate": 1.0, "added_p95_ms": 400,
              "rerank_p95_ms": 250, "rerank_successes": 64, "rerank_attempts": 64,
              "rerank_fallbacks": 0, "production_prediction_ok": False}

    result = gate_result(baseline, rerank, reranker_enabled=True)
    assert result["passed"] is False
    assert "prediction" in result["reason"].lower()


def test_predict_production_uses_planner_output_without_gold(monkeypatch):
    from eval import eval_rerank as ev

    class Registry:
        def metadata_catalog(self):
            return [{"category": "traffic", "description": "交通", "routing_keywords": ["盲道"]}]

        def load_body(self, code):
            return "TRAFFIC SKILL"

    monkeypatch.setattr(ev, "_skill_registry", Registry())
    monkeypatch.setattr(ev, "_route_skills", lambda **kwargs: {
        "active_skills": ["traffic"], "source": "keyword", "confidence": 0.9,
    })
    monkeypatch.setattr(ev, "_planner_understand", lambda *args, **kwargs: {
        "ok": True,
        "perceived_major": "traffic",
        "perceived_subcategory": "blind_path_occupied",
        "premises_scope": "public",
        "issues": [{
            "major_code": "traffic",
            "subcategory_code": "blind_path_occupied",
            "slots": {"behavior": "共享单车"},
        }],
    })

    prediction = ev.predict_production("盲道被共享单车占了")
    assert prediction["predicted_major"] == "traffic"
    assert prediction["predicted_subcategory"] == "blind_path_occupied"
    assert prediction["planner_ok"] is True
    assert prediction["keyword"].startswith("盲道占用")


def test_predict_production_does_not_fallback_to_gold(monkeypatch):
    from eval import eval_rerank as ev

    class Registry:
        def metadata_catalog(self):
            return []

        def load_body(self, code):
            return ""

    monkeypatch.setattr(ev, "_skill_registry", Registry())
    monkeypatch.setattr(ev, "_route_skills", lambda **kwargs: {
        "active_skills": [], "source": "fallback", "confidence": 0.0,
    })
    monkeypatch.setattr(ev, "_planner_understand", lambda *args, **kwargs: {
        "ok": True, "perceived_major": "", "perceived_subcategory": "",
        "premises_scope": "public", "issues": [],
    })

    prediction = ev.predict_production("路边有个奇怪的东西")
    assert prediction["predicted_major"] == ""
    assert prediction["predicted_subcategory"] == ""
    assert prediction["keyword"] == "路边有个奇怪的东西"


def test_gate_result_rejects_end_to_end_added_p95_over_500():
    baseline = {"hit_at_5": 1.0, "mrr": 0.875, "top1_hits": 50, "empty_rate": 1.0}
    rerank = {"hit_at_5": 1.0, "mrr": 0.959, "top1_hits": 55, "top1_moves": 10,
              "top1_regressions": 0, "empty_rate": 1.0, "added_p95_ms": 550,
              "rerank_p95_ms": 250, "rerank_successes": 64, "rerank_attempts": 64,
              "rerank_fallbacks": 0, "production_prediction_ok": True}

    result = gate_result(baseline, rerank, reranker_enabled=True)
    assert result["passed"] is False
    assert "end-to-end" in result["reason"].lower()
