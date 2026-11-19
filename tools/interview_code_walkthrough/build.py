"""Validate and extract source-backed snippets for the interview viewer."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


class WalkthroughError(Exception):
    """Raised when the manifest or a referenced source range is invalid."""


REQUIRED_SNIPPET_FIELDS = {
    "file",
    "method",
    "start",
    "end",
    "startAnchor",
    "title",
    "explain",
    "interviewQuestions",
    "pitfalls",
}


def _require_text(value: Any, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WalkthroughError(f"{context}: {field} must be a non-empty string")
    return value.strip()


def _require_string_list(value: Any, field: str, context: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise WalkthroughError(f"{context}: {field} must be a non-empty list")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise WalkthroughError(
                f"{context}: {field}[{index}] must be a non-empty string"
            )
        result.append(item.strip())
    return result


def load_manifest(path: Path) -> dict:
    """Load JSON and convert all read failures into one actionable error type."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise WalkthroughError(f"manifest not found: {path}") from exc
    except OSError as exc:
        raise WalkthroughError(f"cannot read manifest {path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WalkthroughError(
            f"invalid manifest JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise WalkthroughError("manifest root must be an object")
    return data


def validate_manifest(data: dict) -> None:
    """Validate the stable manifest shape without touching source files."""
    _require_text(data.get("title"), "title", "manifest")
    _require_text(data.get("subtitle"), "subtitle", "manifest")

    chapters = data.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != 9:
        raise WalkthroughError("manifest must contain exactly nine chapters")

    chapter_ids: set[str] = set()
    for chapter_index, chapter in enumerate(chapters):
        context = f"chapter[{chapter_index}]"
        if not isinstance(chapter, dict):
            raise WalkthroughError(f"{context} must be an object")
        chapter_id = _require_text(chapter.get("id"), "id", context)
        if chapter_id in chapter_ids:
            raise WalkthroughError(f"{context}: duplicate id {chapter_id!r}")
        chapter_ids.add(chapter_id)
        _require_text(chapter.get("title"), "title", context)
        _require_text(chapter.get("summary"), "summary", context)

        snippets = chapter.get("snippets")
        if not isinstance(snippets, list) or not snippets:
            raise WalkthroughError(f"{context}: snippets must be a non-empty list")

        for snippet_index, snippet in enumerate(snippets):
            snippet_context = f"{context}.snippets[{snippet_index}]"
            if not isinstance(snippet, dict):
                raise WalkthroughError(f"{snippet_context} must be an object")
            missing = REQUIRED_SNIPPET_FIELDS - snippet.keys()
            extra = snippet.keys() - REQUIRED_SNIPPET_FIELDS
            if missing:
                raise WalkthroughError(
                    f"{snippet_context}: missing fields {sorted(missing)}"
                )
            if extra:
                raise WalkthroughError(
                    f"{snippet_context}: unknown fields {sorted(extra)}"
                )

            _require_text(snippet.get("file"), "file", snippet_context)
            _require_text(snippet.get("method"), "method", snippet_context)
            _require_text(snippet.get("startAnchor"), "startAnchor", snippet_context)
            _require_text(snippet.get("title"), "title", snippet_context)
            _require_text(snippet.get("explain"), "explain", snippet_context)
            _require_string_list(
                snippet.get("interviewQuestions"), "interviewQuestions", snippet_context
            )
            _require_string_list(snippet.get("pitfalls"), "pitfalls", snippet_context)

            start = snippet.get("start")
            end = snippet.get("end")
            if isinstance(start, bool) or not isinstance(start, int) or start < 1:
                raise WalkthroughError(
                    f"{snippet_context}: start must be a positive integer"
                )
            if isinstance(end, bool) or not isinstance(end, int) or end < start:
                raise WalkthroughError(
                    f"{snippet_context}: end must be an integer >= start"
                )


def extract_snippet(project_root: Path, snippet: dict) -> dict:
    """Resolve one snippet against the real source and verify its start anchor."""
    root = project_root.resolve()
    requested_path = Path(snippet["file"])
    if requested_path.is_absolute():
        raise WalkthroughError(f"snippet file must be relative: {requested_path}")

    source_path = (root / requested_path).resolve()
    try:
        source_path.relative_to(root)
    except ValueError as exc:
        raise WalkthroughError(
            f"snippet file is outside project root: {snippet['file']}"
        ) from exc

    if not source_path.is_file():
        raise WalkthroughError(f"source file not found: {snippet['file']}")

    try:
        text = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise WalkthroughError(f"source file is not UTF-8: {snippet['file']}") from exc
    except OSError as exc:
        raise WalkthroughError(f"cannot read source file {snippet['file']}: {exc}") from exc

    lines = text.splitlines()
    start = snippet["start"]
    end = snippet["end"]
    if end > len(lines):
        raise WalkthroughError(
            f"{snippet['file']}: line range {start}-{end} exceeds file length {len(lines)}"
        )

    actual_anchor = lines[start - 1].strip()
    expected_anchor = snippet["startAnchor"].strip()
    if actual_anchor != expected_anchor:
        raise WalkthroughError(
            f"{snippet['file']}: anchor mismatch at line {start}; "
            f"expected {expected_anchor!r}, found {actual_anchor!r}"
        )

    code = "\n".join(lines[start - 1 : end])
    return {
        **snippet,
        "sourcePath": str(source_path),
        "relativePath": snippet["file"],
        "lineStart": start,
        "lineEnd": end,
        "code": code,
        "codeHash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
    }


def _resolve_chapters(project_root: Path, data: dict) -> list[dict]:
    resolved_chapters = []
    for chapter in data["chapters"]:
        resolved_chapters.append(
            {
                **chapter,
                "snippets": [
                    extract_snippet(project_root, snippet)
                    for snippet in chapter["snippets"]
                ],
            }
        )
    return resolved_chapters


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def build_walkthrough(
    project_root: Path,
    manifest_path: Path,
    output_path: Path,
    *,
    check_only: bool = False,
) -> dict:
    """Validate, resolve, render, and atomically publish the walkthrough."""
    data = load_manifest(manifest_path)
    validate_manifest(data)
    chapters = _resolve_chapters(project_root, data)
    snippet_count = sum(len(chapter["snippets"]) for chapter in chapters)

    if not check_only:
        from tools.interview_code_walkthrough.render import render_html

        generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        rendered = render_html({**data, "chapters": chapters}, generated_at)
        _atomic_write(output_path, rendered)

    return {
        "chapters": len(chapters),
        "snippets": snippet_count,
        "outputPath": str(output_path),
        "checkOnly": check_only,
    }
