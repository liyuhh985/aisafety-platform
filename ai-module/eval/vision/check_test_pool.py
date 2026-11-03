# -*- coding: utf-8 -*-
"""检查未使用图片能否支撑 test 集（每类 15-20 张）"""
import json
import os

HERE = r'E:\java\newProject\ai-module\eval\vision'
POOL = os.path.join(HERE, 'pool')

# 加载合并映射
MM = json.load(open(os.path.join(HERE, '_merge_final.json'), encoding='utf-8'))
MERGE = MM['merge']
NEW = MM['new_cats']
CODE2NAME = {k: v[2] for k, v in NEW.items()}

# 污水/消防改判
def load_rc(cat):
    p = os.path.join(POOL, cat, 'reclass.json')
    if os.path.isfile(p):
        return json.load(open(p, encoding='utf-8'))
    return {}
SEW_RC = load_rc('sewage_odor')
FIRE_RC = load_rc('fire_lane_blocked')

# 二次核查不成立的
def load_audit(cat):
    p = os.path.join(POOL, cat, 'audit2.json')
    if os.path.isfile(p):
        try:
            j = json.load(open(p, encoding='utf-8'))
            return {x['file'] for x in j.get('invalid', [])}
        except Exception:
            return set()
    return set()

print('=' * 80)
print('可用作 test 集的素材（每类）')
print('=' * 80)
print(f'{"类别":<28}{"池中":>5}{"已用":>5}{"剩余":>5}  建议')
print('-' * 80)

available = {}
for c in sorted(os.listdir(POOL)):
    d = os.path.join(POOL, c)
    if not os.path.isdir(d):
        continue
    # 已用（annotations 里的 items + rejected）
    ap = os.path.join(d, 'annotations.json')
    if not os.path.isfile(ap):
        continue
    try:
        ann = json.load(open(ap, encoding='utf-8'))
    except Exception:
        continue
    used = set(ann.get('items', {})) | {x['file'] for x in ann.get('rejected', [])}

    # 池中所有图
    allimg = set(f for f in os.listdir(d)
                 if f.lower().endswith(('.jpg', '.jpeg', '.png')))
    remain = allimg - used

    # 排除核查不成立的（那些图本身有问题）
    bad = load_audit(c)
    remain_ok = remain - bad

    newcode = MERGE.get(c, c)
    name = CODE2NAME.get(newcode, c)
    available.setdefault(newcode, []).extend(
        [os.path.join(d, f) for f in remain_ok])

for code in sorted(available, key=lambda x: -len(available[x])):
    n = len(available[code])
    name = CODE2NAME.get(code, code)
    if n >= 20:
        sug = '✅ 够（可切 20）'
    elif n >= 10:
        sug = '△ 偏少（可切 10-15）'
    elif n > 0:
        sug = '⚠️ 很少'
    else:
        sug = '❌ 无'
    print(f'{name:<28}{"":>5}{"":>5}{n:>5}  {sug}')

total = sum(len(v) for v in available.values())
print('-' * 80)
print(f'{"合计可切":<28}{"":>5}{"":>5}{total:>5} 张')
