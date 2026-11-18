"""AI 建任务 payload 的 Java 契约边界：送出去的字段类型必须收口。

回归背景：抽取模型/地理编码返回的 district 可能是空数组 []，直接进 payload
会让 Java 端 AiHazardDTO.district(String) 反序列化失败 -> 500 -> 任务建不出来。
"""


def _patch_pipeline(monkeypatch, info, geo, captured):
    # submit_from_history 在调用时解析模块全局名，所以 patch 模块属性即可。
    from tools import hazard_submit

    monkeypatch.setattr(hazard_submit, "_extract", lambda *a, **k: dict(info))
    monkeypatch.setattr(hazard_submit, "geocode", lambda address: dict(geo))

    def fake_enqueue(user_id, session_id, payload):
        captured.update(payload)
        return {"ok": True, "requestId": "req-test", "message": "已受理"}

    monkeypatch.setattr(hazard_submit, "enqueue_hazard_create", fake_enqueue)


def test_submit_passes_confirmation_request_id_to_enqueue(monkeypatch):
    from tools import hazard_submit

    captured = {}
    monkeypatch.setattr(hazard_submit, "_extract", lambda *a, **k: {
        "category": "traffic/road_occupancy",
        "address": "三明市梅列区某路",
        "description": "占道",
        "severity": 1,
    })
    monkeypatch.setattr(hazard_submit, "geocode", lambda address: {
        "longitude": 117.6, "latitude": 26.2, "district": "梅列区",
    })

    def fake_enqueue(user_id, session_id, payload, *, request_id=None):
        captured["request_id"] = request_id
        return {"ok": True, "requestId": request_id, "status": "PENDING"}

    monkeypatch.setattr(hazard_submit, "enqueue_hazard_create", fake_enqueue)
    result = hazard_submit.submit_from_history(
        1, [], "占道了", request_id="req-confirm-fixed",
    )

    assert result["requestId"] == "req-confirm-fixed"
    assert captured["request_id"] == "req-confirm-fixed"


def test_submit_payload_types_are_coerced_at_the_java_boundary(monkeypatch):
    captured = {}
    _patch_pipeline(
        monkeypatch,
        info={"category": "traffic/road_occupancy", "address": "三明市梅列区某路",
              "district": [], "description": ["a", "b"], "severity": "严重"},
        geo={"longitude": 117.6, "latitude": 26.2, "district": []},
        captured=captured,
    )
    from tools import hazard_submit

    result = hazard_submit.submit_from_history(1, [], "占道了")

    assert result["action"] == "accepted"
    payload = captured
    assert isinstance(payload["district"], str) and payload["district"] == ""
    assert isinstance(payload["description"], str) and payload["description"] == "a、b"
    assert isinstance(payload["severity"], int) and 0 <= payload["severity"] <= 2
    for key in ("category", "address", "imageUrl", "report"):
        assert isinstance(payload[key], str), key


def test_submit_payload_normal_strings_stay_identical(monkeypatch):
    captured = {}
    _patch_pipeline(
        monkeypatch,
        info={"category": "traffic/road_occupancy", "address": "三明市梅列区某路",
              "district": "梅列区", "description": "占道", "severity": 2,
              "imageUrl": "", "report": ""},
        geo={"longitude": 117.6, "latitude": 26.2, "district": "梅列区"},
        captured=captured,
    )
    from tools import hazard_submit

    hazard_submit.submit_from_history(1, [], "占道了")

    assert captured == {
        "userId": 1,
        "category": "traffic/road_occupancy",
        "categoryList": ["traffic/road_occupancy"],
        "address": "三明市梅列区某路",
        "district": "梅列区",
        "longitude": 117.6,
        "latitude": 26.2,
        "description": "占道",
        "severity": 2,
        "imageUrl": "",
        "imageFileId": None,
        "report": "",
    }


def test_submit_severity_zero_is_not_treated_as_default(monkeypatch):
    captured = {}
    _patch_pipeline(
        monkeypatch,
        info={"category": "traffic/road_occupancy", "address": "三明市梅列区某路",
              "district": "梅列区", "description": "占道", "severity": 0},
        geo={"longitude": 117.6, "latitude": 26.2, "district": "梅列区"},
        captured=captured,
    )
    from tools import hazard_submit

    hazard_submit.submit_from_history(1, [], "占道了")
    assert captured["severity"] == 0

import json as _json


_GEO = {"longitude": 117.6, "latitude": 26.2, "district": "梅列区"}


def _patch_llm_pipeline(monkeypatch, content, captured, geo=None):
    # 走真实 _extract（只把 LLM 调用换成固定 JSON），再兜住 geocode/入队。
    from tools import hazard_submit

    monkeypatch.setattr(
        hazard_submit._extractor, "_call_llm",
        lambda *a, **k: {"content": content},
    )
    monkeypatch.setattr(hazard_submit, "geocode", lambda address: dict(geo or _GEO))

    def fake_enqueue(user_id, session_id, payload):
        captured.clear()
        captured.update(payload)
        return {"ok": True, "requestId": "req-test", "message": "已受理"}

    monkeypatch.setattr(hazard_submit, "enqueue_hazard_create", fake_enqueue)
    return hazard_submit


def _llm_info(category_list=None, category=None, **extra):
    data = {"address": "三明市梅列区某路", "district": "梅列区",
            "description": "隐患描述", "severity": 1}
    if category_list is not None:
        data["categoryList"] = category_list
    if category is not None:
        data["category"] = category
    data.update(extra)
    return _json.dumps(data)


def test_two_categories_keep_order_and_first_is_category(monkeypatch):
    captured = {}
    hs = _patch_llm_pipeline(
        monkeypatch,
        _llm_info(["municipal/manhole_damage", "fire/fire_equipment_fault"]),
        captured,
    )
    assert hs.submit_from_history(1, [], "井盖坏了，消防设施也不正常")["action"] == "accepted"
    assert captured["categoryList"] == ["municipal/manhole_damage", "fire/fire_equipment_fault"]
    assert captured["category"] == "municipal/manhole_damage"


def test_category_list_dedupes_preserving_order(monkeypatch):
    captured = {}
    hs = _patch_llm_pipeline(
        monkeypatch,
        _llm_info(["fire/fire_equipment_fault", "消防设施", "fire/fire_equipment_fault",
                   "utility/exposed_wire"]),
        captured,
    )
    hs.submit_from_history(1, [], "消防设施老旧，还有裸露电线")
    assert captured["categoryList"] == ["fire/fire_equipment_fault", "utility/exposed_wire"]
    assert captured["category"] == "fire/fire_equipment_fault"


def test_category_list_truncates_to_three(monkeypatch):
    captured = {}
    hs = _patch_llm_pipeline(
        monkeypatch,
        _llm_info(["municipal/manhole_damage", "fire/fire_equipment_fault",
                   "utility/gas_leak", "building/wall_crack_lean",
                   "elevator_special/elevator_stopped"]),
        captured,
    )
    hs.submit_from_history(1, [], "多处隐患")
    assert captured["categoryList"] == [
        "municipal/manhole_damage", "fire/fire_equipment_fault", "utility/gas_leak"]
    assert captured["category"] == "municipal/manhole_damage"


def test_category_list_bad_format_falls_back_to_single_category(monkeypatch):
    captured = {}
    # categoryList 不是列表且解析不出 -> 退回单类别 category，不崩。
    hs = _patch_llm_pipeline(
        monkeypatch,
        _llm_info(category_list="消防安全", category="fire/fire_equipment_fault"),
        captured,
    )
    assert hs.submit_from_history(1, [], "消防设施老旧")["action"] == "accepted"
    assert captured["categoryList"] == ["fire/fire_equipment_fault"]
    assert captured["category"] == "fire/fire_equipment_fault"


def test_category_list_unparseable_without_category_is_no_category(monkeypatch):
    from tools import hazard_submit

    def forbid_external(*_, **__):
        raise AssertionError("no_category 路径不应调用外部服务")

    monkeypatch.setattr(hazard_submit, "geocode", forbid_external)
    monkeypatch.setattr(hazard_submit, "enqueue_hazard_create", forbid_external)
    monkeypatch.setattr(
        hazard_submit._extractor, "_call_llm",
        lambda *a, **k: {"content": _llm_info(
            category_list=[123, {}, "不存在的类别"], category="")},
    )
    result = hazard_submit.submit_from_history(1, [], "说不清的隐患")
    assert result["action"] == "no_category"


def test_payload_category_defends_against_empty_category(monkeypatch):
    captured = {}
    _patch_pipeline(
        monkeypatch,
        info={"category": "", "categoryList": ["fire/fire_equipment_fault", "utility/gas_leak"],
              "address": "三明市梅列区某路", "district": "梅列区",
              "description": "隐患", "severity": 1},
        geo=_GEO,
        captured=captured,
    )
    from tools import hazard_submit

    assert hazard_submit.submit_from_history(1, [], "x")["action"] == "accepted"
    assert captured["categoryList"] == ["fire/fire_equipment_fault", "utility/gas_leak"]
    assert captured["category"] == "fire/fire_equipment_fault"


def test_submit_payload_carries_uploaded_image_file_id(monkeypatch):
    captured = {}
    _patch_pipeline(
        monkeypatch,
        info={"category": "traffic/road_occupancy", "address": "三明市梅列区某路",
              "district": "梅列区", "description": "占道", "severity": 1},
        geo=_GEO,
        captured=captured,
    )
    from tools import hazard_submit

    hazard_submit.submit_from_history(
        1, [], "占道了", image_url="http://minio/safety-images/a.png", image_file_id=99)
    assert captured["imageUrl"] == "http://minio/safety-images/a.png"
    assert captured["imageFileId"] == 99
