# -*- coding: utf-8 -*-
"""补跑指定预测目录中 parsed is None 的失败条目（低并发避免触发 10 并发上限）。"""
import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

AI_MODULE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(AI_MODULE))
from mimo_client import get_client


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--prompt", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    items = json.loads(args.manifest.read_text(encoding="utf-8"))["items"]
    prompt = args.prompt.read_text(encoding="utf-8")
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    client = get_client(None)

    todo = []
    for it in items:
        p = args.output / f"{it['sha256']}.json"
        if not p.is_file():
            todo.append((it, p))
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("parsed") is None:
            todo.append((it, p))

    print(f"Total={len(items)}, retrying={len(todo)} with workers={args.workers}")
    if not todo:
        return 0

    def run_one(it, p):
        for attempt in range(3):
            try:
                raw = client.analyze(it["source_path"], prompt, temperature=0.0)
                parsed = client._extract_json(raw) if raw else None
                if isinstance(parsed, dict):
                    return it["file"], p, {
                        "sha256": it["sha256"],
                        "file": it.get("file", ""),
                        "arm": args.output.name,
                        "prompt_sha256": prompt_sha,
                        "model": getattr(client, "model", ""),
                        "temperature": 0.0,
                        "raw_response": raw,
                        "parsed": parsed,
                        "error": "",
                    }
            except Exception as exc:
                err = f"request_failed:{type(exc).__name__}:{exc}"
            time.sleep(1.5 * (attempt + 1))
        return it["file"], p, {
            "sha256": it["sha256"],
            "file": it.get("file", ""),
            "arm": args.output.name,
            "prompt_sha256": prompt_sha,
            "model": getattr(client, "model", ""),
            "temperature": 0.0,
            "raw_response": None,
            "parsed": None,
            "error": "retry_exhausted",
        }

    ok, bad = 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_one, it, p) for it, p in todo]
        for f in as_completed(futs):
            fname, p, payload = f.result()
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if payload["parsed"] is not None:
                ok += 1
            else:
                bad += 1
                print("FAILED:", fname)
    print(f"Retry complete: ok={ok}, failed={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
