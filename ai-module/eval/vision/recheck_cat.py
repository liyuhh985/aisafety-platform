# -*- coding: utf-8 -*-
"""
通用类别标注复核

对指定类别逐张核查：这张图真的是该类别吗？
用与消防通道相同的思路 —— 让模型按"可见证据"判断，而不是靠关键词。

对每个类别定义"核心视觉判据"：
  燃气泄漏   → 必须能看到管道破损/泄漏点/气泡/水渍痕迹；只有爆炸火球不算
  污水外溢   → 必须是可见的黑臭污水/排放口；垃圾堆或清水积水不算
  施工防护缺失 → 必须有明确的施工开挖面，且缺少围挡或警示
  临时构筑物 → 必须能看到加建的构筑物（棚、房、外扩）
  盲道占用   → 必须能看到盲道砖，且被物体占用

输出：<cat>/audit2.json，列出应改判的条目
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = r'E:\java\newProject\ai-module\eval\vision'
_AI = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, _AI):
    if p not in sys.path:
        sys.path.insert(0, p)

POOL = os.path.join(HERE, 'pool')

# 各类别的核心判据
CRITERIA = {
    "gas_leak": {
        "label": "燃气泄漏",
        "must": "能看到燃气管道的破损、开裂、腐蚀穿孔、接口松脱、或泄漏迹象（气泡、结霜、明显气味提示牌）",
        "not": "爆炸火球、浓烟、消防演练、完好的燃气管道、燃气罐正常摆放、只是闻到味道的文字描述",
    },
    "sewage_odor": {
        "label": "污水外溢",
        "must": "能看到可见的污水：黑臭水体、污水从管道/井口外溢、污水横流",
        "not": "垃圾堆积为主、清水或雨水积水、单纯的路面积水、只是有异味描述",
    },
    "no_warning": {
        "label": "无安全警示",
        "must": "能看到施工开挖面/坑洞/危险区域，且现场确实没有警示牌、锥桶、警戒线",
        "not": "有警示设施的现场、非施工场景、坑洞本身（那是深基坑）",
    },
    "no_barrier": {
        "label": "未设置围挡",
        "must": "能看到施工区域边界，且没有连续的实体围挡/护栏/隔离",
        "not": "围挡齐全的工地、只是没有警示牌（那是无安全警示）",
    },
    "illegal_structure": {
        "label": "临时构筑物/私搭乱建",
        "must": "能看到明显的加建构筑物：楼顶搭棚、阳台外扩、占道铁皮房、私建围墙、违法加层",
        "not": "只是外墙破损、只是堆放杂物、正常遮阳棚、规划无法从照片判断",
    },
    "blind_path_occupied": {
        "label": "盲道占用",
        "must": "能看到盲道砖（条状/点状凸起），且被车辆、摊位、杂物占用或压占",
        "not": "看不到盲道、普通人行道被占、盲道完好无占用",
    },
}

PROMPT = """你是图片标注质检员。这张图被标为「{label}」隐患，请核查标注是否成立。

## 标准

**成立（valid=true）必须满足：**
{ok}

**不成立（valid=false）的典型情况：**
{bad}

## 判断要点

- 只看**画面里真实可见的东西**，不推测、不脑补
- 拿不准时倾向 valid=true（宁可放过）
- 如果画面主体其实是别的隐患类型，在 actual 里写清楚

只输出 JSON：
{{"valid": true或false, "evidence": "画面里能看到什么，25字内", "actual": "若valid=false，画面实际是什么隐患；若true留空"}}
"""


def check(client, path, cat):
    c = CRITERIA[cat]
    prompt = PROMPT.format(label=c['label'], ok=c['must'], bad=c['not'])
    try:
        out = client.analyze_json(path, prompt)
        if isinstance(out, dict):
            return out
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cat', required=True)
    ap.add_argument('--workers', type=int, default=10)
    args = ap.parse_args()

    cat = args.cat
    if cat not in CRITERIA:
        print(f'未定义判据: {cat}')
        return 1

    from mimo_client import MiMoVisionClient
    client = MiMoVisionClient()

    p = os.path.join(POOL, cat, 'annotations.json')
    if not os.path.isfile(p):
        print('无 annotations.json')
        return 1
    items = json.load(open(p, encoding='utf-8')).get('items', {})

    print(f'[{cat}] 核查 {len(items)} 张  模型={client.model}\n')

    res = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(check, client,
                          os.path.join(POOL, cat, 'review', f), cat): f
                for f in items}
        for fu in as_completed(futs):
            f = futs[fu]
            res[f] = fu.result()

    valid, invalid, failed = [], [], []
    for f, r in res.items():
        if not r:
            failed.append(f)
        elif r.get('valid'):
            valid.append((f, r.get('evidence', '')))
        else:
            invalid.append((f, r.get('evidence', ''), r.get('actual', '')))

    print('=' * 84)
    print(f'成立   {len(valid):>3} 张')
    print(f'不成立 {len(invalid):>3} 张')
    print(f'失败   {len(failed):>3} 张')
    print('=' * 84)

    if invalid:
        print('\n--- 标注不成立的 ---')
        for f, ev, act in invalid:
            print(f'  {f:<16} 画面: {ev[:38]:<40} 实际: {act[:24]}')

    out = {
        'total': len(items),
        'valid': len(valid),
        'invalid': [{'file': f, 'evidence': ev, 'actual': act}
                    for f, ev, act in invalid],
    }
    json.dump(out, open(os.path.join(POOL, cat, 'audit2.json'), 'w',
                        encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n→ {cat}/audit2.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
