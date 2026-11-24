# -*- coding: utf-8 -*-
from eval.semantic_grounding.labeler_config import build_labeler


def test_labelers_use_distinct_models(monkeypatch):
    monkeypatch.setenv("SEMANTIC_LABELER_A_BASE_URL", "http://a")
    monkeypatch.setenv("SEMANTIC_LABELER_A_API_KEY", "ka")
    monkeypatch.setenv("SEMANTIC_LABELER_A_MODEL", "minimax-m3.1-flash")
    monkeypatch.setenv("SEMANTIC_LABELER_B_BASE_URL", "http://b")
    monkeypatch.setenv("SEMANTIC_LABELER_B_API_KEY", "kb")
    monkeypatch.setenv("SEMANTIC_LABELER_B_MODEL", "glm-5.3-flash")
    a = build_labeler("A")
    b = build_labeler("B")
    assert a.base_url == "http://a"
    assert a.model == "minimax-m3.1-flash"
    assert b.base_url == "http://b"
    assert b.model == "glm-5.3-flash"
    assert a.temperature == 0.0
    assert b.temperature == 0.0


def test_labeler_input_excludes_ground_truth_and_grouping_fields():
    from eval.semantic_grounding.run_labelers import build_labeler_input

    row = {
        "id": "qv-001",
        "source_group_id": "group-a",
        "category": "dangerous_building",
        "slot": "structure",
        "value": "墙体倾斜",
        "quote": "房子明显往一边斜",
        "source_text": "房子明显往一边斜",
        "split": "dev",
        "expected_label": "entailed",
    }
    payload = build_labeler_input(row)
    assert set(payload) == {"slot", "slot_question", "value", "quote"}
    assert "expected_label" not in payload
    assert "source_group_id" not in payload
