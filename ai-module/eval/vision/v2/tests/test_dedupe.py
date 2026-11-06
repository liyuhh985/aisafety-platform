from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import dedupe


def test_hamming_distance_counts_changed_bits():
    assert dedupe.hamming64(0b0000, 0b1010) == 2
    assert dedupe.hamming64(0b1111, 0b1111) == 0


def test_find_near_duplicate_pairs_uses_four_bit_threshold():
    items = [
        {"file": "a.jpg", "dhash64": 0b000000},
        {"file": "b.jpg", "dhash64": 0b000011},
        {"file": "c.jpg", "dhash64": 0b11111111},
    ]

    pairs = dedupe.find_near_duplicate_pairs(items, max_distance=4)

    assert pairs == [("a.jpg", "b.jpg", 2)]


def test_dhash64_is_stable_for_identical_image_content(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    image = Image.new("L", (32, 32), color=128)
    image.save(first)
    image.save(second)

    assert dedupe.dhash64(first) == dedupe.dhash64(second)

