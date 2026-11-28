# -*- coding: utf-8 -*-
"""
汇总 6 类标注核查结果，重算准确率

两种口径：
  A 保守：标注不成立的图直接剔除（评测集缩小，但干净）
  B 修正：按 actual 改判（保持样本量，但依赖模型对 actual 的判断）

推荐 A，因为 B 里 actual 是模型说的，用它当答案会循环论证。
"""
import json
import os
import re
from collections import Counter, defaultdict

HERE = r'E:\java\newProject\ai-module\eval\vision'
POOL = os.path.join(HERE, 'pool')
EVAL_OUT = r'E:\java\newProject\ai-module\db\eval_real_output.txt'

MERGE = {
    'falling_object': 'facade_risk', 'facade_fall': 'facade_risk',
    'dangerous_building': 'structural_damage', 'wall_crack_lean': 'structural_damage',
    'exposed_wire': 'wire_fault', 'illegal_wiring': 'wire_fault',
    'temporary_power': 'wire_fault',
    'fire_equipment_fault': 'fire_facility', 'fire_water_abnormal': 'fire_facility',
    'no_warning': 'construction_prot', 'no_barrier': 'construction_prot',
    'sewage_odor': 'sewage_overflow',
}

TAX = json.load(open(os.path.join(HERE, '_taxonomy_final.json'), encoding='utf-8'))
CODE2 = {}
for m in TAX:
    for s in m['subcategories']:
        CODE2[s['code']] = (m['code'], m['label'], s['label'])


def norm(s):
    if not s or s.startswith('('):
        return None
    return s.split('/')[-1].lower() if '/' in s else s.lower()


# 汇总所有核查结果
AUDITED = ['gas_leak', 'sewage_odor', 'no_warning', 'no_barrier',
           'illegal_structure', 'blind_path_occupied']
FIRE_RC = json.load(open(os.path.join(POOL, 'fire_lane_blocked', 'reclass.json'),
                         encoding='utf-8')) if os.path.isfile(
    os.path.join(POOL, 'fire_lane_blocked', 'reclass.json')) else {}
SEW_RC = json.load(open(os.path.join(POOL, 'sewage_odor', 'reclass.json'),
                        encoding='utf-8')) if os.path.isfile(
    os.path.join(POOL, 'sewage_odor', 'reclass.json')) else {}

print('=' * 82)
print('6 类标注核查汇总')
print('=' * 82)
print(f'{"类别":<26}{"总数":>5}{"成立":>5}{"不成立":>7}{"问题率":>8}')
print('-' * 82)
T_BAD = 0
T_ALL = 0
bad_files = defaultdict(set)   # 标注不成立的文件
for c in AUDITED:
    p = os.path.join(POOL, c, 'audit2.json')
    if not os.path.isfile(p):
        continue
    j = json.load(open(p, encoding='utf-8'))
    total = j['total']
    inv = j['invalid']
    name = CODE2.get(c, ('', '', c))[2]
    print(f'{name:<26}{total:>5}{j["valid"]:>5}{len(inv):>7}'
          f'{len(inv)/total*100:>7.0f}%')
    T_BAD += len(inv)
    T_ALL += total
    for x in inv:
        bad_files[c].add(x['file'])
print('-' * 82)
print(f'{"合计":<26}{T_ALL:>5}{T_ALL-T_BAD:>5}{T_BAD:>7}{T_BAD/T_ALL*100:>7.0f}%')

# 读评测结果
txt = open(EVAL_OUT, encoding='utf-8', errors='replace').read()
pat = re.compile(r'\[(正确|大类对|错误|漏报|误报|失败)\]\s+(\S+)\s+(\S+)\s+期望=(\S+)\s+实际=(\S+)')
rows = [dict(zip(['mark', 'cat', 'file', 'exp', 'act'], m.groups()))
        for m in pat.finditer(txt)]


def calc(drop_bad, use_fire_rc, use_sew_rc):
    per = defaultdict(Counter)
    T = Counter()
    for r in rows:
        e, a = norm(r['exp']), norm(r['act'])
        cat = r['cat']

        # 剔除标注不成立的
        if drop_bad and r['file'] in bad_files.get(cat, set()):
            continue

        if use_sew_rc and e == 'sewage_odor' and r['file'] in SEW_RC:
            e = SEW_RC[r['file']]
        if use_fire_rc and e == 'fire_lane_blocked' and r['file'] in FIRE_RC:
            e = FIRE_RC[r['file']]

        if e:
            e = MERGE.get(e, e)
        if a:
            a = MERGE.get(a, a)

        key = e or '(负样本)'
        s = per[key]
        s['total'] += 1
        T['total'] += 1
        if e is None and a is None:
            s['ok'] += 1; T['ok'] += 1
        elif e is None:
            s['fp'] += 1; T['fp'] += 1
        elif a is None:
            s['fn'] += 1; T['fn'] += 1
        elif e == a:
            s['ok'] += 1; T['ok'] += 1
        else:
            em = CODE2.get(e, ('?',))[0]
            am = CODE2.get(a, ('?',))[0]
            if em != '?' and em == am:
                s['major'] += 1; T['major'] += 1
            else:
                s['wrong'] += 1; T['wrong'] += 1
    return per, T


print()
print('=' * 82)
print('准确率变化')
print('=' * 82)
_, T0 = calc(False, False, False)
print(f'  未清洗                    {T0["ok"]:>4}/{T0["total"]} = '
      f'{T0["ok"]/T0["total"]*100:>5.1f}%')

_, T1 = calc(False, True, True)
print(f'  仅改判(消防/污水)          {T1["ok"]:>4}/{T1["total"]} = '
      f'{T1["ok"]/T1["total"]*100:>5.1f}%')

per2, T2 = calc(True, True, True)
print(f'  剔除标注错误 + 改判        {T2["ok"]:>4}/{T2["total"]} = '
      f'{T2["ok"]/T2["total"]*100:>5.1f}%')
print()
print(f'  大类命中（清洗后）         {T2["ok"]+T2["major"]}/{T2["total"]} = '
      f'{(T2["ok"]+T2["major"])/T2["total"]*100:.1f}%')
print(f'  漏报 {T2["fn"]}   误报 {T2["fp"]}')

print()
print('=' * 82)
print('清洗后分项（按准确率排序）')
print('=' * 82)
print(f'{"类别":<30}{"样本":>5}{"严格":>5}{"准确率":>7}')
print('-' * 82)
for k, s in sorted(per2.items(), key=lambda x: -(x[1]['ok'] / max(x[1]['total'], 1))):
    name = CODE2.get(k, ('', '', '(负样本)'))[2]
    tot = s['total']
    print(f'{name:<30}{tot:>5}{s["ok"]:>5}{s["ok"]/tot*100:>6.0f}%')

json.dump({
    'cleaned': {'strict': T2['ok'] / T2['total'],
                'major': (T2['ok'] + T2['major']) / T2['total'],
                'n': T2['total'], 'fn': T2['fn'], 'fp': T2['fp']},
    'raw': {'strict': T0['ok'] / T0['total'], 'n': T0['total']},
    'dropped': T_BAD,
}, open(os.path.join(HERE, '_clean_result.json'), 'w', encoding='utf-8'),
    ensure_ascii=False, indent=1)
print('\n→ _clean_result.json')
