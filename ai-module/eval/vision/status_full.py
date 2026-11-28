# -*- coding: utf-8 -*-
"""完整进度面板：采集 → 筛选 → 粗筛 → 标注 → 复检 → 定稿"""
import json
import os

HERE = r'E:\java\newProject\ai-module\eval\vision'
POOL = os.path.join(HERE, 'pool')
REAL = os.path.join(HERE, 'images_real')

tax = json.load(open(os.path.join(HERE, '_taxonomy.json'), encoding='utf-8-sig'))
subs = [(m['label'], s['code'], s['label']) for m in tax for s in m['subcategories']]

print('=' * 104)
print('视觉评测集构建进度')
print('=' * 104)
print(f'{"大类":<10}{"小类":<15}{"采集":>5}{"粗筛":>5}{"标注":>5}{"复检后":>7}{"定稿":>5}  阶段')
print('-' * 104)

rows = []
for mlab, code, slab in subs:
    d = os.path.join(POOL, code)
    pool = triage = ann = final = gt = 0

    if os.path.isdir(d):
        pool = len([f for f in os.listdir(d)
                    if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        tp = os.path.join(d, 'triage.json')
        if os.path.isfile(tp):
            try:
                triage = len(json.load(open(tp, encoding='utf-8'))['keep'])
            except Exception:
                pass
        ap = os.path.join(d, 'annotations.json')
        if os.path.isfile(ap):
            try:
                ann = len(json.load(open(ap, encoding='utf-8')).get('items', {}))
            except Exception:
                pass
        up = os.path.join(d, 'audit.json')
        if os.path.isfile(up) and ann:
            try:
                sus = len(json.load(open(up, encoding='utf-8')).get('suspect', []))
                final = ann - sus
            except Exception:
                final = ann
        else:
            final = ann

    gtp = os.path.join(REAL, code, 'ground_truth.json')
    if os.path.isfile(gtp):
        try:
            gt = len(json.load(open(gtp, encoding='utf-8-sig')).get('items', {}))
        except Exception:
            pass

    if gt:
        stage = '✅定稿'
    elif final:
        stage = '待落地'
    elif ann:
        stage = '复检后无合格'
    elif triage:
        stage = '待标注'
    elif pool:
        stage = '待粗筛'
    else:
        stage = '未采集'

    rows.append((mlab, slab, pool, triage, ann, final, gt, stage))

for r in rows:
    print(f'{r[0]:<10}{r[1]:<15}{r[2]:>5}{r[3]:>5}{r[4]:>5}{r[5]:>7}{r[6]:>5}  {r[7]}')

print('-' * 104)
S = lambda i: sum(x[i] for x in rows)
print(f'{"合计":<25}{S(2):>5}{S(3):>5}{S(4):>5}{S(5):>7}{S(6):>5}')
print()
print(f'采集 {S(2)} 张 → 粗筛 {S(3)} 张 → 标注 {S(4)} 张 → 复检后 {S(5)} 张 → 定稿 {S(6)} 张')
print(f'复检剔除率 {(1-S(5)/max(S(4),1))*100:.0f}%')
print()

thin = [(r[1], r[5]) for r in rows if 0 < r[5] < 15]
if thin:
    print(f'⚠️ 可用样本 <15 张的类别（{len(thin)} 个）：')
    for c, n in sorted(thin, key=lambda x: x[1]):
        print(f'    {c:<26} {n:>3} 张')
