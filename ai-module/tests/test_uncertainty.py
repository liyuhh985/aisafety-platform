"""可验证的不确定性信号：不依赖模型自报置信度。"""
from core.uncertainty import assess, has_active_danger, normalize_text, slot_status

SMOKE_SOURCE = "楼道里全是浓烟，人都出不来"


def test_normalize_text_strips_punctuation_and_fullsized_digits():
    assert normalize_text("１２号院，楼 道。") == "12号院楼道"


def test_slot_status_grounded_cases():
    assert slot_status("浓烟", SMOKE_SOURCE) == "grounded"
    assert slot_status("占用", "盲道被机动车长期占用") == "grounded"
    assert slot_status("下方人行道", "下面就是人行道") == "grounded"


def test_slot_status_never_flags_a_synonym_as_invented():
    # 用户写"消防栓"，模型归一成"消火栓"：只差一个字，绝不能被判成编造。
    # 覆盖率 0.67 落在 grounded 带（>=0.6），weak 带是给 0.34~0.6 的近似改写留的余量。
    assert slot_status("消火栓", "消防栓箱体破损") != "strong"
    assert slot_status("消防栓", "消火栓箱体破损") != "strong"
    assert slot_status("燃气管道", "煤气管老化") != "strong"


def test_slot_status_flags_invented_values_as_strong():
    assert slot_status("持续中", SMOKE_SOURCE) == "strong"
    assert slot_status("杂物", "楼下消火栓坏了算隐患吗") == "strong"


def test_slot_status_flags_invented_numbers_as_strong():
    assert slot_status("3人被困", "楼上着火了") == "strong"
    assert slot_status("2层以上", SMOKE_SOURCE) == "strong"


def test_slot_status_empty_value():
    assert slot_status("", SMOKE_SOURCE) == "empty"
    assert slot_status(None, SMOKE_SOURCE) == "empty"


def test_has_active_danger_hits_colloquial_phrasing():
    for text in ("楼上火烧起来了，好几个人在里面", "楼道里全是浓烟，人都出不来",
                 "厨房煤气味道很重", "楼下饭店的油锅烧起来了", "人都下不来"):
        assert has_active_danger(text) is True, text


def test_has_active_danger_hits_v2b_acute_exposure_terms():
    for text in (
        "污水井里硫化氢浓度超标，工人已经中毒",
        "有人下化粪池后晕厥，叫不醒",
        "车库里的易燃溶剂泄漏，随时可能闪燃",
    ):
        assert has_active_danger(text) is True, text


def test_has_active_danger_does_not_fire_on_routine_hazards():
    for text in ("紧急出口被堵住了", "马上就要下雨了", "这事很紧急，帮我看下这个井盖",
                 "紧急疏散通道被杂物堵住，需要尽快清理", "小区外墙广告牌锈蚀"):
        assert has_active_danger(text) is False, text


def test_assess_flags_cautious_on_an_invented_slot():
    plan = {
        "ok": True,
        "issues": [{
            "subcategory_code": "fire_lane_blocked",
            "slots": {"blocker": "浓烟", "persistence": "持续中"},
        }],
    }
    result = assess(plan, [{"role": "user", "content": SMOKE_SOURCE}])
    assert result["uncertainty_level"] == "cautious"
    assert result["ungrounded_slots"] == ["fire_lane_blocked.persistence=持续中"]
    assert any(sig.startswith("ungrounded_slot:") for sig in result["uncertainty_signals"])


def test_assess_stays_ok_when_every_slot_is_grounded():
    plan = {
        "ok": True,
        "issues": [{
            "subcategory_code": "blind_path_occupied",
            "slots": {"behavior": "占用", "persistence": "长期", "blocked": "完全堵死"},
        }],
    }
    result = assess(plan, [{"role": "user", "content": "盲道被机动车长期占用，完全堵死"}])
    assert result["uncertainty_level"] == "ok"
    assert result["ungrounded_slots"] == []
    assert result["danger_veto"] is False


def test_assess_sets_danger_veto_from_the_user_text():
    plan = {"ok": True, "issues": [{"subcategory_code": "fire_lane_blocked", "slots": {}}]}
    result = assess(plan, [{"role": "user", "content": SMOKE_SOURCE}])
    assert result["danger_veto"] is True
    assert any(sig.startswith("danger_term:") for sig in result["uncertainty_signals"])


def test_assess_treats_major_mismatch_as_cautious():
    plan = {
        "ok": True,
        "major_mismatch": True,
        "selected_major_code": "traffic",
        "issues": [{"subcategory_code": "fire_equipment_fault", "slots": {}}],
    }
    result = assess(plan, [{"role": "user", "content": "消防设施老旧"}])
    assert result["uncertainty_level"] == "cautious"
    assert any(sig.startswith("major_mismatch:") for sig in result["uncertainty_signals"])


def test_assess_includes_vision_summary_in_the_source():
    plan = {
        "ok": True,
        "issues": [{"subcategory_code": "falling_object", "slots": {"source": "外墙广告牌"}}],
    }
    result = assess(plan, [{"role": "user", "content": "你看这张图"}],
                    vision_summary="[视觉分析] 外墙广告牌严重锈蚀")
    assert result["uncertainty_level"] == "ok"


def test_assess_ignores_plans_without_issues():
    result = assess({}, [{"role": "user", "content": "你好"}])
    assert result["uncertainty_level"] == "ok"
    assert result["ungrounded_slots"] == []
    assert result["grounding_ratio"] == 1.0
