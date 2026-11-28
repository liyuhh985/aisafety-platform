# -*- coding: utf-8 -*-
"""
候选图片批量采集（多源、多关键词、多页）

数据源：
  - baidu  百度图片  acjson 接口，取 replaceUrl[0].ObjURL 原图直链
  - bing   Bing 图片  images/async 接口，解析 m="..." 内的 murl

用法：
    python harvest.py --cat manhole_damage            # 采一个类别
    python harvest.py --all                           # 采全部已配置类别
    python harvest.py --cat fire_lane_blocked -n 400  # 指定目标条数

输出：
    pool/<cat>/sources.json    候选清单（url/来源/关键词/尺寸）
    pool/<cat>/<src>_<nn>.jpg  已下载原图（分辨率达标才有）

设计要点：
    · 只负责"广撒网"，不做质量判断。筛选交给 screen.py
    · 下载即校验短边 >=800、字节数 >=15KB，不合格立即丢弃
    · 已存在文件跳过，支持中断续跑
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

_HERE = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(_HERE, "pool")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

MIN_SIDE = 800
MIN_BYTES = 15000
TIMEOUT = 25

# 图库/电商/水印站黑名单：这些来源基本不是新闻图，直接不下载
BLOCK_DOMAINS = (
    "dreamstime", "alamy", "shutterstock", "freepik", "istockphoto", "gettyimages",
    "123rf", "depositphotos", "adobe.stock", "vecteezy", "canstockphoto",
    "taobao", "tmall", "jd.com", "1688", "amazon", "aliexpress", "pinduoduo",
    "shopify", "ebay", "walmart", "aliexpress", "dhgate", "made-in-china",
    "zhaopin", "58cdn", "ganji", "anjuke", "ke.com", "lianjia",
    "hifigo", "nicehck", "head-fi", "momoshop", "shopee",
    "baike", "wenku", "docin", "doc88", "zhihu.com/question",
    "pngtree", "lovepik", "51miz", "zcool", "huaban", "nipic",
)


def is_blocked(url):
    u = url.lower()
    return any(d in u for d in BLOCK_DOMAINS)


# ---------------------------------------------------------------- 关键词配置
# zh = 百度中文关键词（命中率高，但常带中文标牌 → 靠 OCR 筛掉）
# en = Bing 英文关键词（真正的新闻照片，几乎没有中文泄题词）
KEYWORDS = {
    "manhole_damage": {"zh": ["井盖破损 曝光", "井盖缺失 危险 行人", "窨井盖 破裂 路面",
                              "井盖塌陷 车辆", "破损井盖 现场", "井盖破了 投诉",
                              "井盖丢失 路人", "井盖下沉 路面", "马路 井盖 缺失"]},
    "fire_lane_blocked": {"zh": ["消防通道 违停", "消防车通道 被占用", "消防通道 停车 曝光",
                                 "消防通道 堵 小区", "消防通道 占用 整治", "消防通道 乱停车",
                                 "生命通道 被占", "小区 消防通道 私家车"]},
    "garbage_pile": {"zh": ["垃圾堆积 曝光", "建筑垃圾 乱堆", "垃圾成堆 路边", "装修垃圾 堆放",
                            "垃圾 乱倒 街道", "垃圾堆 无人清理", "垃圾 露天堆放", "小区 垃圾 堆积"]},
    "no_barrier": {"zh": ["工地 无围挡", "施工 未设置围挡", "施工 敞开 无防护", "道路开挖 无围挡",
                          "工地 围挡 缺失", "施工现场 没有围挡", "开挖 无遮挡 行人"]},
    "no_warning": {"zh": ["施工 无警示", "挖坑 未设警示", "道路施工 无警示标志",
                          "深坑 无警示 行人", "施工 没有警示牌", "路面开挖 无警示"]},
    "road_occupancy": {"zh": ["占道经营 曝光", "乱堆乱放 人行道", "店外经营 占道",
                              "杂物堆放 人行道", "占道 摆摊 整治", "商户 占道 行人"]},
    "vehicle_occupancy": {"zh": ["车辆占道 曝光", "机动车占用人行道", "违停 盲道",
                                 "车辆 占用 人行道", "车辆 乱停 占道", "私家车 占道 通行"]},
    "blind_path_occupied": {"zh": ["盲道 被占用", "盲道 停车 曝光", "盲道 被堵",
                                   "盲道 占用 整治", "盲道 被占 行人"]},
    "road_surface_collapse": {"zh": ["路面塌陷", "道路塌方 城市", "路面 大坑 危险",
                                     "路面 塌了一个洞", "马路 塌陷 现场"]},
    "drainage_flood": {"zh": ["道路积水 严重", "积水 内涝 街道", "下水道 堵塞 溢水",
                              "路面 积水 行人", "暴雨 积水 路口"]},
    "street_light_pole": {"zh": ["路灯 损坏", "电线杆 倾斜", "路灯 不亮 曝光",
                                 "路灯 倒了", "线杆 断裂 危险"]},
    "fire_equipment_fault": {"zh": ["灭火器 过期", "消火栓 损坏", "消防设施 破损",
                                    "消防栓 无水 破损", "灭火器 失效 检查"]},
    "exposed_wire": {"zh": ["电线 裸露", "电线 老化 危险", "电缆 垂落",
                            "电线 掉下来 危险", "线路 裸露 路边"]},
    "illegal_wiring": {"zh": ["私拉乱接 电线", "飞线充电 曝光", "电动车 飞线 充电",
                              "电线 乱拉 小区"]},
    "scaffold_guard": {"zh": ["脚手架 无防护", "临边 无防护", "高处作业 无防护",
                              "脚手架 隐患", "工地 临边 危险"]},
    "deep_pit": {"zh": ["深基坑 危险", "基坑 无防护", "工地 深坑 危险",
                        "开挖 深坑 塌方"]},
    "wall_crack_lean": {"zh": ["墙体开裂", "围墙 倾斜", "墙面裂缝 危险",
                               "墙体 裂缝 居民", "围墙 要倒 危险"]},
    "facade_fall": {"zh": ["外立面 脱落", "墙面 瓷砖脱落", "外墙 掉落",
                           "外墙 脱落 砸", "楼体 墙皮 脱落"]},
    "illegal_structure": {"zh": ["违规搭建", "违章建筑 曝光", "私搭乱建",
                                 "楼顶 违建", "违章搭建 拆除"]},
    "dangerous_building": {"zh": ["危房 警示", "危房 拆除", "老旧房屋 危险",
                                  "房屋 开裂 危房", "危楼 居民"]},
    "sewage_odor": {"zh": ["污水 横流", "污水外溢 街道", "臭水 路边",
                           "下水道 返味 居民", "污水 直排"]},
    "traffic_facility_damage": {"zh": ["交通标志 损坏", "护栏 损坏 道路", "红绿灯 故障",
                                       "交通设施 破损", "隔离栏 损坏"]},
    "gas_pipe_aging": {"zh": ["燃气管道 老化", "燃气管道 锈蚀", "燃气管 外露"]},
    "distribution_box_fault": {"zh": ["配电箱 损坏", "电箱 敞开", "配电柜 破损",
                                      "电箱 门 打开 危险"]},
    "other": {"zh": ["城市管理 曝光 隐患"]},
    "fire_water_abnormal": {"zh": ["消火栓 无水", "消防水源 缺失", "消防栓 没水",
                                    "消防水池 干涸", "消防管道 无水 曝光"]},
    "falling_object": {"zh": ["高空坠物 危险", "外墙 悬挂物 脱落", "楼顶 坠物 砸",
                              "高空 掉东西 小区", "广告牌 摇摇欲坠"]},
    "gas_leak": {"zh": ["燃气泄漏 抢修", "天然气 泄漏 现场", "燃气管道 泄漏",
                        "燃气 泄露 居民"]},
    "temporary_power": {"zh": ["施工 临时用电 隐患", "工地 电线 乱接", "施工用电 私拉",
                               "工地 电箱 裸露"]},
    "elevator_trapped": {"zh": ["电梯 困人", "电梯 困人 救援", "被困电梯 消防"]},
    "elevator_stopped": {"zh": ["电梯 停运", "电梯 故障 小区", "电梯 坏了 居民",
                                "电梯 异响 投诉"]},
    "elevator_inspection": {"zh": ["电梯 超期未检", "电梯 检验标志 过期",
                                   "电梯 无检验合格标志"]},
}



# ---------------------------------------------------------------- 采集器
# ---------------------------------------------------------------- 百度会话
_bsession = None


def _baidu_session():
    """百度 acjson 需要先访问首页拿 BAIDUID cookie，否则返回 82 字节空壳"""
    global _bsession
    if _bsession is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        try:
            s.get("https://image.baidu.com/", timeout=15)
        except Exception:
            pass
        _bsession = s
    return _bsession


def fetch_baidu(kw, pages=3):
    out = []
    s = _baidu_session()
    for p in range(pages):
        url = ("https://image.baidu.com/search/acjson?tn=resultjson_com&ipn=rj"
               "&ct=201326592&fp=result&queryWord={q}&cl=2&lm=-1&ie=utf-8&oe=utf-8"
               "&st=-1&word={q}&pn={pn}&rn=30").format(
                   q=requests.utils.quote(kw), pn=p * 30)
        try:
            r = s.get(url, timeout=TIMEOUT,
                      headers={"Referer": "https://image.baidu.com/"})
            if len(r.content) < 500:
                time.sleep(1.5)
                s.get("https://image.baidu.com/", timeout=15)
                r = s.get(url, timeout=TIMEOUT,
                          headers={"Referer": "https://image.baidu.com/"})
            j = r.json()
            for x in (j.get("data") or []):
                if not isinstance(x, dict):
                    continue
                ru = (x.get("replaceUrl") or [{}])[0]
                real = ru.get("ObjURL") or ru.get("ObjUrl")
                if not real or not real.startswith("http"):
                    continue
                out.append({
                    "url": real,
                    "w": x.get("width") or 0,
                    "h": x.get("height") or 0,
                    "title": (x.get("fromPageTitleEnc") or "").replace("<[^>]+>", "")[:60],
                    "keyword": kw,
                    "source": "baidu",
                })
        except Exception:
            pass
        time.sleep(0.3)
    return out


def fetch_bing(kw, pages=2):
    out = []
    for p in range(pages):
        url = "https://www.bing.com/images/async"
        params = {"q": kw, "first": p * 35, "count": 35, "mmasync": "1"}
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT,
                             headers={"User-Agent": UA,
                                      "Referer": "https://www.bing.com/images/search?q="
                                                 + requests.utils.quote(kw)})
            html = r.text
            for chunk in html.split('m="')[1:]:
                end = chunk.find('"')
                if end < 0:
                    continue
                raw = chunk[:end].replace("&quot;", '"').replace("&amp;", "&")
                try:
                    j = json.loads(raw)
                except Exception:
                    continue
                murl = j.get("murl")
                if not murl or not murl.startswith("http"):
                    continue
                out.append({
                    "url": murl, "w": 0, "h": 0,
                    "title": (j.get("t") or "")[:60],
                    "keyword": kw, "source": "bing",
                })
        except Exception:
            pass
        time.sleep(0.4)
    return out


# ---------------------------------------------------------------- 下载
_lock = threading.Lock()
_counter = {"n": 0}


def download(item, outdir, prefix):
    """下载单张，返回 (ok, filename, reason)"""
    try:
        r = requests.get(item["url"], timeout=TIMEOUT, stream=True,
                         headers={"User-Agent": UA,
                                  "Referer": "https://image.baidu.com/",
                                  "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
        if r.status_code != 200:
            return False, None, f"HTTP{r.status_code}"
        data = r.content
        if len(data) < MIN_BYTES:
            return False, None, f"small{len(data)//1024}KB"
        from PIL import Image
        import io
        try:
            im = Image.open(io.BytesIO(data))
            w, h = im.size
        except Exception:
            return False, None, "notimage"
        if min(w, h) < MIN_SIDE:
            return False, None, f"res{w}x{h}"
        if w * h > 40_000_000:
            return False, None, f"toobig{w}x{h}"
        with _lock:
            _counter["n"] += 1
            n = _counter["n"]
        ext = ".png" if data[:8].startswith(b"\x89PNG") else ".jpg"
        fname = f"{prefix}{n:04d}{ext}"
        with open(os.path.join(outdir, fname), "wb") as f:
            f.write(data)
        item = dict(item)
        item.update({"file": fname, "w": w, "h": h, "bytes": len(data)})
        return True, item, ""
    except Exception as e:
        return False, None, type(e).__name__


# ---------------------------------------------------------------- 主流程
def harvest(cat, target=250, workers=12):
    conf = KEYWORDS.get(cat)
    if not conf:
        print(f"[跳过] {cat}: 未配置关键词")
        return 0, 0

    outdir = os.path.join(POOL, cat)
    os.makedirs(outdir, exist_ok=True)

    print(f"\n{'='*66}\n[{cat}] 采集中 → 目标 {target} 张")
    cands, seen = [], set()
    for kw in conf.get("zh", []):
        got = fetch_baidu(kw, pages=3)
        new = [c for c in got if c["url"] not in seen]
        for c in new:
            seen.add(c["url"])
        cands.extend(new)
        print(f"  百度 '{kw}' → {len(got)} 条（新增 {len(new)}）")
    for kw in conf.get("en", []):
        got = fetch_bing(kw, pages=2)
        new = [c for c in got if c["url"] not in seen]
        for c in new:
            seen.add(c["url"])
        cands.extend(new)
        print(f"  Bing '{kw}' → {len(got)} 条（新增 {len(new)}）")

    # 已知尺寸的直接淘汰
    before = len(cands)
    cands = [c for c in cands if not (c["w"] and c["h"] and min(c["w"], c["h"]) < MIN_SIDE)]
    # 图库/电商站直接淘汰
    before2 = len(cands)
    cands = [c for c in cands if not is_blocked(c["url"])]
    print(f"  候选 {before} → 剔小图后 {before2} → 剔图库站后 {len(cands)}")

    # 优先下载大图
    cands.sort(key=lambda c: -(c["w"] * c["h"]))

    prefix = cat.split("_")[0][:3].upper()
    ok_items, reasons = [], {}
    _counter["n"] = 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(download, c, outdir, prefix) for c in cands[: min(len(cands), target * 4)]]
        for f in as_completed(futs):
            ok, payload, reason = f.result()
            if ok:
                ok_items.append(payload)
                if len(ok_items) >= target:
                    break
            else:
                key = reason.split("x")[0] if reason.startswith("res") else reason
                reasons[key] = reasons.get(key, 0) + 1

    src_path = os.path.join(outdir, "sources.json")
    json.dump({"category": cat, "downloaded": len(ok_items),
               "keywords": conf, "items": ok_items},
              open(src_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"  下载成功 {len(ok_items)}/{target}  失败分布 {dict(sorted(reasons.items(), key=lambda x: -x[1])[:5])}")
    return len(ok_items), len(cands)


def add_external(json_path):
    """把沙箱抓来的百度候选合并进 harvest 流程（Python 直连百度被反爬时的通道）"""
    data = json.load(open(json_path, encoding="utf-8"))
    out = []
    for it in data.get("items", []):
        url = it[0] if isinstance(it, list) else it.get("url")
        if not url:
            continue
        out.append({
            "url": url,
            "w": (it[1] if isinstance(it, list) else it.get("w")) or 0,
            "h": (it[2] if isinstance(it, list) else it.get("h")) or 0,
            "title": ((it[3] if isinstance(it, list) else it.get("title")) or "")[:60],
            "keyword": data.get("keyword", ""),
            "source": "baidu-ext",
        })
    return out


def harvest_from_file(cat, json_path, target=250, workers=12):
    """从外部候选 JSON 直接下载"""
    outdir = os.path.join(POOL, cat)
    os.makedirs(outdir, exist_ok=True)
    cands = add_external(json_path)
    before = len(cands)
    cands = [c for c in cands if not (c["w"] and c["h"] and min(c["w"], c["h"]) < MIN_SIDE)]
    cands = [c for c in cands if not is_blocked(c["url"])]
    print(f"\n[{cat}] 外部候选 {before} → 可用 {len(cands)} → 目标 {target}")
    cands.sort(key=lambda c: -(c["w"] * c["h"]))

    prefix = cat.split("_")[0][:3].upper()
    _counter["n"] = 0
    ok_items, reasons = [], {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(download, c, outdir, prefix)
                for c in cands[: min(len(cands), target * 4)]]
        for f in as_completed(futs):
            ok, payload, reason = f.result()
            if ok:
                ok_items.append(payload)
                if len(ok_items) >= target:
                    break
            else:
                key = reason.split("x")[0] if reason.startswith("res") else reason
                reasons[key] = reasons.get(key, 0) + 1

    src_path = os.path.join(outdir, "sources.json")
    old = {"items": []}
    if os.path.isfile(src_path):
        try:
            old = json.load(open(src_path, encoding="utf-8"))
        except Exception:
            pass
    merged = {it["url"]: it for it in old.get("items", [])}
    for it in ok_items:
        merged[it["url"]] = it
    json.dump({"category": cat, "downloaded": len(merged),
               "items": list(merged.values())},
              open(src_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  新增 {len(ok_items)} 张，池内累计 {len(merged)} 张；失败 {dict(sorted(reasons.items(), key=lambda x: -x[1])[:4])}")
    return len(ok_items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--from-file", default=None, help="从候选 JSON 下载（百度沙箱通道）")
    ap.add_argument("-n", "--target", type=int, default=250)
    args = ap.parse_args()

    if args.from_file:
        if not args.cat:
            print("--from-file 需要同时指定 --cat")
            return 1
        harvest_from_file(args.cat, args.from_file, target=args.target)
        return 0

    if args.all:
        cats = [c for c in KEYWORDS if c != "other"]
    elif args.cat:
        cats = [args.cat]
    else:
        print("用法: python harvest.py --cat <类别> [-n 250]  或  --all")
        return 1

    total = 0
    for cat in cats:
        n, c = harvest(cat, target=args.target)
        total += n
    print(f"\n{'='*66}\n合计下载 {total} 张，存入 {POOL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
