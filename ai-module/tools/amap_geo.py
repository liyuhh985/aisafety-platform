"""高德地理编码：地址 -> 坐标 + 行政区。失败降级返回空坐标（不抛错）。"""
import logging
import requests
from config import AMAP_WEB_KEY

LOGGER = logging.getLogger(__name__)
GEO_URL = "https://restapi.amap.com/v3/geocode/geo"


def _empty():
    return {"longitude": None, "latitude": None,
            "province": "", "city": "", "district": "", "level": ""}


def geocode(address: str) -> dict:
    """返回 {longitude, latitude, province, city, district, level}。

    - 地址空、无 key、超时、返回异常 -> 全部降级为空，坐标 None，不抛错。
    - 命中 -> 坐标浮点 + 行政区；level=道路/门牌/POI 等。
    """
    if not address or not str(address).strip():
        return _empty()
    if not AMAP_WEB_KEY:
        LOGGER.warning("AMAP_WEB_KEY 未配置，地理编码降级")
        return _empty()
    try:
        resp = requests.get(
            GEO_URL,
            params={"address": str(address).strip(), "key": AMAP_WEB_KEY},
            timeout=5,
        )
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        LOGGER.warning("amap geocode 请求失败 address=%s error=%s", address, e)
        return _empty()
    if data.get("status") != "1":
        LOGGER.warning("amap geocode info=%s address=%s", data.get("info"), address)
        return _empty()
    geocodes = data.get("geocodes") or []
    if not geocodes:
        return _empty()
    g = geocodes[0]
    loc = g.get("location") or ""
    lng, lat = None, None
    if "," in loc:
        parts = loc.split(",", 1)
        try:
            lng = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            lng = lat = None
    return {
        "longitude": lng,
        "latitude": lat,
        "province": g.get("province", ""),
        "city": g.get("city", ""),
        "district": g.get("district", ""),
        "level": g.get("level", ""),
    }
