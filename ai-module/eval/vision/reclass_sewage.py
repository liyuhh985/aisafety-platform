# -*- coding: utf-8 -*-
"""
重新归类「污水/异味」类的误标（修正版）

关键修正：判断"画面主体是什么"，不是"关键词出现了什么"。
  "沟渠内水体灰黑，水面漂浮垃圾" → 主体是水体 → 污水
  "垃圾桶满溢，周边垃圾堆积"     → 主体是垃圾 → 垃圾堆积

判断顺序：
  1. 先看有没有"水体主语"（河道/沟渠/水面/排污口/涵洞/黑臭水体）
     → 有，则判污水（垃圾只是漂浮物）
  2. 再看是不是垃圾桶/垃圾堆为主体
     → 是，判垃圾堆积
  3. 再看是不是路面积水
     → 是，判排水积水
  4. 都不明确 → 保留原类（保守）
"""
import json
import os

POOL = r'E:\java\newProject\ai-module\eval\vision\pool'
P = os.path.join(POOL, 'sewage_odor', 'annotations.json')

j = json.load(open(P, encoding='utf-8'))
items = j.get('items', {})

# 水体主语：这些词出现，说明画面主体是"一片水"
WATER_BODY = ['河道', '沟渠', '水面', '水体', '排污口', '排污管', '涵洞',
              '黑臭水体', '河面', '池塘', '水沟', '排水沟', '排污水',
              '污水直排', '管道向河', '排入河']

# 垃圾主体：垃圾桶、垃圾堆
GARBAGE_MAIN = ['垃圾桶', '垃圾箱', '垃圾堆', '成堆垃圾', '垃圾堆积',
                '生活垃圾散落', '废旧物', '垃圾散落', '堆满垃圾',
                '垃圾成山', '大量垃圾']

# 路面积水
ROAD_WATER = ['路面积水', '路面大片', '路面有', '车道', '漫流', '蔓延至人行道',
              '积水漫溢', '路缘', '路沿']

# 封闭排水设施（属市政设施，不是污水外溢主体）
DRAIN_STRUCT = ['井盖', '检查井', '雨水篦', '篦子']


def classify(text):
    t = text or ''
    has_water_body = any(k in t for k in WATER_BODY)
    has_garbage = any(k in t for k in GARBAGE_MAIN)
    has_road = any(k in t for k in ROAD_WATER)

    # 1. 水体主语优先 —— 但如果是"垃圾桶/垃圾堆"为主体且无水体，跳过
    if has_water_body and not (has_garbage and not has_water_body):
        return 'sewage_odor', '水体主体'

    # 2. 垃圾主体
    if has_garbage:
        return 'garbage_pile', '垃圾为主体'

    # 3. 水体（无垃圾主体时）
    if has_water_body:
        return 'sewage_odor', '水体主体'

    # 4. 路面积水
    if has_road:
        return 'drainage_flood', '路面水'

    return 'sewage_odor', '不明确→保留'


groups = {'sewage_odor': [], 'garbage_pile': [], 'drainage_flood': []}
reasons = []
for f, rec in items.items():
    t = rec.get('key_evidence') or ''
    cat, why = classify(t)
    groups[cat].append((f, t))
    reasons.append((f, cat, why, t))

print('=' * 76)
print('污水/异味 类重新归类（修正版）')
print('=' * 76)
for k, v in groups.items():
    print(f'  → {k:<18} {len(v):>3} 张')

print()
print('挪走的明细：')
for f, cat, why, t in reasons:
    if cat != 'sewage_odor':
        print(f'  {f:<14} → {cat:<16} [{why}] {t[:40]}')

out = {f: cat for f, cat, why, t in reasons}
json.dump(out, open(os.path.join(POOL, 'sewage_odor', 'reclass.json'), 'w',
                    encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'\n已写入 reclass.json')
