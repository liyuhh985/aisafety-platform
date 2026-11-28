#!/usr/bin/env python3
"""Build the offline interview code walkthrough."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.interview_code_walkthrough.build import WalkthroughError, build_walkthrough

MANIFEST_PATH = PROJECT_ROOT / "tools" / "interview_code_walkthrough" / "manifest.json"
OUTPUT_PATH = PROJECT_ROOT / "output" / "interview-code-walkthrough" / "index.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a source-backed, offline interview code walkthrough."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate every manifest entry and source range without writing HTML.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        stats = build_walkthrough(
            PROJECT_ROOT,
            MANIFEST_PATH,
            OUTPUT_PATH,
            check_only=args.check_only,
        )
    except WalkthroughError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1

    print(f"{stats['chapters']} chapters, {stats['snippets']} snippets")
    if stats["checkOnly"]:
        print("validation passed; no output written")
    else:
        print(f"output: {stats['outputPath']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

