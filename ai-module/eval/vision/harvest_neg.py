# -*- coding: utf-8 -*-
"""
负样本采集：每类找正常场景

用途：测真实误报率。现在样本里几乎全是有隐患的图，
     所以"误报率 0%"不可信。

负样本要求：
  · 画面是正常、合规、无隐患的场景
  · 与目标类别是同一类场所（如"井盖破损"的负样本是完好井盖）
  · 不能用另一类隐患冒充正常（如用垃圾堆当"盲道占用"的负样本）

用法：
    python harvest_neg.py --plan          # 只打印关键词计划
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HERE = r'E:\java\newProject\ai-module\eval\vision'
NEG_DIR = os.path.join(HERE, 'negatives')

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
MIN_SIDE = 800
MIN_BYTES = 15000

# 每类的负样本关键词（描述"正常状态"）
PLAN = {
    "manhole_damage": ["井盖 完好 平整", "市政 井盖 规范 路面"],
    "fire_lane_blocked": ["消防通道 畅通 无占用", "消防通道 地面 清晰"],
    "garbage_pile": ["街道 干净 整洁", "垃圾分类亭 规范"],
    "road_occupancy": ["人行道 畅通 整洁", "街道 无占道"],
    "vehicle_occupancy": ["停车位 规范停车", "车辆 有序停放"],
    "blind_path_occupied": ["盲道 完好 畅通", "人行道 盲道 整洁"],
    "traffic_facility_damage": ["交通标志 完好", "护栏 完好 道路"],
    "road_surface_collapse": ["路面 平整 完好", "沥青路面 平整"],
    "drainage_flood": ["路面 无积水", "排水口 通畅"],
    "street_light_pole": ["路灯 完好 正常", "电线杆 整齐"],
    "fire_equipment_fault": ["消火栓 完好", "灭火器 规范 摆放"],
    "fire_facility": ["消防设施 完好 检查"],
    "structural_damage": ["房屋 墙面 完好", "建筑 结构 良好"],
    "facade_risk": ["外墙 完好 整洁", "楼体 外立面 正常"],
    "illegal_structure": ["小区 楼体 规整", "建筑 外观 规范"],
    "wire_fault": ["电线 整齐 规范", "线路 架设 规整"],
    "distribution_box_fault": ["配电箱 关闭 完好", "电箱 规范"],
    "gas_leak": ["燃气管道 完好", "天然气管道 规范"],
    "gas_pipe_aging": ["燃气管道 新 完好"],
    "construction_prot": ["工地 围挡 规范", "施工现场 围挡 齐全"],
    "scaffold_guard": ["脚手架 规范 防护", "工地 安全防护 到位"],
    "deep_pit": ["基坑 防护 到位", "工地 安全 规范"],
    "elevator_trapped": ["电梯 正常运行", "电梯 轿厢 内景"],
    "elevator_stopped": ["电梯 正常 运行 显示"],
    "elevator_inspection": ["电梯 检验合格标志", "电梯 年检 合格"],
    "sewage_overflow": ["河道 清澈", "排水沟 干净"],
    "other": ["城市 街道 整洁 有序"],
}


def fetch_baidu(session, kw, pages=2):
    out = []
    for p in range(pages):
        url = ("https://image.baidu.com/search/acjson?tn=resultjson_com&ipn=rj"
               "&ct=201326592&fp=result&queryWord={q}&cl=2&lm=-1&ie=utf-8&oe=utf-8"
               "&st=-1&word={q}&pn={pn}&rn=30").format(
                   q=requests.utils.quote(kw), pn=p * 30)
        try:
            r = session.get(url, timeout=25,
                            headers={"Referer": "https://image.baidu.com/"})
            if len(r.content) < 500:
                time.sleep(1.5)
                session.get("https://image.baidu.com/", timeout=15)
                r = session.get(url, timeout=25,
                                headers={"Referer": "https://image.baidu.com/"})
            j = r.json()
            for x in (j.get("data") or []):
                if not isinstance(x, dict):
                    continue
                ru = (x.get("replaceUrl") or [{}])[0]
                real = ru.get("ObjURL") or ru.get("ObjUrl")
                if not real or not real.startswith("http"):
                    continue
                out.append({"url": real, "w": x.get("width") or 0,
                            "h": x.get("height") or 0,
                            "title": (x.get("fromPageTitleEnc") or "")[:50]})
        except Exception:
            pass
        time.sleep(0.3)
    return out


def download(item, outdir, prefix):
    try:
        r = requests.get(item["url"], timeout=25,
                         headers={"User-Agent": UA,
                                  "Referer": "https://image.baidu.com/"})
        if r.status_code != 200:
            return False, None
        data = r.content
        if len(data) < MIN_BYTES:
            return False, None
        from PIL import Image
        import io
        try:
            im = Image.open(io.BytesIO(data))
            w, h = im.size
        except Exception:
            return False, None
        if min(w, h) < MIN_SIDE:
            return False, None
        return True, data
    except Exception:
        return False, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plan', action='store_true')
    ap.add_argument('--cat')
    ap.add_argument('-n', '--per-cat', type=int, default=8)
    args = ap.parse_args()

    if args.plan:
        print(f'{"类别":<26}{"负样本关键词"}')
        print('-' * 76)
        for k, v in PLAN.items():
            print(f'{k:<26}{" / ".join(v)}')
        return 0

    cats = [args.cat] if args.cat else list(PLAN)
    os.makedirs(NEG_DIR, exist_ok=True)

    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    try:
        s.get('https://image.baidu.com/', timeout=15)
    except Exception:
        pass

    total = 0
    for cat in cats:
        kws = PLAN.get(cat, [])
        if not kws:
            continue
        outdir = os.path.join(NEG_DIR, cat)
        os.makedirs(outdir, exist_ok=True)

        cands, seen = [], set()
        for kw in kws:
            got = fetch_baidu(s, kw, pages=2)
            for c in got:
                if c['url'] in seen:
                    continue
                seen.add(c['url'])
                if c['w'] and c['h'] and min(c['w'], c['h']) < MIN_SIDE:
                    continue
                cands.append(c)

        prefix = 'NEG' + cat[:3].upper()
        got_n = 0
        idx = 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {}
            for c in cands[:args.per_cat * 4]:
                futs[ex.submit(download, c, outdir, prefix)] = c
            for fu in as_completed(futs):
                if got_n >= args.per_cat:
                    break
                ok, data = fu.result()
                if ok:
                    got_n += 1
                    idx += 1
                    fn = f'{prefix}{idx:02d}.jpg'
                    with open(os.path.join(outdir, fn), 'wb') as f:
                        f.write(data)

        print(f'{cat:<26} 候选 {len(cands):>3} → 下载 {got_n} 张')
        total += got_n

    print(f'\n合计 {total} 张负样本 → {NEG_DIR}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
