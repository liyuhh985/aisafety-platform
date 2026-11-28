# -*- coding: utf-8 -*-
"""
候选图自动筛选（无人值守预筛）

把 harvest 抓到的大池子，自动砍到"值得人看"的小池子。
四道闸门，逐层淘汰：

  闸门1 分辨率      短边 >= 800px，长宽比 0.4~2.5（排除超长截图/拼接长图）
  闸门2 重复        感知哈希去重（近似重复、裁剪变体）
  闸门3 水印/图库   角落水印检测 + 平铺水印检测 + 域名兜底
  闸门4 文字        可选：OCR 判断是否含"泄题文字"

输出：
  pool/<cat>/keep.json     通过全部闸门，进入人工/智能体复审
  pool/<cat>/drop.json     淘汰清单及原因
  pool/<cat>/review/       通过闸门的图片副本（便于逐张查看）

用法：
    python screen.py --cat manhole_damage
    python screen.py --all
    python screen.py --cat manhole_damage --ocr        # 开启文字闸门
"""
import argparse
import json
import os
import shutil
import sys
from collections import Counter

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(_HERE, "pool")

MIN_SIDE = 800
MIN_RATIO = 0.40          # h/w 下限：太扁的横幅图
MAX_RATIO = 2.50          # h/w 上限：太长的拼接图


# ---------------------------------------------------------------- 闸门1
def check_shape(img, path):
    h, w = img.shape[:2]
    if min(w, h) < MIN_SIDE:
        return False, f"分辨率短边{min(w,h)}<{MIN_SIDE}"
    r = h / w
    if r < MIN_RATIO:
        return False, f"过扁 h/w={r:.2f}"
    if r > MAX_RATIO:
        return False, f"过长 h/w={r:.2f}"
    return True, ""


# ---------------------------------------------------------------- 闸门2
def phash(img, size=8):
    """感知哈希，返回 64bit 的 uint64"""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (32, 32), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(np.float32(g))
    low = dct[:size, :size]
    med = np.median(low[1:, 1:])       # 去掉直流分量
    bits = (low > med).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def hamming(a, b):
    return bin(a ^ b).count("1")


# ---------------------------------------------------------------- 闸门3
def has_watermark(img):
    """
    水印检测（启发式，宁可放过不可错杀）：
      A. 平铺水印：高频斜向纹理在整幅图上周期性出现 → dreamstime/shutterstock 特征
      B. 底部条带：底部一条横贯的深色/浅色纯色条 + 边缘文字
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # A. 用 FFT 找周期性斜纹
    small = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA)
    f = np.fft.fftshift(np.abs(np.fft.fft2(small)))
    f = np.log1p(f)
    cy, cx = 128, 128
    # 屏蔽中心低频
    mask = np.ones_like(f)
    mask[cy - 12:cy + 12, cx - 12:cx + 12] = 0
    hp = f * mask
    if hp.size and hp.max() > 0:
        # 高频能量集中在少数几个点 → 周期性平铺水印
        flat = np.sort(hp.flatten())[::-1]
        top_ratio = flat[:40].sum() / (flat.sum() + 1e-6)
        if top_ratio > 0.42:
            return True, f"疑似平铺水印(周期性{top_ratio:.2f})"

    # B. 底部条带检测：最底部 8% 区域内，某一行几乎全是同一颜色
    band = gray[int(h * 0.92):, :]
    if band.size:
        row_std = band.std(axis=1)
        uniform_rows = (row_std < 8).sum()
        if uniform_rows > band.shape[0] * 0.5 and band.shape[0] > 10:
            # 且该条带与主图亮度差异明显
            main_mean = gray[:int(h * 0.85)].mean()
            band_mean = band.mean()
            if abs(main_mean - band_mean) > 25:
                return True, "底部水印条带"
    return False, ""


def blocked_domain(url):
    bad = ("dreamstime", "alamy", "shutterstock", "freepik", "istockphoto",
           "gettyimages", "123rf", "depositphotos", "vecteezy", "pngtree",
           "lovepik", "51miz", "zcool", "nipic", "taobao", "tmall", "jd.com",
           "1688", "amazon", "aliexpress", "shopee", "momoshop", "zhaopin",
           "58cdn", "anjuke", "lianjia", "ke.com")
    u = url.lower()
    return next((b for b in bad if b in u), None)


# ---------------------------------------------------------------- 闸门4
_ocr = None


def get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


LEAK_KW = {
    "fire_lane_blocked": ["消防通道", "消防车通道", "禁止占用", "严禁停车", "禁止停车", "生命通道"],
    "manhole_damage": ["井盖", "窨井", "检查井"],
    "garbage_pile": ["垃圾", "废弃物"],
    "no_barrier": ["围挡"],
    "no_warning": ["警示", "注意安全", "危险"],
    "vehicle_occupancy": ["禁止停车", "违停", "禁停", "盲道"],
    "blind_path_occupied": ["盲道", "禁止占用"],
    "road_occupancy": ["占道", "禁止摆摊"],
}


def ocr_leak(path, cat):
    kws = LEAK_KW.get(cat)
    if not kws:
        return False, ""
    try:
        res, _ = get_ocr()(path)
    except Exception:
        return False, ""
    texts = []
    for it in (res or []):
        try:
            t, s = str(it[1]).strip(), float(it[2])
        except Exception:
            continue
        if s >= 0.5 and len(t) >= 2:
            texts.append(t)
    for t in texts:
        for kw in kws:
            if kw in t:
                return True, t
    return False, ""


# ---------------------------------------------------------------- 主流程
def screen(cat, use_ocr=False):
    d = os.path.join(POOL, cat)
    sp = os.path.join(d, "sources.json")
    if not os.path.isfile(sp):
        print(f"[跳过] {cat}: 无 sources.json")
        return
    src = json.load(open(sp, encoding="utf-8"))
    items = src.get("items", [])
    print(f"\n{'='*70}\n[{cat}] 池中 {len(items)} 张 → 开始筛选")

    keep, drop = [], []
    hashes = []

    for it in items:
        f = it.get("file")
        p = os.path.join(d, f) if f else None
        if not p or not os.path.isfile(p):
            continue
        img = cv2.imread(p)
        if img is None:
            drop.append({**it, "reason": "无法解码"})
            continue

        # 闸门3a 域名
        bd = blocked_domain(it.get("url", ""))
        if bd:
            drop.append({**it, "reason": f"图库/电商域名({bd})"})
            continue

        # 闸门1 尺寸
        ok, why = check_shape(img, p)
        if not ok:
            drop.append({**it, "reason": why})
            continue

        # 闸门2 去重
        ph = phash(img)
        dup = next((k for h, k in hashes if hamming(ph, h) <= 6), None)
        if dup:
            drop.append({**it, "reason": f"与{dup}近似重复"})
            continue
        hashes.append((ph, f))

        # 闸门3b 水印
        wm, why = has_watermark(img)
        if wm:
            drop.append({**it, "reason": why})
            continue

        # 闸门4 文字泄题（可选）
        if use_ocr:
            leak, txt = ocr_leak(p, cat)
            if leak:
                drop.append({**it, "reason": f"文字泄题({txt})", "text": txt})
                continue

        keep.append(it)

    # 导出
    review = os.path.join(d, "review")
    if os.path.isdir(review):
        shutil.rmtree(review)
    os.makedirs(review, exist_ok=True)
    for it in keep:
        shutil.copy2(os.path.join(d, it["file"]), os.path.join(review, it["file"]))

    json.dump({"category": cat, "total": len(items), "keep": len(keep),
               "drop": len(drop), "items": keep},
              open(os.path.join(d, "keep.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"category": cat, "items": drop},
              open(os.path.join(d, "drop.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    reasons = Counter(x["reason"].split("(")[0].split("与")[0] for x in drop)
    print(f"  保留 {len(keep)} / {len(items)}  ({len(keep)/max(len(items),1)*100:.0f}%)")
    for r, n in reasons.most_common(8):
        print(f"    - {r}: {n}")
    return len(keep), len(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ocr", action="store_true", help="开启文字泄题闸门")
    args = ap.parse_args()

    if args.all:
        cats = [c for c in sorted(os.listdir(POOL))
                if os.path.isfile(os.path.join(POOL, c, "sources.json"))]
    elif args.cat:
        cats = [args.cat]
    else:
        print("用法: python screen.py --cat <类别> | --all [--ocr]")
        return 1

    tk = tt = 0
    for c in cats:
        r = screen(c, use_ocr=args.ocr)
        if r:
            tk += r[0]
            tt += r[1]
    print(f"\n{'='*70}\n合计：{tt} 张 → 保留 {tk} 张 ({tk/max(tt,1)*100:.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
