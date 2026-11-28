# -*- coding: utf-8 -*-
"""
把复审结果落地成评测集

annotations.json（复审产物） → images_real/<cat>/（图片 + ground_truth.json）

只拷贝 verdict=keep 的图片，标注直接沿用复审记录。
评测脚本 eval_real.py 不需要改动。

用法：
    python build_dataset.py --cat manhole_damage
    python build_dataset.py --all
    python build_dataset.py --all --clean    # 先清空旧评测集
    python build_dataset.py --status
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POOL = os.path.join(HERE, "pool")
REAL = os.path.join(HERE, "images_real")

# 类别 → 大类的映射（从 taxonomy 读）
def load_taxonomy():
    tax = json.load(open(os.path.join(HERE, "_taxonomy.json"), encoding="utf-8-sig"))
    m = {}
    for maj in tax:
        for sub in maj["subcategories"]:
            m[sub["code"]] = (maj["code"], maj["label"], sub["label"])
    return m


TAX = load_taxonomy()


def build(cat, clean=False):
    d = os.path.join(POOL, cat)
    ap = os.path.join(d, "annotations.json")
    if not os.path.isfile(ap):
        return None

    ann = json.load(open(ap, encoding="utf-8"))
    keep = ann.get("items", {})
    if not keep:
        return "empty"

    # 剔除复检判为可疑的
    up = os.path.join(d, "audit.json")
    suspect = {}
    if os.path.isfile(up):
        try:
            for s in json.load(open(up, encoding="utf-8")).get("suspect", []):
                suspect[s["file"]] = s.get("issue", "")
        except Exception:
            pass

    outdir = os.path.join(REAL, cat)
    if clean and os.path.isdir(outdir):
        shutil.rmtree(outdir)
    os.makedirs(outdir, exist_ok=True)

    maj, maj_label, sub_label = TAX.get(cat, (None, "", ""))

    items = {}
    copied = 0
    dropped = 0
    for fname, rec in keep.items():
        if fname in suspect:
            dropped += 1
            continue
        src = os.path.join(d, "review", fname)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(outdir, fname)
        if not os.path.isfile(dst):
            shutil.copy2(src, dst)
            copied += 1
        items[fname] = {
            "has_hazard": rec.get("has_hazard", True),
            "major_category": rec.get("major_category") or maj,
            "subcategory": rec.get("subcategory") or cat,
            "severity": rec.get("severity"),
            "key_evidence": rec.get("key_evidence", ""),
            "multi_hazard": rec.get("multi_hazard", False),
            "secondary_categories": rec.get("secondary_categories", []),
            "text_in_image": rec.get("text_in_image", False),
            "text_content": rec.get("text_content", ""),
            "difficulty": rec.get("difficulty"),
            "label_confidence": rec.get("label_confidence", "medium"),
            "is_negative_sample": rec.get("is_negative_sample", False),
            "notes": rec.get("notes", ""),
        }

    pos = sum(1 for v in items.values() if v["has_hazard"])
    neg = len(items) - pos
    gt = {
        "_meta": {
            "name": f"{cat} 真实图评测集",
            "category": f"{maj}/{cat}",
            "category_label": f"{maj_label}/{sub_label}",
            "source": "百度图片 → 原站直链下载 → 自动筛选 → 粗筛 → 标注 → 严格复检",
            "rebuild": "2026-10-31",
            "positive": pos,
            "negative": neg,
            "audit_removed": dropped,
        },
        "rejected": ann.get("rejected", []),
        "items": items,
    }
    json.dump(gt, open(os.path.join(outdir, "ground_truth.json"), "w",
                       encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(items), copied, pos, neg, dropped


def status():
    cats = sorted([c for c in os.listdir(POOL)
                   if os.path.isfile(os.path.join(POOL, c, "annotations.json"))])
    print(f"{'类别':<26}{'最终样本':>8}{'正':>5}{'负':>5}")
    print("-" * 46)
    T = 0
    for c in cats:
        r = build(c)
        if not r or r == "empty":
            print(f"{c:<26}      空")
            continue
        n, _, pos, neg, _ = r
        print(f"{c:<26}{n:>8}{pos:>5}{neg:>5}")
        T += n
    print("-" * 46)
    print(f"{'合计':<26}{T:>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        status()
        return 0

    cats = (sorted([c for c in os.listdir(POOL)
                    if os.path.isfile(os.path.join(POOL, c, "annotations.json"))])
            if args.all else [args.cat])

    T = 0
    for c in cats:
        r = build(c, clean=args.clean)
        if not r:
            print(f"{c:<26} 无 annotations.json，跳过")
            continue
        if r == "empty":
            print(f"{c:<26} 复审结果为空（全部淘汰）")
            continue
        n, copied, pos, neg, dropped = r
        print(f"{c:<26} 样本 {n:>3}（正 {pos} / 负 {neg}）  复检剔 {dropped}  新拷贝 {copied}")
        T += n
    print(f"\n合计落地 {T} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
