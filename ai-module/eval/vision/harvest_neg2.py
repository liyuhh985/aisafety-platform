# -*- coding: utf-8 -*-
"""补采施工类、电梯类负样本（原关键词无结果）"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HERE = r'E:\java\newProject\ai-module\eval\vision'
NEG = os.path.join(HERE, 'negatives')
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
MIN_SIDE = 800
MIN_BYTES = 15000

# 更宽的关键词
PLAN = {
    "construction_prot": ["建筑工地 规范 施工", "工地 安全 文明施工",
                          "施工现场 标准化", "市政工程 施工 围挡"],
    "scaffold_guard": ["脚手架 搭设 规范", "建筑工地 外架", "工程 脚手架 安全"],
    "deep_pit": ["基坑 支护 施工", "建筑工地 基础 开挖 规范", "工程 基坑 施工"],
    "elevator_trapped": ["电梯 正常运行", "电梯 轿厢 内部", "写字楼 电梯"],
    "elevator_stopped": ["电梯 楼层 显示", "电梯 按钮 面板", "商场 电梯 运行"],
    "elevator_inspection": ["电梯 检验合格证", "电梯 使用标志", "特种设备 标识"],
    "other": ["城市 街道 整洁", "城市 景观 道路"],
}


def fetch(s, kw, pages=2):
    out = []
    for p in range(pages):
        url = ("https://image.baidu.com/search/acjson?tn=resultjson_com&ipn=rj"
               "&ct=201326592&fp=result&queryWord={q}&cl=2&lm=-1&ie=utf-8&oe=utf-8"
               "&st=-1&word={q}&pn={pn}&rn=30").format(
                   q=requests.utils.quote(kw), pn=p * 30)
        try:
            r = s.get(url, timeout=25, headers={"Referer": "https://image.baidu.com/"})
            if len(r.content) < 500:
                time.sleep(1.5)
                s.get("https://image.baidu.com/", timeout=15)
                r = s.get(url, timeout=25, headers={"Referer": "https://image.baidu.com/"})
            j = r.json()
            for x in (j.get("data") or []):
                if not isinstance(x, dict):
                    continue
                ru = (x.get("replaceUrl") or [{}])[0]
                real = ru.get("ObjURL") or ru.get("ObjUrl")
                if not real or not real.startswith("http"):
                    continue
                out.append({"url": real, "w": x.get("width") or 0,
                            "h": x.get("height") or 0})
        except Exception:
            pass
        time.sleep(0.3)
    return out


def dl(item):
    try:
        r = requests.get(item["url"], timeout=25,
                         headers={"User-Agent": UA,
                                  "Referer": "https://image.baidu.com/"})
        if r.status_code != 200:
            return None
        d = r.content
        if len(d) < MIN_BYTES:
            return None
        from PIL import Image
        import io
        try:
            im = Image.open(io.BytesIO(d))
            w, h = im.size
        except Exception:
            return None
        if min(w, h) < MIN_SIDE:
            return None
        return d
    except Exception:
        return None


s = requests.Session()
s.headers.update({"User-Agent": UA})
try:
    s.get('https://image.baidu.com/', timeout=15)
except Exception:
    pass

total = 0
for cat, kws in PLAN.items():
    d = os.path.join(NEG, cat)
    os.makedirs(d, exist_ok=True)
    cands, seen = [], set()
    for kw in kws:
        for c in fetch(s, kw, 2):
            if c['url'] in seen:
                continue
            seen.add(c['url'])
            if c['w'] and c['h'] and min(c['w'], c['h']) < MIN_SIDE:
                continue
            cands.append(c)

    prefix = 'NEG' + cat[:3].upper()
    n = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(dl, c) for c in cands[:32]]
        for fu in as_completed(futs):
            if n >= 8:
                break
            data = fu.result()
            if data:
                n += 1
                open(os.path.join(d, f'{prefix}{n:02d}.jpg'), 'wb').write(data)
    print(f'{cat:<26} 候选 {len(cands):>3} → 下载 {n}')
    total += n

print(f'\n补给 {total} 张')
