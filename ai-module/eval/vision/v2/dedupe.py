from __future__ import annotations

import hashlib
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageOps


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dhash64(path: Path) -> int:
    with Image.open(path) as source:
        image = ImageOps.grayscale(source).resize((9, 8), Image.Resampling.LANCZOS)
        pixels = image.tobytes()

    value = 0
    for row in range(8):
        offset = row * 9
        for col in range(8):
            value = (value << 1) | int(pixels[offset + col] > pixels[offset + col + 1])
    return value


def hamming64(left: int, right: int) -> int:
    return int(left ^ right).bit_count()


def find_near_duplicate_pairs(
    items: list[dict],
    max_distance: int = 4,
) -> list[tuple[str, str, int]]:
    pairs: list[tuple[str, str, int]] = []
    for left, right in combinations(items, 2):
        distance = hamming64(int(left["dhash64"]), int(right["dhash64"]))
        if distance <= max_distance:
            pairs.append((left["file"], right["file"], distance))
    return pairs
