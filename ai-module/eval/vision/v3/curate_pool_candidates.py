# -*- coding: utf-8 -*-
"""
梳理本地已有 pool/<cat> 精选候选，输出每个旧类/合并类的 Top 6 高质量候选（优先未使用且无泄题文字的图）。
"""
import collections
import hashlib
import json
import sys
from pathlib import Path
from PIL import Image

AI_MODULE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(AI_MODULE))
from core.hazard_taxonomy import ALL_SUBCATEGORY_CODES, SUBCATEGORY_TO_MAJOR, SUBCATEGORY_LABELS

VISION_DIR = AI_MODULE / "eval" / "vision"
POOL_DIR = VISION_DIR / "pool"
V3_DIR = Path(__file__).resolve().parent

POOL_TO_V3 = {
    "wall_crack_lean": "dangerous_building",
    "facade_fall": "falling_object",
    "fire_water_abnormal": "fire_equipment_fault",
}


def compute_dhash(img_path: Path, hash_size: int = 8) -> str:
    with Image.open(img_path) as img:
        gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())
    bits = []
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for col in range(hash_size):
            bits.append("1" if pixels[offset + col] > pixels[offset + col + 1] else "0")
    return f"{int(''.join(bits), 2):016x}"


def main() -> int:
    v2b_test = json.loads((VISION_DIR / "v2" / "frozen_test_manifest.v2b.json").read_text(encoding="utf-8"))["items"]
    v2b_test_shas = {it["sha256"] for it in v2b_test if it.get("sha256")}
    v2b_test_files = {Path(it.get("file", "")).name for it in v2b_test}

    candidates_by_sub = collections.defaultdict(list)
    for cat_dir in sorted(POOL_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        ann_path = cat_dir / "annotations.json"
        if not ann_path.is_file():
            continue
        ann = json.loads(ann_path.read_text(encoding="utf-8"))
        suspects = set()
        for aud_name in ("audit.json", "audit2.json"):
            aud_p = cat_dir / aud_name
            if aud_p.is_file():
                aud = json.loads(aud_p.read_text(encoding="utf-8"))
                for s in aud.get("suspect", []):
                    if isinstance(s, dict) and s.get("file"):
                        suspects.add(s["file"])

        for fname, info in (ann.get("items") or {}).items():
            if not isinstance(info, dict) or fname in suspects:
                continue
            if not info.get("has_hazard") or info.get("is_negative_sample"):
                continue
            fpath = cat_dir / "review" / fname
            if not fpath.is_file():
                fpath = cat_dir / fname
                if not fpath.is_file():
                    continue
            ev = str(info.get("key_evidence") or "")
            target = POOL_TO_V3.get(cat_dir.name, cat_dir.name)
            if cat_dir.name == "illegal_wiring" and any(k in ev for k in ("电动车", "电动自行车", "电瓶车", "飞线")):
                target = "ebike_hazard"
            if target not in SUBCATEGORY_TO_MAJOR:
                continue
            try:
                data = fpath.read_bytes()
                sha = hashlib.sha256(data).hexdigest()
                with Image.open(fpath) as im:
                    w, h = im.size
                if min(w, h) < 500:
                    continue
                dhash = compute_dhash(fpath)
            except Exception:
                continue

            text_in_img = bool(info.get("text_in_image"))
            conf_high = info.get("label_confidence") == "high"
            in_v2b = (sha in v2b_test_shas) or (fname in v2b_test_files)
            # 优先级：未在旧测试集(0) > 无字(0) > 高置信度(0) > 分辨率大
            rank = (1 if in_v2b else 0, 1 if text_in_img else 0, 0 if conf_high else 1, -(w * h))
            candidates_by_sub[target].append({
                "path": str(fpath),
                "file": fname,
                "sha256": sha,
                "dhash": dhash,
                "w": w,
                "h": h,
                "from_pool": cat_dir.name,
                "text_in_image": text_in_img,
                "difficulty": info.get("difficulty", "medium"),
                "conf": info.get("label_confidence", "medium"),
                "evidence": ev,
                "in_v2b_test": in_v2b,
                "rank": rank,
            })

    out = {}
    for code in ALL_SUBCATEGORY_CODES:
        arr = sorted(candidates_by_sub[code], key=lambda x: x["rank"])
        # 按 dHash 去重选 Top 8
        picked = []
        seen_hashes = []
        for item in arr:
            dh = int(item["dhash"], 16)
            if any(bin(dh ^ prev).count("1") <= 4 for prev in seen_hashes):
                continue
            seen_hashes.append(dh)
            item_clean = {k: v for k, v in item.items() if k != "rank"}
            picked.append(item_clean)
            if len(picked) >= 8:
                break
        out[code] = picked
        fresh_nt = sum(1 for x in picked if not x["in_v2b_test"] and not x["text_in_image"])
        print(f"  {code:25s} ({SUBCATEGORY_LABELS[code]:12s}): picked={len(picked)}, fresh_no_text={fresh_nt}")

    (V3_DIR / "pool_curated_candidates.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
