from pathlib import Path

import pytest

from tools.interview_code_walkthrough.build import (
    WalkthroughError,
    extract_snippet,
    load_manifest,
    validate_manifest,
)


def _snippet(**overrides):
    base = {
        "file": "Demo.java",
        "method": "Demo.run",
        "start": 1,
        "end": 1,
        "startAnchor": "first",
        "title": "run",
        "explain": "Explain this method.",
        "interviewQuestions": ["Why is this called?"],
        "interviewAnswers": ["It is called to route the request into the next layer."],
        "pitfalls": ["Do not claim it is asynchronous."],
        "lineNotes": [{"lineOffset": 0, "text": "This annotation declares an HTTP endpoint.", "kind": "syntax"}],
    }
    base.update(overrides)
    return base


def test_extract_snippet_uses_exact_source_lines(tmp_path: Path):
    source = tmp_path / "src" / "Demo.java"
    source.parent.mkdir()
    source.write_text("class Demo {\n  void run() {\n  }\n}\n", encoding="utf-8")
    resolved = extract_snippet(
        tmp_path,
        _snippet(
            file="src/Demo.java",
            method="Demo.run",
            start=2,
            end=3,
            startAnchor="  void run() {",
        ),
    )

    assert resolved["code"] == "  void run() {\n  }"
    assert resolved["lineStart"] == 2
    assert resolved["lineEnd"] == 3
    assert resolved["sourcePath"] == str(source.resolve())


def test_extract_snippet_rejects_anchor_mismatch(tmp_path: Path):
    source = tmp_path / "Demo.java"
    source.write_text("first\nsecond\n", encoding="utf-8")

    with pytest.raises(WalkthroughError, match="anchor mismatch"):
        extract_snippet(tmp_path, _snippet(startAnchor="wrong"))


def test_extract_snippet_rejects_path_escape(tmp_path: Path):
    outside = tmp_path.parent / "outside.java"
    outside.write_text("first\n", encoding="utf-8")

    with pytest.raises(WalkthroughError, match="outside project root"):
        extract_snippet(
            tmp_path,
            _snippet(file="../outside.java", end=1),
        )


def test_validate_manifest_requires_nine_chapters():
    with pytest.raises(WalkthroughError, match="nine chapters"):
        validate_manifest({"title": "x", "subtitle": "y", "chapters": []})


def test_load_manifest_reports_invalid_json(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(WalkthroughError, match="invalid manifest JSON"):
        load_manifest(path)



def test_checked_in_manifest_has_all_chapters():
    root = Path(__file__).parents[2]
    data = load_manifest(root / "tools/interview_code_walkthrough/manifest.json")
    titles = [chapter["title"] for chapter in data["chapters"]]

    assert len(titles) == 9
    assert "Java SSE 入口" in titles
    assert "前端确认、SSE 与分级轮询" in titles


def test_checked_in_manifest_resolves_every_snippet():
    root = Path(__file__).parents[2]
    data = load_manifest(root / "tools/interview_code_walkthrough/manifest.json")
    validate_manifest(data)

    snippet_count = 0
    for chapter in data["chapters"]:
        for snippet in chapter["snippets"]:
            extract_snippet(root, snippet)
            snippet_count += 1

    assert snippet_count >= 20



def test_extract_snippet_rejects_line_note_outside_range(tmp_path: Path):
    source = tmp_path / "Demo.java"
    source.write_text("first\n", encoding="utf-8")

    with pytest.raises(WalkthroughError, match="line note offset"):
        extract_snippet(tmp_path, _snippet(lineNotes=[{"lineOffset": 1, "text": "x"}]))



def test_validate_manifest_rejects_unknown_line_note_kind():
    chapter = {
        "id": "c",
        "title": "t",
        "summary": "s",
        "snippets": [
            _snippet(
                lineNotes=[{"lineOffset": 0, "text": "x", "kind": "unknown"}]
            )
        ],
    }
    with pytest.raises(WalkthroughError, match="kind"):
        validate_manifest({"title": "x", "subtitle": "y", "chapters": [chapter] * 9})


def test_extract_snippet_allows_multiple_notes_on_same_line(tmp_path: Path):
    source = tmp_path / "Demo.java"
    source.write_text("first\n", encoding="utf-8")

    resolved = extract_snippet(
        tmp_path,
        _snippet(
            lineNotes=[
                {"lineOffset": 0, "text": "syntax", "kind": "syntax"},
                {"lineOffset": 0, "text": "call", "kind": "call"},
            ]
        ),
    )

    assert len(resolved["lineNotes"]) == 2


def test_checked_in_manifest_has_expanded_note_coverage():
    root = Path(__file__).parents[2]
    data = load_manifest(root / "tools/interview_code_walkthrough/manifest.json")
    validate_manifest(data)
    notes = [
        note
        for chapter in data["chapters"]
        for snippet in chapter["snippets"]
        for note in snippet["lineNotes"]
    ]
    kinds = {note.get("kind", "syntax") for note in notes}

    assert len(notes) >= 160
    assert kinds == {"syntax", "method", "call", "data", "edge"}
