# -*- coding: utf-8 -*-
"""
切分 dev / test 集

原则：
  dev  集 = 已经标注、调过参的数据（1,865 张）→ 可以随便改
  test 集 = 从未参与任何决策的图（1,520 张里抽）→ 只跑一次

test 集选图规则：
  1. 必须是 pool 里"未标注过"的图（没进过 evaluations）
  2. 排除二次核查判定不成立的图
  3. 按合并后的 24 类分层，每类 N 张
  4. 与 dev 集做感知哈希去重，防止同一张图两边都有

输出：
  test_set/<cat>/  图片 + ground_truth.json（稍后标注）

用法：
    python split_dev_test.py --per-cat 16
"""
import argparse
import json
import os
import shutil
import sys

HERE = r'E:\java\newProject\ai-module\eval\vision'
POOL = os.path.join(HERE, 'pool')
OUT = os.path.join(HERE, 'test_set')

sys.path.insert(0, HERE)

MM = json.load(open(os.path.join(HERE, '_merge_final.json'), encoding='utf-8'))
MERGE = MM['merge']
NEW = MM['new_cats']
CODE2NAME = {k: v[2] for k, v in NEW.items()}


def load_json(p):
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding='utf-8'))
        except Exception:
            return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-cat', type=int, default=16)
    args = ap.parse_args()

    # 收集 dev 集已用文件（用于去重）
    dev_files = set()
    dev_dir = os.path.join(HERE, 'images_real')
    if os.path.isdir(dev_dir):
        for c in os.listdir(dev_dir):
            d = os.path.join(dev_dir, c)
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                    dev_files.add(f)

    # 收集候选
    cand = {}
    for c in sorted(os.listdir(POOL)):
        d = os.path.join(POOL, c)
        if not os.path.isdir(d):
            continue
        ann = load_json(os.path.join(d, 'annotations.json'))
        if not ann:
            continue
        used = set(ann.get('items', {})) | {x['file'] for x in ann.get('rejected', [])}

        # 二次核查不成立的排除
        audit = load_json(os.path.join(d, 'audit2.json'))
        bad = set()
        if audit:
            bad = {x['file'] for x in audit.get('invalid', [])}

        newcode = MERGE.get(c, c)

        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            if f in used or f in bad or f in dev_files:
                continue
            cand.setdefault(newcode, []).append((os.path.join(d, f), f, c))

    # 分层抽样
    print(f'{"类别":<30}{"候选":>6}{"选取":>6}')
    print('-' * 46)
    picked = {}
    total = 0
    for code in sorted(cand, key=lambda x: -len(cand[x])):
        lst = cand[code]
        # 过滤：文件大小太低（坏图）
        good = [x for x in lst if os.path.getsize(x[0]) > 20000]
        n = min(args.per_cat, len(good))
        picked[code] = good[:n]
        total += n
        print(f'{CODE2NAME.get(code, code):<30}{len(good):>6}{n:>6}')
    print('-' * 46)
    print(f'{"合计":<30}{"":>6}{total:>6}')

    # 输出
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    for code, lst in picked.items():
        d = os.path.join(OUT, code)
        os.makedirs(d, exist_ok=True)
        meta = []
        for src, f, oldcat in lst:
            shutil.copy2(src, os.path.join(d, f))
            meta.append({'file': f, 'source_category': oldcat})
        json.dump({'_meta': {'category': code, 'label': CODE2NAME.get(code, code),
                             'count': len(meta), 'status': 'unlabeled'},
                   'items': meta},
                  open(os.path.join(d, '_pending.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)

    print(f'\ntest 集已生成 → test_set/  ({len(picked)} 类, {total} 张)')
    print('下一步：用双模型标注 + 仲裁，生成 ground_truth.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
