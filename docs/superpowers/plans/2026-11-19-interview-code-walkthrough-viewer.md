# Interview Code Walkthrough Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, source-linked HTML study viewer for the asynchronous hazard-creation flow without modifying business source files.

**Architecture:** A Python stdlib generator validates a JSON manifest, extracts exact source-line ranges from the repository, verifies start anchors, and renders a single self-contained HTML file with inline CSS and JavaScript. The first version contains nine chapters covering Java SSE entry through frontend polling.

**Tech Stack:** Python 3.13 standard library, pytest 9, HTML, inline CSS, inline JavaScript

## Global Constraints

- Generated artifact: `output/interview-code-walkthrough/index.html`
- Generator entrypoint: `tools/build_interview_code_walkthrough.py`
- Manifest: `tools/interview_code_walkthrough/manifest.json`
- Extract code from source; never manually reproduce it in the renderer.
- `startAnchor` must equal the trimmed source line at `start`.
- Do not modify Java, Python, or Vue business source files.
- Do not use external CDN, JavaScript packages, or a web server.
- Build failures must not overwrite the previous successful output.
- First version covers exactly the nine chapters approved in `docs/superpowers/specs/2026-11-19-interview-code-walkthrough-viewer-design.md`.

---

### Task 1: Source Extraction and Manifest Validation

**Files:**
- Create: `tools/interview_code_walkthrough/__init__.py`
- Create: `tools/interview_code_walkthrough/build.py`
- Test: `tools/tests/test_interview_code_walkthrough_build.py`

**Interfaces:**
- Produces:
  - `class WalkthroughError(Exception)`
  - `load_manifest(path: Path) -> dict`
  - `validate_manifest(data: dict) -> None`
  - `extract_snippet(project_root: Path, snippet: dict) -> dict`
  - `build_walkthrough(project_root: Path, manifest_path: Path, output_path: Path) -> dict`

- [ ] **Step 1: Write failing extraction and validation tests**

```python
from pathlib import Path
import pytest
from tools.interview_code_walkthrough.build import (
    WalkthroughError, extract_snippet, validate_manifest,
)


def test_extract_snippet_uses_exact_source_lines(tmp_path):
    source = tmp_path / "src" / "Demo.java"
    source.parent.mkdir()
    source.write_text("class Demo {\n  void run() {\n  }\n}\n", encoding="utf-8")
    snippet = {
        "file": "src/Demo.java", "method": "Demo.run", "start": 2,
        "end": 3, "startAnchor": "  void run() {", "title": "run",
        "explain": "explain", "interviewQuestions": ["q"], "pitfalls": ["p"],
    }
    resolved = extract_snippet(tmp_path, snippet)
    assert resolved["code"] == "  void run() {\n  }"
    assert resolved["lineStart"] == 2
    assert resolved["lineEnd"] == 3


def test_extract_snippet_rejects_anchor_mismatch(tmp_path):
    source = tmp_path / "Demo.java"
    source.write_text("first\nsecond\n", encoding="utf-8")
    snippet = {
        "file": "Demo.java", "method": "Demo", "start": 1, "end": 1,
        "startAnchor": "wrong", "title": "t", "explain": "e",
        "interviewQuestions": ["q"], "pitfalls": ["p"],
    }
    with pytest.raises(WalkthroughError, match="anchor mismatch"):
        extract_snippet(tmp_path, snippet)


def test_validate_manifest_requires_nine_chapters():
    with pytest.raises(WalkthroughError, match="nine chapters"):
        validate_manifest({"title": "x", "chapters": []})
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `python -m pytest tools/tests/test_interview_code_walkthrough_build.py -v`  
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement validation, path safety, extraction, and atomic build**

Implement `build.py` with these exact behaviors:

```python
ALLOWED_SNIPPET_FIELDS = {
    "file", "method", "start", "end", "startAnchor", "title",
    "explain", "interviewQuestions", "pitfalls",
}


def validate_manifest(data):
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != 9:
        raise WalkthroughError("manifest must contain exactly nine chapters")
    for chapter in chapters:
        require non-empty `id`, `title`, `summary`
        require non-empty `snippets`
        for snippet in chapter["snippets"]:
            require all fields in ALLOWED_SNIPPET_FIELDS
            require `start` and `end` are one-based positive integers
            require `end >= start`
            require `interviewQuestions` and `pitfalls` are lists of strings


def extract_snippet(project_root, snippet):
    source_path = (project_root / snippet["file"]).resolve()
    require source_path is inside project_root
    read UTF-8 lines
    require line range is inside the file
    require trimmed actual start line equals trimmed `startAnchor`
    return snippet plus sourcePath, lineStart, lineEnd, code, codeHash
```

`build_walkthrough()` must resolve all snippets, call the renderer, write a temporary file in the output directory, and use `Path.replace()` only after rendering succeeds.

- [ ] **Step 4: Run tests to confirm pass**

Run: `python -m pytest tools/tests/test_interview_code_walkthrough_build.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/interview_code_walkthrough tools/tests/test_interview_code_walkthrough_build.py
git commit -m "feat: add code walkthrough source extractor"
```

---

### Task 2: Self-Contained HTML Renderer

**Files:**
- Create: `tools/interview_code_walkthrough/render.py`
- Test: `tools/tests/test_interview_code_walkthrough_render.py`

**Interfaces:**
- Consumes: resolved manifest from Task 1 with chapter snippets containing `code`, `lineStart`, `lineEnd`, `sourcePath`, and `codeHash`.
- Produces: `render_html(data: dict, generated_at: str) -> str`

- [ ] **Step 1: Write failing renderer tests**

```python
from tools.interview_code_walkthrough.render import render_html


def sample_data():
    return {
        "title": "Code Walkthrough",
        "subtitle": "Offline study page",
        "chapters": [{
            "id": "chapter-1", "title": "Java entry", "summary": "entry",
            "snippets": [{
                "title": "Controller", "method": "AiController.assistantStream",
                "file": "AiController.java", "lineStart": 78, "lineEnd": 79,
                "code": "@PostMapping\npublic SseEmitter assistantStream",
                "explain": "explanation", "interviewQuestions": ["why SSE"],
                "pitfalls": ["do not call accepted created"], "codeHash": "abc",
            }],
        }],
    }


def test_renderer_contains_navigation_code_and_modes():
    html = render_html(sample_data(), "2026-11-19T12:00:00+08:00")
    assert "Java entry" in html
    assert "AiController.assistantStream" in html
    assert "learning-mode" in html
    assert "interview-mode" in html
    assert "https://" not in html


def test_renderer_escapes_source_html():
    data = sample_data()
    data["chapters"][0]["snippets"][0]["code"] = "<script>alert(1)</script>"
    html = render_html(data, "2026-11-19T12:00:00+08:00")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `python -m pytest tools/tests/test_interview_code_walkthrough_render.py -v`  
Expected: FAIL because `render.py` does not exist.

- [ ] **Step 3: Implement the renderer**

The HTML must include:

- fixed left navigation generated from chapter titles;
- search input filtering chapter and snippet titles;
- chapter summaries;
- source cards with escaped code and real line numbers;
- explanation, interview-question, and pitfall sections;
- copy-path and `vscode://file/...:line` controls;
- `learning-mode` and `interview-mode` toggles;
- per-snippet mastery checkboxes persisted to `localStorage`;
- inline CSS and inline JavaScript only;
- generation timestamp and build counts.

Use `html.escape()` for every source or manifest string. Do not interpolate raw code into JavaScript.

- [ ] **Step 4: Run renderer tests**

Run: `python -m pytest tools/tests/test_interview_code_walkthrough_render.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/interview_code_walkthrough/render.py tools/tests/test_interview_code_walkthrough_render.py
git commit -m "feat: add offline walkthrough renderer"
```

---

### Task 3: Nine-Chapter Async Hazard-Creation Manifest

**Files:**
- Create: `tools/interview_code_walkthrough/manifest.json`
- Test: extend `tools/tests/test_interview_code_walkthrough_build.py`

**Interfaces:**
- Consumes: manifest schema from Task 1.
- Produces: the nine approved chapters and 20–30 source snippets used by Task 4.

- [ ] **Step 1: Add a failing manifest coverage test**

```python
def test_checked_in_manifest_has_all_chapters():
    root = Path(__file__).parents[2]
    data = load_manifest(root / "tools/interview_code_walkthrough/manifest.json")
    titles = [chapter["title"] for chapter in data["chapters"]]
    assert len(titles) == 9
    assert "Java SSE 入口" in titles
    assert "前端确认、SSE 与分级轮询" in titles
```

- [ ] **Step 2: Run the test to confirm failure**

Run: `python -m pytest tools/tests/test_interview_code_walkthrough_build.py::test_checked_in_manifest_has_all_chapters -v`  
Expected: FAIL because the manifest is absent.

- [ ] **Step 3: Create the manifest with these exact chapters and source ranges**

| Chapter | Source ranges |
|---|---|
| Java SSE 入口 | `AiController.java` 78–86, 92–134; `AiService.java` 220–230, 242–276 |
| LangGraph 确认与提交节点 | `assistant_graph.py` 2322–2358, 2359–2439, 2442–2495 |
| Python request + outbox 事务 | `hazard_submit.py` 313–328, 329–388; `hazard_create_queue.py` 150–184, 185–202 |
| Relay 扫描与 RabbitMQ 投递 | `hazard_create_queue.py` 349–391, 393–438 |
| Java RabbitMQ Listener | `HazardCreateConsumer.java` 34–52, 54–80 |
| Java createAi 事务与幂等 | `HazardServiceImpl.java` 150–164, 180–228 |
| 成功回执与 Python 状态更新 | `HazardCreateResultPublisher.java` 26–44; `hazard_create_queue.py` 497–529 |
| RequestReconciler 超时对账 | `hazard_create_queue.py` 587–659; `HazardController.java` 128–142 |
| 前端确认、SSE 与分级轮询 | `hazardPoll.js` 1–22; `request.js` 43–100; `HomeView.vue` 1096–1124, 1192–1210 |

Each snippet must include a concrete explanation, at least one interview question, and at least one pitfall. Python ranges must explain unfamiliar syntax in plain Chinese, especially `with`, exception handling, dictionaries, `async`/`await`, and `async for`.

- [ ] **Step 4: Validate every anchor and range**

Run: `python tools/build_interview_code_walkthrough.py --check-only`  
Expected: exit code 0; output reports 9 chapters and at least 20 resolved snippets.

- [ ] **Step 5: Commit**

```bash
git add tools/interview_code_walkthrough/manifest.json tools/tests/test_interview_code_walkthrough_build.py
git commit -m "feat: add async hazard creation walkthrough manifest"
```

---

### Task 4: CLI, Generated Page, and Usage Guide

**Files:**
- Create: `tools/build_interview_code_walkthrough.py`
- Create: `output/interview-code-walkthrough/README.md`
- Generate: `output/interview-code-walkthrough/index.html`
- Test: `tools/tests/test_interview_code_walkthrough_cli.py`

**Interfaces:**
- Consumes: `build_walkthrough()` from Task 1 and manifest from Task 3.
- Produces: CLI exit codes and generated offline artifact.

- [ ] **Step 1: Write a failing CLI test**

```python
import subprocess, sys
from pathlib import Path


def test_cli_check_only_validates_manifest():
    root = Path(__file__).parents[2]
    result = subprocess.run(
        [sys.executable, "tools/build_interview_code_walkthrough.py", "--check-only"],
        cwd=root, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "9 chapters" in result.stdout
```

- [ ] **Step 2: Run the CLI test to confirm failure**

Run: `python -m pytest tools/tests/test_interview_code_walkthrough_cli.py -v`  
Expected: FAIL because the CLI entrypoint does not exist.

- [ ] **Step 3: Implement the CLI and README**

CLI behavior:

```text
python tools/build_interview_code_walkthrough.py
python tools/build_interview_code_walkthrough.py --check-only
```

- Default build writes `output/interview-code-walkthrough/index.html`.
- `--check-only` validates and extracts all snippets without writing HTML.
- Errors print the failing chapter/snippet and return exit code 1.
- Success prints chapter count, snippet count, and output path.

README must document purpose, commands, update procedure after source-line changes, and the fact that generated HTML is offline and read-only.

- [ ] **Step 4: Generate the HTML and run tests**

Run:

```bash
python tools/build_interview_code_walkthrough.py
python -m pytest tools/tests/test_interview_code_walkthrough_build.py tools/tests/test_interview_code_walkthrough_render.py tools/tests/test_interview_code_walkthrough_cli.py -v
```

Expected: all tests pass and HTML is generated.

- [ ] **Step 5: Commit**

```bash
git add tools/build_interview_code_walkthrough.py output/interview-code-walkthrough/README.md output/interview-code-walkthrough/index.html tools/tests/test_interview_code_walkthrough_cli.py
git commit -m "feat: generate offline interview code walkthrough"
```

---

### Task 5: Browser and Stale-Source Verification

**Files:**
- Modify if browser checks reveal issues: generated renderer or manifest only.
- Verify: `output/interview-code-walkthrough/index.html`

- [ ] **Step 1: Open the generated page locally**

Open `output/interview-code-walkthrough/index.html` in the Codex browser preview or a local browser.

Expected:

- all nine chapters appear in the left navigation;
- code can be read with line numbers;
- search filters chapters and snippets;
- learning/interview mode switches visibly;
- mastery checkboxes survive a page reload;
- copy-path and VS Code link controls exist;
- no external network request is required.

- [ ] **Step 2: Verify stale-source protection without editing business source**

Create a temporary test source and manifest in a temporary directory, then run `extract_snippet()` with a deliberately wrong anchor.

Run: `python -m pytest tools/tests/test_interview_code_walkthrough_build.py -v`  
Expected: mismatch test passes and reports `anchor mismatch`.

- [ ] **Step 3: Run the complete verification suite once more**

Run:

```bash
python tools/build_interview_code_walkthrough.py
python -m pytest tools/tests/test_interview_code_walkthrough_build.py tools/tests/test_interview_code_walkthrough_render.py tools/tests/test_interview_code_walkthrough_cli.py -v
git diff --check
```

Expected: build succeeds, all tests pass, and no whitespace errors.

- [ ] **Step 4: Commit any verification fixes**

```bash
git add tools/interview_code_walkthrough output/interview-code-walkthrough tools/tests
git commit -m "test: verify offline walkthrough viewer"
```
