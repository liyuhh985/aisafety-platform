from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

V2_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_DIR))

import prepare_prompts as pp
import run_predictions as rp


class FakeClient:
    model = "fake-vision"

    def analyze(self, image_path, prompt, temperature):
        return '{"has_hazard": false, "confidence": "高", "reason_if_no_hazard": "正常"}'

    @staticmethod
    def _extract_json(text):
        return json.loads(text)


def test_run_arm_writes_one_prediction_per_sha(tmp_path):
    frozen = tmp_path / "frozen.json"
    frozen.write_text(
        json.dumps({
            "items": [
                {"sha256": "abc", "source_path": str(tmp_path / "x.jpg"), "split": "test"},
            ]
        }),
        encoding="utf-8",
    )
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("prompt", encoding="utf-8")

    result = rp.run_arm(frozen, prompt, tmp_path / "out", FakeClient())

    assert result == {"total": 1, "written": 1, "failed": 0}
    payload = json.loads((tmp_path / "out" / "abc.json").read_text(encoding="utf-8"))
    assert payload["parsed"]["has_hazard"] is False
    assert payload["model"] == "fake-vision"
    assert payload["temperature"] == 0.0


def test_run_arm_filters_requested_split(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "items": [
                {"sha256": "dev-item", "source_path": "dev.jpg", "split": "dev"},
                {"sha256": "test-item", "source_path": "test.jpg", "split": "test"},
            ]
        }),
        encoding="utf-8",
    )
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("prompt", encoding="utf-8")

    result = rp.run_arm(manifest, prompt, tmp_path / "out", FakeClient(), split="test")

    assert result == {"total": 1, "written": 1, "failed": 0}
    assert (tmp_path / "out" / "test-item.json").is_file()
    assert not (tmp_path / "out" / "dev-item.json").exists()


def test_prepare_prompts_hashes_and_appends_rules(tmp_path):
    manifest = pp.prepare_prompts(tmp_path)
    baseline = (tmp_path / "baseline.txt").read_text(encoding="utf-8")
    final = (tmp_path / "final.txt").read_text(encoding="utf-8")

    assert manifest["baseline"]["sha256"] == hashlib.sha256(baseline.encode("utf-8")).hexdigest()
    assert manifest["final"]["sha256"] == hashlib.sha256(final.encode("utf-8")).hexdigest()
    assert "无法判断时，输出 has_hazard=false" in final
    assert final.startswith(baseline)


def test_run_arm_accepts_parallel_workers(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"items": [
        {"sha256": f"item-{i}", "source_path": f"image-{i}.jpg", "split": "test"}
        for i in range(4)
    ]}), encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("prompt", encoding="utf-8")

    result = rp.run_arm(manifest, prompt, tmp_path / "out", FakeClient(), workers=2)

    assert result == {"total": 4, "written": 4, "failed": 0}
    assert len(list((tmp_path / "out").glob("*.json"))) == 4
