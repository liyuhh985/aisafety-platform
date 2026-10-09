"""AI 建任务 payload 的 Java 契约边界：送出去的字段类型必须收口。

回归背景：抽取模型/地理编码返回的 district 可能是空数组 []，直接进 payload
会让 Java 端 AiHazardDTO.district(String) 反序列化失败 -> 500 -> 任务建不出来。
"""


def _patch_pipeline(monkeypatch, info, geo, captured):
    # submit_from_history 在调用时解析模块全局名，所以 patch 模块属性即可。
    from tools import hazard_submit

    monkeypatch.setattr(hazard_submit, "_extract", lambda *a, **k: dict(info))
    monkeypatch.setattr(hazard_submit, "geocode", lambda address: dict(geo))

    def fake_create_hazard(payload):
        captured.update(payload)
        return {"ok": True, "hazardId": 42, "message": "已创建"}

    monkeypatch.setattr(hazard_submit, "create_hazard", fake_create_hazard)


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

    assert result["action"] == "created"
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
        "address": "三明市梅列区某路",
        "district": "梅列区",
        "longitude": 117.6,
        "latitude": 26.2,
        "description": "占道",
        "severity": 2,
        "imageUrl": "",
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
