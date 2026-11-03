# -*- coding: utf-8 -*-
"""盘点现有数据：哪些还能用、怎么用"""
import json
import os

HERE = r'E:\java\newProject\ai-module\eval\vision'
POOL = os.path.join(HERE, 'pool')

print('=' * 76)
print('现有数据盘点')
print('=' * 76)

# 1. 原始池子
pool_imgs = 0
used = 0
cats = []
for c in sorted(os.listdir(POOL)):
    d = os.path.join(POOL, c)
    if not os.path.isdir(d):
        continue
    n = len([f for f in os.listdir(d)
             if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
    if n == 0:
        continue
    pool_imgs += n
    ap = os.path.join(d, 'annotations.json')
    k = 0
    if os.path.isfile(ap):
        try:
            j = json.load(open(ap, encoding='utf-8'))
            k = len(j.get('items', {})) + len(j.get('rejected', []))
        except Exception:
            pass
    used += k
    cats.append((c, n, k))

print(f'\n【1. 原始图片池】pool/')
print(f'  总图片     {pool_imgs} 张')
print(f'  已处理     {used} 张（标注过）')
print(f'  未使用     {pool_imgs - used} 张  ← 可切 test 集')

# 2. 当前评测集
print(f'\n【2. 当前评测集】')
for name in ('images_real', 'images_merged'):
    d = os.path.join(HERE, name)
    if not os.path.isdir(d):
        print(f'  {name}: 不存在')
        continue
    tot = 0
    nc = 0
    for c in os.listdir(d):
        p = os.path.join(d, c, 'ground_truth.json')
        if os.path.isfile(p):
            try:
                j = json.load(open(p, encoding='utf-8-sig'))
                tot += len(j.get('items', {}))
                nc += 1
            except Exception:
                pass
    print(f'  {name}: {nc} 类 / {tot} 张')

# 3. 负样本
print(f'\n【3. 负样本】negatives/')
neg = os.path.join(HERE, 'negatives')
if os.path.isdir(neg):
    n = len([f for f in os.listdir(neg) if f.lower().endswith('.jpg')])
    tot = 0
    for c in os.listdir(neg):
        d = os.path.join(neg, c)
        if os.path.isdir(d):
            tot += len([f for f in os.listdir(d)
                        if f.lower().endswith(('.jpg', '.png'))])
    print(f'  原始采集   {tot} 张')
    p = os.path.join(neg, 'negative_set_clean.json')
    if os.path.isfile(p):
        j = json.load(open(p, encoding='utf-8'))
        print(f'  清洗合格   {sum(len(v) for v in j.values())} 张')

# 4. 二次核查结果
print(f'\n【4. 已产出的核查结果】')
for c in sorted(os.listdir(POOL)):
    p = os.path.join(POOL, c, 'audit2.json')
    if os.path.isfile(p):
        try:
            j = json.load(open(p, encoding='utf-8'))
            print(f'  {c}: {j["total"]} 张，不成立 {len(j["invalid"])}')
        except Exception:
            pass
