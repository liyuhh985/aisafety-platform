# -*- coding: utf-8 -*-
from eval.semantic_grounding.consensus import cohen_kappa, merge_pair


def test_exact_agreement_and_disagreement():
    assert merge_pair("entailed", "entailed") == {
        "label": "entailed", "status": "agreed",
    }
    assert merge_pair("entailed", "neutral") == {
        "label": "ambiguous", "status": "disagreed",
    }


def test_cohen_kappa():
    assert cohen_kappa(
        ["entailed", "neutral", "contradicted"],
        ["entailed", "neutral", "contradicted"],
    ) == 1.0
    kappa = cohen_kappa(
        ["entailed", "entailed", "neutral", "neutral"],
        ["entailed", "neutral", "neutral", "neutral"],
    )
    assert 0.0 <= kappa < 1.0


def test_quality_gate_rejects_low_agreement():
    import pytest
    from eval.semantic_grounding.consensus import assert_quality_gate

    with pytest.raises(ValueError, match="overall_agreement"):
        assert_quality_gate({"overall_agreement": 0.70, "cohen_kappa": 0.80})


def test_quality_gate_rejects_low_kappa():
    import pytest
    from eval.semantic_grounding.consensus import assert_quality_gate

    with pytest.raises(ValueError, match="cohen_kappa"):
        assert_quality_gate({"overall_agreement": 0.90, "cohen_kappa": 0.50})
