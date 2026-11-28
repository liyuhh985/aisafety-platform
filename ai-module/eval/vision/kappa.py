# -*- coding: utf-8 -*-
"""
双模型独立标注 + 一致性检验（Cohen's Kappa）

模拟业界"两个标注员独立标注同一批图，算一致性"的流程。

标注员：
  A = DeepSeek V4.1 Flash
  B = GLM-5.3-Flash-X

两个模型使用**完全相同**的提示词，不共享任何中间结果，独立判断。

输出：
  kappa_result.json   一致率、Kappa、分歧清单
  控制台打印混淆矩阵

用法：
    python kappa.py --n 300
"""
import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = r'E:\java\newProject\ai-module\eval\vision'
_AI = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, _AI):
    if p not in sys.path:
        sys.path.insert(0, p)

POOL = os.path.join(HERE, 'pool')
OUT = os.path.join(HERE, 'kappa')

# 两个标注员
ANNOTATORS = {
    'A': ('opendesign', 'deepseek-v4.1-flash'),
    'B': ('opendesign', 'glm-5.3-flashx'),
}

# 统一提示词（两个模型用同一份，保证可比）
PROMPT = """你是城市安全隐患排查专家。请判断这张图片中的隐患属于哪一类。

只输出 JSON：
{"has_hazard": true或false, "major": "大类英文码", "sub": "小类英文码"}

类别表（大类码 / 小类码）：
traffic 交通与通行: road_occupancy(占道经营/乱堆乱放) vehicle_occupancy(车辆占道) blind_path_occupied(盲道占用) traffic_facility_damage(交通设施损坏)
municipal 市政设施: manhole_damage(井盖缺失破损) road_surface_collapse(路面塌陷) drainage_flood(排水积水) street_light_pole(路灯线杆损坏)
fire 消防安全: fire_lane_blocked(消防通道占用) fire_facility(消防设施/水源异常)
building 建筑安全: structural_damage(建筑结构损伤:危房/墙体开裂倾斜) facade_risk(外立面破损/坠落风险:瓷砖脱落/高空坠物) illegal_structure(临时构筑物/私搭乱建)
utility 电气与燃气: wire_fault(电线裸露/私拉乱接/施工临时用电) distribution_box_fault(配电设施故障) gas_leak(燃气泄漏) gas_pipe_aging(燃气管道老化)
construction 施工安全: construction_prot(施工防护缺失:无围挡/无警示) scaffold_guard(脚手架/临边防护) deep_pit(深基坑风险)
elevator_special 电梯与特种设备: elevator_trapped(电梯困人) elevator_stopped(停运/异响) elevator_inspection(超期未检)
environment_other 环境与其他: garbage_pile(垃圾堆积) sewage_overflow(污水外溢)

若画面无任何隐患，has_hazard 设 false，major/sub 留空字符串。
拿不准时按最接近的类别选。
只输出 JSON，不要解释。"""

VALID_MAJOR = {'traffic', 'municipal', 'fire', 'building', 'utility',
               'construction', 'elevator_special', 'environment_other'}
VALID_SUB = {
    'road_occupancy', 'vehicle_occupancy', 'blind_path_occupied', 'traffic_facility_damage',
    'manhole_damage', 'road_surface_collapse', 'drainage_flood', 'street_light_pole',
    'fire_lane_blocked', 'fire_facility',
    'structural_damage', 'facade_risk', 'illegal_structure',
    'wire_fault', 'distribution_box_fault', 'gas_leak', 'gas_pipe_aging',
    'construction_prot', 'scaffold_guard', 'deep_pit',
    'elevator_trapped', 'elevator_stopped', 'elevator_inspection',
    'garbage_pile', 'sewage_overflow',
}


def call(client, path, retries=3):
    for att in range(retries):
        try:
            out = client.analyze_json(path, PROMPT)
            if not isinstance(out, dict):
                return {'has_hazard': None, 'major': '', 'sub': '', '_bad': 'parse'}
            hz = out.get('has_hazard')
            major = str(out.get('major') or '').strip().lower()
            sub = str(out.get('sub') or '').strip().lower()
            if major not in VALID_MAJOR:
                major = ''
            if sub not in VALID_SUB:
                sub = ''
            return {'has_hazard': hz, 'major': major, 'sub': sub, '_bad': ''}
        except Exception as e:
            msg = str(e)
            if any(k in msg for k in ('402', '401', '403', 'Payment')):
                raise
            if att < retries - 1:
                time.sleep(2 * (att + 1))
    return {'has_hazard': None, 'major': '', 'sub': '', '_bad': 'error'}


def sample_images(n):
    """从未使用的图里抽样（这些图没有参与过调参，适合做一致性检验）"""
    cands = []
    for c in sorted(os.listdir(POOL)):
        d = os.path.join(POOL, c)
        if not os.path.isdir(d):
            continue
        ap = os.path.join(d, 'annotations.json')
        ann = {}
        if os.path.isfile(ap):
            try:
                ann = json.load(open(ap, encoding='utf-8'))
            except Exception:
                ann = {}
        used = set(ann.get('items', {})) | {x['file'] for x in ann.get('rejected', [])}
        for f in os.listdir(d):
            if not f.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            if f in used:
                continue
            cands.append((c, f, os.path.join(d, f)))

    # 按类别分层抽样，保证每类都有
    by_cat = defaultdict(list)
    for c, f, p in cands:
        by_cat[c].append((c, f, p))

    per = max(1, n // max(len(by_cat), 1))
    picked = []
    for c, lst in by_cat.items():
        picked.extend(lst[:per])
    picked = picked[:n]
    return picked


def cohen_kappa(a_labels, b_labels):
    """Cohen's Kappa（多类别）"""
    n = len(a_labels)
    if n == 0:
        return 0.0
    agree = sum(1 for x, y in zip(a_labels, b_labels) if x == y)
    po = agree / n
    ca = Counter(a_labels)
    cb = Counter(b_labels)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if pe == 1:
        return 1.0
    return (po - pe) / (1 - pe)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=300)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()

    from mimo_client import VisionClient

    clients = {}
    for key, (prov, model) in ANNOTATORS.items():
        c = VisionClient(prov)
        c.model = model          # 覆盖模型名
        clients[key] = c
        print(f'标注员 {key}: {model}')

    items = sample_images(args.n)
    print(f'\n抽样 {len(items)} 张，来自 {len(set(x[0] for x in items))} 个类别\n')

    results = {k: {} for k in ANNOTATORS}
    for key in ANNOTATORS:
        cl = clients[key]
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(call, cl, p): (c, f) for c, f, p in items}
            for fu in as_completed(futs):
                c, f = futs[fu]
                try:
                    results[key][(c, f)] = fu.result()
                except Exception as e:
                    results[key][(c, f)] = {'has_hazard': None, 'major': '',
                                            'sub': '', '_bad': str(e)[:40]}
                done += 1
        print(f'  标注员 {key} 完成 {done}/{len(items)}')

    # 对齐样本
    pairs = []
    for c, f, p in items:
        a = results['A'].get((c, f))
        b = results['B'].get((c, f))
        if not a or not b:
            continue
        if a['_bad'] or b['_bad']:
            continue
        pairs.append({'cat': c, 'file': f,
                      'A_sub': a['sub'] or '(无隐患)',
                      'B_sub': b['sub'] or '(无隐患)',
                      'A_major': a['major'], 'B_major': b['major']})

    print(f'\n有效配对 {len(pairs)} 组')

    a_sub = [x['A_sub'] for x in pairs]
    b_sub = [x['B_sub'] for x in pairs]
    a_maj = [x['A_major'] for x in pairs]
    b_maj = [x['B_major'] for x in pairs]

    k_sub = cohen_kappa(a_sub, b_sub)
    k_maj = cohen_kappa(a_maj, b_maj)
    agree_sub = sum(1 for x, y in zip(a_sub, b_sub) if x == y) / max(len(pairs), 1)
    agree_maj = sum(1 for x, y in zip(a_maj, b_maj) if x == y) / max(len(pairs), 1)

    print()
    print('=' * 70)
    print('一致性结果')
    print('=' * 70)
    print(f'  小类一致率   {agree_sub*100:.1f}%   Cohen\'s Kappa = {k_sub:.3f}')
    print(f'  大类一致率   {agree_maj*100:.1f}%   Cohen\'s Kappa = {k_maj:.3f}')
    print()
    if k_sub >= 0.8:
        lvl = '近乎完美（≥0.80）'
    elif k_sub >= 0.6:
        lvl = '较好（0.60-0.80）'
    elif k_sub >= 0.4:
        lvl = '中等（0.40-0.60）'
    else:
        lvl = '较差（<0.40）'
    print(f'  小类一致性等级：{lvl}')

    # 分歧明细
    disagree = [x for x in pairs if x['A_sub'] != x['B_sub']]
    print(f'\n分歧 {len(disagree)} 组（{len(disagree)/max(len(pairs),1)*100:.0f}%）')
    conf = Counter((x['A_sub'], x['B_sub']) for x in disagree)
    print('\n主要分歧模式（Top 15）：')
    for (a, b), n in conf.most_common(15):
        print(f'  {a:<26} vs {b:<26} {n:>3}')

    os.makedirs(OUT, exist_ok=True)
    json.dump({
        'n_pairs': len(pairs),
        'kappa_sub': k_sub, 'kappa_major': k_maj,
        'agree_sub': agree_sub, 'agree_major': agree_maj,
        'annotators': {k: v[1] for k, v in ANNOTATORS.items()},
        'pairs': pairs,
        'disagreements': disagree,
    }, open(os.path.join(OUT, 'kappa_result.json'), 'w', encoding='utf-8'),
        ensure_ascii=False, indent=1)
    print(f'\n→ kappa/kappa_result.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
