"""机器预抽取的地址必须过结构判据：宁可判空（回到「追问地址」），
也不能静默建出一条位置完全错误的工单。

实测背景：把「楼道」这类相对位置交给高德，会被匹配到别的城市
（"楼道" -> 广州番禺区，坐标 113.416586/22.960305），比"没有地址"更糟。

注意这条判据只决定「确认卡片要不要预填地址」；用户在卡片里/追问里
自己写的地址不做这个判据（人的输入一律认）。
"""
from tools import hazard_submit as hs


class _FakeExtractor:
    def __init__(self, content):
        self._content = content

    def _call_llm(self, messages, cancellation=None):
        return {"content": self._content}


def test_rejects_relative_or_too_short_text():
    for text in ("楼道", "楼下", "家门口", "这里", "", "1", "小区", "   "):
        assert hs._looks_like_address(text) is False, text


def test_accepts_locatable_addresses():
    for text in ("三明万达广场东南角消防栓", "三明市梅列区东新四路万达广场", "XX路 12 号"):
        assert hs._looks_like_address(text) is True, text


def test_extract_location_drops_relative_place(monkeypatch):
    monkeypatch.setattr(hs, "_location_extractor",
                        _FakeExtractor('{"address":"楼道","district":"三明市"}'))
    assert hs.extract_location([], "楼道里的消防栓生锈了，已经出不了水") == ""


def test_extract_location_keeps_real_address(monkeypatch):
    monkeypatch.setattr(hs, "_location_extractor",
                        _FakeExtractor('{"address":"三明万达广场东南角","district":"三明市"}'))
    assert hs.extract_location([], "三明万达广场东南角的消防栓出不了水") == "三明万达广场东南角"