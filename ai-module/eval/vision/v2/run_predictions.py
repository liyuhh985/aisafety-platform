from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AI_MODULE_DIR = Path(__file__).resolve().parents[3]
if str(AI_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODULE_DIR))


def _prompt_sha(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _annotate_item(
    item: dict,
    client,
    prompt: str,
    prompt_sha: str,
    temperature: float,
    arm: str,
) -> dict:
    raw = None
    parsed = None
    error = ""
    try:
        raw = client.analyze(item["source_path"], prompt, temperature=temperature)
        parsed = client._extract_json(raw) if raw else None
        if not isinstance(parsed, dict):
            parsed = None
            error = "parse_failed"
    except Exception as exc:
        error = f"request_failed:{type(exc).__name__}:{exc}"
    return {
        "sha256": item["sha256"],
        "file": item.get("file", ""),
        "arm": arm,
        "prompt_sha256": prompt_sha,
        "model": getattr(client, "model", ""),
        "temperature": temperature,
        "raw_response": raw,
        "parsed": parsed,
        "error": error,
    }


def run_arm(
    frozen_path: Path,
    prompt_path: Path,
    output_dir: Path,
    client,
    temperature: float = 0.0,
    split: str | None = None,
    workers: int = 1,
) -> dict:
    if workers <= 0:
        raise ValueError("workers must be positive")
    manifest = json.loads(Path(frozen_path).read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    if split is not None:
        items = [item for item in items if item.get("split") == split]

    prompt = Path(prompt_path).read_text(encoding="utf-8")
    prompt_sha = _prompt_sha(prompt)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _annotate_item,
                item,
                client,
                prompt,
                prompt_sha,
                temperature,
                output_dir.name,
            )
            for item in items
        ]
        for future in as_completed(futures):
            payload = future.result()
            (output_dir / f"{payload['sha256']}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            written += 1
            if payload["parsed"] is None:
                failed += 1
    return {"total": len(items), "written": written, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one prompt arm against a v2.1 manifest")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--split", default=None)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--provider", default=None)
    args = parser.parse_args()

    from mimo_client import get_client

    client = get_client(args.provider)
    result = run_arm(
        args.manifest,
        args.prompt,
        args.output,
        client,
        temperature=args.temperature,
        split=args.split,
        workers=args.workers,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
