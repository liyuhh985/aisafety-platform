# -*- coding: utf-8 -*-
"""生成带编号标签的拼图联系表，用于快速人工视觉复核候选图片。"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw

def make_grid(image_paths: list[Path], out_path: Path, cols: int = 3, thumb_w: int = 420, thumb_h: int = 320):
    rows = (len(image_paths) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * thumb_w, rows * thumb_h), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)
    mapping = []
    for idx, p in enumerate(image_paths):
        r, c = divmod(idx, cols)
        x0, y0 = c * thumb_w, r * thumb_h
        try:
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((thumb_w - 8, thumb_h - 32), Image.Resampling.LANCZOS)
                px = x0 + (thumb_w - im.width) // 2
                py = y0 + 26 + (thumb_h - 30 - im.height) // 2
                canvas.paste(im, (px, py))
        except Exception as exc:
            draw.text((x0 + 10, y0 + 40), f"ERR:{exc}", fill=(200, 0, 0))
        tag = f"[{idx}] {p.name[:24]}"
        draw.rectangle([x0, y0, x0 + thumb_w - 1, y0 + 24], fill=(25, 25, 25))
        draw.text((x0 + 6, y0 + 5), tag, fill=(255, 255, 0))
        mapping.append({"idx": idx, "name": p.name, "path": str(p)})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="JPEG", quality=88)
    out_path.with_suffix(".json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path} ({len(image_paths)} images)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()
    imgs = sorted([p for p in args.dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")])[:args.limit]
    make_grid(imgs, args.out)

if __name__ == "__main__":
    main()
