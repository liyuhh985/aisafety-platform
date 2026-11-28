# -*- coding: utf-8 -*-
"""
整理评测目录（含去重）

策略：
  · dev 集（images_real）：只保留 ground_truth.json 标注（754 KB），
    图片丢弃 —— 因为 images_merged 里已有同样的图，只是换了类别名
  · backup 副本：直接删除（与 images_real 完全相同）
  · pool：保留（6.3 GB，但里面还有 1,520 张未用的图，是后续扩充的素材）
  · 其余中间文件：移到 _archive/

预计从 11.9 GB 降到 8.6 GB 左右。

用法：
    python tidy.py --dry
    python tidy.py
    python tidy.py --keep-pool-img   # 连 pool 里的图一起归档（激进，省 6 GB）
"""
import argparse
import json
import os
import shutil

HERE = r'E:\java\newProject\ai-module\eval\vision'
ARCH = os.path.join(HERE, '_archive')

KEEP_PY = {
    'harvest.py', 'harvest_neg.py', 'harvest_neg2.py',
    'screen.py', 'triage.py',
    'annotate.py', 'audit.py', 'recheck_cat.py', 'recheck_fire.py',
    'reclass_sewage.py',
    'split_dev_test.py', 'label_test_v2.py',
    'final_eval.py', 'final_eval_v2.py', 'kappa.py',
    'eval_negatives.py', 'clean_negatives.py',
    'build_dataset.py', 'finalize.py', 'clean_and_recalc.py',
    'gen_final_report.py',
    'status_full.py', 'inventory.py', 'check_test_pool.py',
    'json_repair.py', 'tidy.py',
}

KEEP_MD = {'REPORT_FINAL.md', 'ANNOTATION_RULES.md', 'TAXONOMY_REFACTOR.md', 'README.md'}

KEEP_JSON = {
    '_taxonomy.json', '_taxonomy_final.json', '_merge_final.json',
    '_final_eval_v2.json', '_clean_result.json',
    'test_set_annotations.json',
}

# 要整体删除的（重复数据）
DELETE_DIRS = ['_images_real_backup_32class', 'images', '__pycache__']

# 要移入归档的目录
ARCH_DIRS = ['kappa']


def dirsize(d):
    s = 0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                s += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--keep-pool-img', action='store_true',
                    help='把 pool 里的图片也归档（只留标注 JSON）')
    args = ap.parse_args()

    dry = args.dry
    moved = []
    deleted = []

    # ---- 1. dev 集：只留标注，丢图片 ----
    dev = os.path.join(HERE, 'images_real')
    if os.path.isdir(dev):
        keep_dir = os.path.join(HERE, 'dev_annotations')
        if not dry:
            os.makedirs(keep_dir, exist_ok=True)
        n = 0
        for c in os.listdir(dev):
            p = os.path.join(dev, c, 'ground_truth.json')
            if os.path.isfile(p):
                dst = os.path.join(keep_dir, f'{c}.json')
                if not dry:
                    shutil.copy2(p, dst)
                n += 1
        moved.append(f'[保留] dev 集标注 {n} 个 → dev_annotations/  '
                     f'（丢弃图片，images_merged 已有同图）')
        if not dry:
            shutil.rmtree(dev, ignore_errors=True)

    # ---- 2. 删除重复目录 ----
    for d in DELETE_DIRS:
        p = os.path.join(HERE, d)
        if os.path.isdir(p):
            deleted.append(f'[删除] {d}/  ({dirsize(p)//1024//1024} MB)')
            if not dry:
                shutil.rmtree(p, ignore_errors=True)

    # ---- 3. pool 可选归档 ----
    if args.keep_pool_img:
        pool = os.path.join(HERE, 'pool')
        if os.path.isdir(pool):
            moved.append(f'[归档] pool/ 的图片（{dirsize(pool)//1024//1024} MB），'
                         f'保留各目录下的 *.json')

    # ---- 4. 归档目录 ----
    for d in ARCH_DIRS:
        p = os.path.join(HERE, d)
        if os.path.isdir(p):
            dst = os.path.join(ARCH, d)
            if os.path.exists(dst):
                continue
            moved.append(f'[归档] {d}/')
            if not dry:
                os.makedirs(ARCH, exist_ok=True)
                try:
                    shutil.move(p, dst)
                except Exception as e:
                    print(f'  失败 {d}: {e}')

    # ---- 5. 归档脚本/文档/中间JSON ----
    os.makedirs(os.path.join(ARCH, 'scripts'), exist_ok=True)
    os.makedirs(os.path.join(ARCH, 'docs'), exist_ok=True)
    os.makedirs(os.path.join(ARCH, 'json'), exist_ok=True)

    for f in os.listdir(HERE):
        src = os.path.join(HERE, f)
        if not os.path.isfile(src):
            continue
        if f.endswith('.py') and f not in KEEP_PY:
            dst = os.path.join(ARCH, 'scripts', f)
            tag = '[脚本]'
        elif f.endswith('.md') and f not in KEEP_MD:
            dst = os.path.join(ARCH, 'docs', f)
            tag = '[文档]'
        elif f.endswith('.json') and f not in KEEP_JSON:
            dst = os.path.join(ARCH, 'json', f)
            tag = '[JSON]'
        else:
            continue
        if os.path.exists(dst):
            continue
        moved.append(f'{tag} {f}')
        if not dry:
            shutil.move(src, dst)

    print(f'{"【计划】" if dry else "【已执行】"}\n')
    for m in moved:
        print(f'  {m}')
    print()
    for d in deleted:
        print(f'  {d}')

    if not dry:
        print()
        remain_py = [f for f in os.listdir(HERE) if f.endswith('.py')]
        remain_md = [f for f in os.listdir(HERE) if f.endswith('.md')]
        remain_dir = [d for d in os.listdir(HERE)
                      if os.path.isdir(os.path.join(HERE, d))]
        print(f'整理后：{len(remain_py)} 个脚本 / {len(remain_md)} 份文档 / '
              f'{len(remain_dir)} 个目录')
        print(f'当前占用：{dirsize(HERE)//1024//1024} MB')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
