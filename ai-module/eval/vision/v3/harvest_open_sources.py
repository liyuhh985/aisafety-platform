# -*- coding: utf-8 -*-
"""
面向 33 类诊断集（v3）的开放真实高清图源采集脚本（Wikimedia Commons + Openverse）。
仅使用合规开放 API，严格过滤尺寸、比例与文件格式，并进行 SHA-256 与 dHash 去重。
"""
import argparse
import hashlib
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "candidates_raw"
USER_AGENT = "CitySafetyDiagnosticBenchmark/3.0 (research-eval; no-spam)"
MIN_SIDE = 600
MAX_BYTES = 15 * 1024 * 1024
MIN_BYTES = 18 * 1024

# 针对空白/新增/稀缺正样本与对应负样本的精准中英文检索词
TASKS = {
    "pos_tree_fall_hazard": {
        "wiki": [
            "fallen tree blocking road",
            "storm fallen tree street car",
            "broken tree branch road hazard",
            "uprooted tree street",
        ],
        "openverse": [
            "fallen tree road",
            "tree fell on car street",
            "storm damaged tree sidewalk",
        ],
    },
    "pos_confined_space": {
        "wiki": [
            "manhole worker",
            "sewer maintenance worker",
            "confined space manhole",
            "utility manhole underground",
        ],
        "openverse": [
            "sewer worker manhole",
            "manhole maintenance street",
            "underground pipe worker",
        ],
    },
    "pos_hazmat_storage": {
        "wiki": [
            "chemical drums hazard",
            "rusted chemical barrels",
            "propane cylinders storage",
            "gas cylinders stacked outdoor",
        ],
        "openverse": [
            "chemical drums barrels",
            "rusty oil drums hazardous",
            "gas cylinder storage",
        ],
    },
    "pos_ebike_hazard": {
        "wiki": [
            "electric bicycle charging",
            "e-bike battery fire",
            "electric scooter hallway",
            "ebike charging indoors",
        ],
        "openverse": [
            "electric scooter charging",
            "electric bike charging indoor",
            "ebike battery charging",
        ],
    },
    "pos_other": {
        "wiki": [
            "broken playground equipment",
            "rusty protruding rebar hazard",
            "damaged park bench broken",
        ],
        "openverse": [
            "broken playground hazard",
            "damaged fitness equipment park",
            "protruding metal rebar ground",
        ],
    },
    "pos_gas_leak": {
        "wiki": [
            "gas leak detector",
            "soap bubbles gas pipe leak",
            "gas pipe corrosion",
        ],
        "openverse": [
            "gas leak detector pipe",
            "natural gas pipeline valve",
        ],
    },
    "pos_elevator_inspection": {
        "wiki": [
            "elevator inspection certificate",
            "elevator safety notice",
        ],
        "openverse": [
            "elevator certificate",
            "elevator safety inspection",
        ],
    },
    "pos_elevator_stopped": {
        "wiki": [
            "out of order elevator",
            "broken escalator barrier",
            "elevator repair sign",
        ],
        "openverse": [
            "elevator out of order",
            "escalator under repair",
        ],
    },
    "neg_ebike_normal": {
        "wiki": [
            "bicycle parking shed",
            "electric bike charging station outdoor",
        ],
        "openverse": [
            "bicycle parking rack outdoor",
            "ev charging station outdoor orderly",
        ],
    },
    "neg_tree_normal": {
        "wiki": [
            "tree lined street sidewalk",
            "pruned street trees city",
        ],
        "openverse": [
            "healthy street trees sidewalk",
            "city sidewalk trees sunny",
        ],
    },
    "neg_confined_normal": {
        "wiki": [
            "construction safety barrier manhole",
            "road work cones barrier",
        ],
        "openverse": [
            "roadwork safety cones barrier",
        ],
    },
    "neg_hazmat_normal": {
        "wiki": [
            "flammable safety cabinet",
            "hazardous material warehouse organized",
        ],
        "openverse": [
            "yellow safety cabinet laboratory",
        ],
    },
}


def compute_dhash(img: Image.Image, hash_size: int = 8) -> str:
    gray = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = list(gray.getdata())
    bits = []
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for col in range(hash_size):
            bits.append("1" if pixels[offset + col] > pixels[offset + col + 1] else "0")
    return f"{int(''.join(bits), 2):016x}"


def search_wikimedia(query: str, limit: int = 12) -> list[dict]:
    out = []
    try:
        r = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"{query} filetype:bitmap",
                "gsrnamespace": 6,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": 1280,
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        pages = (r.json().get("query") or {}).get("pages") or {}
        for p in pages.values():
            ii = (p.get("imageinfo") or [{}])[0]
            mime = ii.get("mime", "")
            w, h = int(ii.get("width") or 0), int(ii.get("height") or 0)
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                continue
            if min(w, h) < MIN_SIDE:
                continue
            ratio = h / w if w else 0
            if not (0.4 <= ratio <= 2.5):
                continue
            dl_url = ii.get("thumburl") or ii.get("url")
            if not dl_url:
                continue
            out.append({
                "url": dl_url,
                "orig_url": ii.get("url", dl_url),
                "title": p.get("title", ""),
                "source": "wikimedia",
                "query": query,
                "w": w,
                "h": h,
            })
    except Exception as exc:
        print(f"  [wiki err] {query}: {exc}")
    return out


def search_openverse(query: str, limit: int = 15) -> list[dict]:
    out = []
    try:
        r = requests.get(
            "https://api.openverse.org/v1/images/",
            params={"q": query, "page_size": limit},
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        for item in (r.json().get("results") or []):
            url = item.get("url")
            if not url:
                continue
            w = int(item.get("width") or 0)
            h = int(item.get("height") or 0)
            if w and h:
                if min(w, h) < MIN_SIDE:
                    continue
                ratio = h / w
                if not (0.4 <= ratio <= 2.5):
                    continue
            out.append({
                "url": url,
                "orig_url": item.get("foreign_landing_url") or url,
                "title": item.get("title") or "",
                "source": f"openverse:{item.get('source', '')}",
                "query": query,
                "w": w,
                "h": h,
            })
    except Exception as exc:
        print(f"  [openverse err] {query}: {exc}")
    return out


def download_candidate(cand: dict, out_dir: Path) -> dict | None:
    try:
        r = requests.get(
            cand["url"],
            headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        data = r.content
        if not (MIN_BYTES <= len(data) <= MAX_BYTES):
            return None
        img = Image.open(io.BytesIO(data))
        img.load()
        w, h = img.size
        if min(w, h) < MIN_SIDE:
            return None
        ratio = h / w
        if not (0.4 <= ratio <= 2.5):
            return None
        sha = hashlib.sha256(data).hexdigest()
        dhash = compute_dhash(img)
        ext = ".png" if img.format == "PNG" else ".jpg"
        out_path = out_dir / f"{sha[:16]}{ext}"
        if img.format not in ("JPEG", "PNG"):
            rgb = img.convert("RGB")
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=92)
            data = buf.getvalue()
            sha = hashlib.sha256(data).hexdigest()
            out_path = out_dir / f"{sha[:16]}.jpg"
        out_path.write_bytes(data)
        return {
            **cand,
            "file": out_path.name,
            "path": str(out_path),
            "sha256": sha,
            "dhash": dhash,
            "w": w,
            "h": h,
            "bytes": len(data),
        }
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-bucket", type=int, default=16)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}
    for bucket, conf in TASKS.items():
        bdir = RAW_DIR / bucket
        bdir.mkdir(parents=True, exist_ok=True)
        cands = []
        seen_urls = set()
        for q in conf.get("wiki", []):
            for it in search_wikimedia(q):
                if it["url"] not in seen_urls:
                    seen_urls.add(it["url"])
                    cands.append(it)
            time.sleep(0.15)
        for q in conf.get("openverse", []):
            for it in search_openverse(q):
                if it["url"] not in seen_urls:
                    seen_urls.add(it["url"])
                    cands.append(it)
            time.sleep(0.2)

        saved = []
        seen_sha = set()
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = [ex.submit(download_candidate, c, bdir) for c in cands[: args.per_bucket * 3]]
            for fut in as_completed(futs):
                res = fut.result()
                if res and res["sha256"] not in seen_sha:
                    seen_sha.add(res["sha256"])
                    saved.append(res)
                    if len(saved) >= args.per_bucket:
                        break
        (bdir / "manifest.json").write_text(
            json.dumps({"bucket": bucket, "count": len(saved), "items": saved}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary[bucket] = len(saved)
        print(f"[{bucket}] candidates={len(cands)}, downloaded={len(saved)}")

    (RAW_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
