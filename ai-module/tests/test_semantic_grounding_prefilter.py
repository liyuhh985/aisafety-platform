# -*- coding: utf-8 -*-
from eval.semantic_grounding.deterministic_prefilter import prefilter_sample


def test_direct_quote_support_skips_models():
    sample = {
        "category": "fire_lane_blocked",
        "slot": "blocker",
        "value": "杂物",
        "quote": "被杂物堵住",
        "source_text": "消防通道被杂物堵住",
    }
    assert prefilter_sample(sample)["decision"] == "grounded"


def test_quote_outside_source_is_invalid():
    sample = {
        "category": "fire_lane_blocked",
        "slot": "blocker",
        "value": "杂物",
        "quote": "被车辆堵住",
        "source_text": "消防通道被杂物堵住",
    }
    assert prefilter_sample(sample)["decision"] == "invalid_source"


def test_synonym_case_requires_verifier():
    sample = {
        "category": "dangerous_building",
        "slot": "structure",
        "value": "墙体倾斜",
        "quote": "房子明显往一边斜",
        "source_text": "房子明显往一边斜",
    }
    assert prefilter_sample(sample)["decision"] == "needs_verifier"


def test_wufa_direct_support_is_not_a_negation_conflict():
    sample = {
        "category": "fire_lane_blocked",
        "slot": "impact",
        "value": "无法进入",
        "quote": "无法进入",
        "source_text": "消防车无法进入小区",
    }
    assert prefilter_sample(sample)["decision"] == "grounded"
