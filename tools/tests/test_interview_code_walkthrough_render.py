from tools.interview_code_walkthrough.render import render_html


def sample_data():
    return {
        "title": "Code Walkthrough",
        "subtitle": "Offline study page",
        "chapters": [
            {
                "id": "chapter-1",
                "title": "Java entry",
                "summary": "The request enters through Java.",
                "snippets": [
                    {
                        "title": "Controller",
                        "method": "AiController.assistantStream",
                        "file": "AiController.java",
                        "lineStart": 78,
                        "lineEnd": 79,
                        "code": "@PostMapping\npublic SseEmitter assistantStream",
                        "explain": "This forwards the request to Python.",
                        "interviewQuestions": ["Why use SSE?"],
                        "pitfalls": ["Accepted does not mean created."],
                        "sourcePath": r"C:\repo\AiController.java",
                        "codeHash": "abc",
                    }
                ],
            }
        ],
    }


def test_renderer_contains_navigation_code_and_modes():
    html = render_html(sample_data(), "2026-11-19T12:00:00+08:00")

    assert "Java entry" in html
    assert "AiController.assistantStream" in html
    assert "learning-mode" in html
    assert "interview-mode" in html
    assert "https://" not in html
    assert "localStorage" in html


def test_renderer_escapes_source_html():
    data = sample_data()
    data["chapters"][0]["snippets"][0]["code"] = "<script>alert(1)</script>"

    html = render_html(data, "2026-11-19T12:00:00+08:00")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_renderer_includes_code_hash_and_source_path():
    html = render_html(sample_data(), "2026-11-19T12:00:00+08:00")

    assert "abc" in html
    assert "AiController.java" in html
    assert "vscode://file/" in html
