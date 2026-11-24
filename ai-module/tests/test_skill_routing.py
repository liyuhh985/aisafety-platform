from core.skill_router import route_by_keywords, route_skills

CATALOG = [
    {"category": "fire", "routing_keywords": ["消防通道", "消火栓"], "description": "消防"},
    {"category": "utility", "routing_keywords": ["配电箱", "燃气泄漏"], "description": "电气燃气"},
    {"category": "municipal", "routing_keywords": ["井盖", "路面积水"], "description": "市政"},
]


def test_single_and_multi_major_are_high_confidence():
    assert route_by_keywords("消防通道被私家车占了", CATALOG)["active_skills"] == ["fire"]
    result = route_by_keywords("消防通道被占，旁边配电箱冒火花", CATALOG)
    assert result["active_skills"] == ["fire", "utility"]


def test_weak_text_needs_llm():
    assert route_by_keywords("那个东西一直响，不太安全", CATALOG)["source"] == "need_llm"


def test_negative_out_of_scope_phrase_does_not_activate():
    result = route_by_keywords("消防员招聘条件是什么", CATALOG)
    assert result == {"active_skills": [], "source": "negative", "confidence": 0.0}


def test_frontend_selection_skips_llm():
    calls = []
    result = route_skills(
        "小区有隐患", CATALOG,
        selected_major_codes=["fire"], locked_majors=[], vision_categories=[],
        route_llm=lambda *a, **k: calls.append(1),
    )
    assert result["active_skills"] == ["fire"]
    assert result["source"] == "frontend"
    assert calls == []


def test_locked_majors_have_highest_priority():
    calls = []
    result = route_skills(
        "消防通道被占", CATALOG,
        selected_major_codes=["utility"], locked_majors=["fire"], vision_categories=["municipal"],
        route_llm=lambda *a, **k: calls.append(1),
    )
    assert result["active_skills"] == ["fire"]
    assert result["source"] == "locked"
    assert calls == []


def test_vision_categories_precede_keywords():
    result = route_skills(
        "消防通道被占", CATALOG,
        selected_major_codes=[], locked_majors=[], vision_categories=["municipal"],
        route_llm=lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM called")),
    )
    assert result["active_skills"] == ["municipal"]
    assert result["source"] == "vision"


def test_weak_keyword_calls_llm_and_caps_three():
    result = route_skills(
        "那个东西一直响", CATALOG,
        selected_major_codes=[], locked_majors=[], vision_categories=[],
        route_llm=lambda text, catalog: {
            "active_skills": ["fire", "utility", "municipal", "traffic"],
            "confidence": 0.8,
        },
    )
    assert result["active_skills"] == ["fire", "utility", "municipal"]
    assert result["source"] == "llm"


def test_low_confidence_or_unknown_llm_categories_fall_back():
    result = route_skills(
        "那个东西一直响", CATALOG,
        selected_major_codes=[], locked_majors=[], vision_categories=[],
        route_llm=lambda text, catalog: {
            "active_skills": ["not_a_hazard", "fire"],
            "confidence": 0.2,
        },
    )
    assert result == {"active_skills": [], "source": "fallback", "confidence": 0.0}


CASES = [
    ("消防通道被私家车占用", ["fire"]),
    ("消防通道被占，配电箱冒火花", ["fire", "utility"]),
    ("井盖缺失，旁边路灯杆歪了", ["municipal"]),
    ("电梯困人且有异响", ["elevator_special"]),
    ("那个东西歪了，我觉得不安全", None),
    ("消防员招聘条件是什么", []),
]
def test_canonical_skill_routing_cases():
    from pathlib import Path
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry(
        Path(__file__).parents[1] / "skills",
        valid_tool_names={"search_regulation", "search_cases"},
    )
    registry.scan_metadata()
    catalog = registry.metadata_catalog()
    cases = [
        ("消防通道被私家车占用", ["fire"]),
        ("消防通道被占，配电箱冒火花", ["fire", "utility"]),
        ("井盖缺失，旁边路灯杆歪了", ["municipal"]),
        ("电梯困人且有异响", ["elevator_special"]),
        ("那个东西歪了，我觉得不安全", None),
        ("消防员招聘条件是什么", []),
    ]
    for text, expected in cases:
        result = route_by_keywords(text, catalog)
        if expected is None:
            assert result["source"] == "need_llm", text
        else:
            assert result["active_skills"] == expected, text
def test_router_llm_failure_degrades_to_no_skill():
    def broken_llm(text, catalog):
        raise RuntimeError("route model unavailable")

    result = route_skills(
        "那个东西一直响", CATALOG,
        selected_major_codes=[], locked_majors=[], vision_categories=[],
        route_llm=broken_llm,
    )
    assert result == {"active_skills": [], "source": "fallback", "confidence": 0.0}