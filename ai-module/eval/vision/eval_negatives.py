# -*- coding: utf-8 -*-
"""
构建负样本评测集并测误报率

做法：
  1. 对采集来的负样本逐张审核（确认真的是正常场景）
  2. 合格的进评测集，标注 has_hazard=false
  3. 用模型跑一遍，统计误报率

误报率 = 模型判"有隐患"的正常图 / 正常图总数

用法：
    python eval_negatives.py --audit       # 先审核负样本是否真的正常
    python eval_negatives.py --eval        # 跑误报率测试
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

NEG = os.path.join(HERE, 'negatives')

LABEL = {
    "manhole_damage": "井盖缺失/破损", "fire_lane_blocked": "消防通道占用",
    "garbage_pile": "垃圾堆积", "road_occupancy": "占道经营/乱堆乱放",
    "vehicle_occupancy": "车辆占道", "blind_path_occupied": "盲道占用",
    "traffic_facility_damage": "交通设施损坏", "road_surface_collapse": "路面塌陷",
    "drainage_flood": "排水/积水", "street_light_pole": "路灯/线杆损坏",
    "fire_equipment_fault": "消防设施/水源异常", "structural_damage": "建筑结构损伤",
    "facade_risk": "外立面破损/坠落风险", "illegal_structure": "临时构筑物/私搭乱建",
    "wire_fault": "电线裸露/私拉乱接", "distribution_box_fault": "配电设施故障",
    "gas_leak": "燃气泄漏", "gas_pipe_aging": "燃气管道老化",
    "construction_prot": "施工防护缺失", "scaffold_guard": "脚手架/临边防护",
    "deep_pit": "深基坑风险", "elevator_trapped": "电梯困人",
    "elevator_stopped": "停运/异响", "elevator_inspection": "超期未检",
    "sewage_overflow": "污水外溢",
}

AUDIT_PROMPT = """这是负样本质检。这张图应该是一个【正常、合规、没有安全隐患】的场景。

它被归为「{label}」这一类，那么它应该是这一类场所的**正常状态**（如完好井盖、畅通消防通道、整洁街道）。

请判断：

**合格（ok=true）**：画面是正常场景，没有该类隐患，也没有其他明显隐患
**不合格（ok=false）**：
  - 画面里其实有隐患（包括别的类型的隐患）
  - 画面是商品图、示意图、插画、AI合成图
  - 带大面积售卖水印
  - 画面太模糊/主体不明，无法判断

只输出 JSON：
{{"ok": true或false, "what": "画面里是什么，20字内", "reason": "若不合格，为什么"}}
"""


def audit_negatives(client, workers=10):
    print('=' * 78)
    print('负样本审核')
    print('=' * 78)

    good, bad = {}, {}
    for cat in sorted(os.listdir(NEG)):
        d = os.path.join(NEG, cat)
        if not os.path.isdir(d):
            continue
        files = [f for f in os.listdir(d) if f.lower().endswith(('.jpg', '.png'))]
        if not files:
            continue

        label = LABEL.get(cat, cat)
        res = {}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(client.analyze_json, os.path.join(d, f),
                              AUDIT_PROMPT.format(label=label)): f for f in files}
            for fu in as_completed(futs):
                f = futs[fu]
                try:
                    res[f] = fu.result()
                except Exception:
                    res[f] = None

        ok_files = []
        bad_files = []
        for f, r in res.items():
            if isinstance(r, dict) and r.get('ok'):
                ok_files.append(f)
                good.setdefault(cat, []).append((f, r.get('what', '')))
            else:
                bad_files.append((f, (r or {}).get('reason', '解析失败')))
                bad.setdefault(cat, []).append((f, (r or {}).get('reason', '')))

        print(f'{cat:<24} {len(files):>2} 张 → 合格 {len(ok_files):>2}  剔除 {len(bad_files):>2}')

    total_ok = sum(len(v) for v in good.values())
    total_bad = sum(len(v) for v in bad.values())
    print()
    print(f'合计：合格 {total_ok} 张，剔除 {total_bad} 张')

    json.dump({c: [f for f, _ in v] for c, v in good.items()},
              open(os.path.join(NEG, 'negative_set.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'合格清单 → negatives/negative_set.json')
    return good


def eval_false_positive(client, workers=10):
    """对合格负样本跑模型，看有多少被误判为有隐患"""
    p = os.path.join(NEG, 'negative_set.json')
    if not os.path.isfile(p):
        print('先跑 --audit')
        return 1

    neg = json.load(open(p, encoding='utf-8'))

    from prompts import VISION_PROMPT

    print('=' * 78)
    print('误报率测试：正常图会不会被判成有隐患')
    print('=' * 78)

    total = 0
    fp = 0
    details = []

    for cat, files in sorted(neg.items()):
        if not files:
            continue
        res = {}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(client.analyze_json,
                              os.path.join(NEG, cat, f), VISION_PROMPT): f
                    for f in files}
            for fu in as_completed(futs):
                f = futs[fu]
                try:
                    res[f] = fu.result()
                except Exception:
                    res[f] = None

        cat_fp = 0
        for f in files:
            r = res.get(f)
            total += 1
            if not isinstance(r, dict):
                continue
            if r.get('has_hazard') is True:
                cat_fp += 1
                fp += 1
                details.append({
                    'cat': cat, 'file': f,
                    'pred': f"{r.get('major_category')}/{r.get('subcategory')}",
                    'desc': (r.get('description') or '')[:60],
                })
        flag = ' ⚠️' if cat_fp else ''
        print(f'{cat:<24} {len(files):>2} 张 → 误报 {cat_fp}{flag}')

    print()
    print('=' * 78)
    print(f'误报率 {fp}/{total} = {fp/max(total,1)*100:.1f}%')
    print('=' * 78)
    if details:
        print('\n误报明细：')
        for d in details:
            print(f"  [{d['cat']}] {d['file']:<14} 判为 {d['pred']:<30} {d['desc']}")

    json.dump({'total': total, 'fp': fp, 'rate': fp / max(total, 1),
               'details': details},
              open(os.path.join(NEG, 'fp_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--audit', action='store_true')
    ap.add_argument('--eval', action='store_true')
    ap.add_argument('--workers', type=int, default=10)
    args = ap.parse_args()

    from mimo_client import MiMoVisionClient
    client = MiMoVisionClient()
    print(f'模型={client.model}\n')

    if args.audit:
        audit_negatives(client, args.workers)
    if args.eval:
        eval_false_positive(client, args.workers)
    if not args.audit and not args.eval:
        print('用法: --audit 或 --eval')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
