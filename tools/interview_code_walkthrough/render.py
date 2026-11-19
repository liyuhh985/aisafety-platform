"""Render a self-contained, offline HTML walkthrough."""

from __future__ import annotations

from html import escape
from pathlib import Path


def _vscode_uri(source_path: str, line_start: int) -> str:
    posix_path = Path(source_path).as_posix()
    return f"vscode://file/{posix_path}:{line_start}"


def _render_code(code: str, line_start: int, line_notes: list[dict]) -> str:
    notes_by_offset = {note["lineOffset"]: note["text"] for note in line_notes}
    rows = []
    for offset, line in enumerate(code.splitlines()):
        line_number = line_start + offset
        rows.append(
            '<div class="code-line">'
            f'<span class="line-number">{line_number}</span>'
            f'<span class="line-text">{escape(line) or " "}</span>'
            "</div>"
        )
        note = notes_by_offset.get(offset)
        if note:
            rows.append(
                '<div class="syntax-note annotation">'
                f'<span class="syntax-badge">L{line_number} · 语法注</span>'
                f'<span>{escape(note)}</span>'
                "</div>"
            )
    return "\n".join(rows)


def _render_interview_questions(questions: list[str], answers: list[str]) -> str:
    items = []
    for question, answer in zip(questions, answers, strict=True):
        items.append(
            '<details class="answer-disclosure">'
            f'<summary>{escape(question)}</summary>'
            '<div class="answer-body">'
            '<span class="answer-label">参考答案</span>'
            f'<p>{escape(answer)}</p>'
            '</div>'
            '</details>'
        )
    return "".join(items)


def _render_list(items: list[str], class_name: str) -> str:
    rendered = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f'<ul class="{class_name}">{rendered}</ul>'


def _render_snippet(snippet: dict, chapter_id: str, snippet_index: int) -> str:
    stable_id = f"{chapter_id}-{snippet_index}"
    source_uri = _vscode_uri(snippet["sourcePath"], snippet["lineStart"])
    search_text = " ".join(
        [
            snippet["title"],
            snippet["method"],
            snippet["file"],
            snippet["explain"],
            *snippet["interviewQuestions"],
            *snippet["interviewAnswers"],
            *snippet["pitfalls"],
            *(note["text"] for note in snippet["lineNotes"]),
        ]
    ).casefold()

    return f'''
    <article class="snippet-card searchable" data-search="{escape(search_text, quote=True)}" id="snippet-{escape(stable_id, quote=True)}">
      <header class="snippet-head">
        <div>
          <p class="eyebrow">代码片段</p>
          <h3>{escape(snippet["title"])}</h3>
          <p class="method-name">{escape(snippet["method"])}</p>
        </div>
        <label class="mastery-toggle" title="标记为已掌握">
          <input type="checkbox" data-mastery-id="{escape(stable_id, quote=True)}">
          <span>已掌握</span>
        </label>
      </header>

      <div class="file-line">
        <code>{escape(snippet["file"])}</code>
        <span>第 {snippet["lineStart"]}–{snippet["lineEnd"]} 行</span>
      </div>

      <div class="code-shell" aria-label="{escape(snippet["title"], quote=True)} 源码">
        <div class="code-toolbar">
          <span>SOURCE</span>
          <button class="icon-button copy-path" data-copy="{escape(snippet["sourcePath"], quote=True)}">复制路径</button>
          <a class="icon-button" href="{escape(source_uri, quote=True)}">在 VS Code 打开</a>
        </div>
        <div class="code-lines">{_render_code(snippet["code"], snippet["lineStart"], snippet["lineNotes"])}</div>
      </div>

      <div class="annotation explain-block">
        <p class="annotation-label">这段在做什么</p>
        <p>{escape(snippet["explain"])}</p>
      </div>

      <div class="annotation interview-grid">
        <section>
          <p class="annotation-label">面试官可能问 · 点击展开答案</p>
          {_render_interview_questions(snippet["interviewQuestions"], snippet["interviewAnswers"])}
        </section>
        <section>
          <p class="annotation-label">容易讲错的边界</p>
          {_render_list(snippet["pitfalls"], "pitfall-list")}
        </section>
      </div>

      <footer class="snippet-footer">
        <span>片段哈希 {escape(snippet["codeHash"][:12])}</span>
        <span>{escape(Path(snippet["sourcePath"]).name)}</span>
      </footer>
    </article>
    '''


def _render_chapter(chapter: dict, chapter_index: int) -> str:
    snippets = "".join(
        _render_snippet(snippet, chapter["id"], snippet_index)
        for snippet_index, snippet in enumerate(chapter["snippets"], start=1)
    )
    chapter_number = f"{chapter_index:02d}"
    return f'''
    <section class="chapter searchable" data-search="{escape((chapter["title"] + " " + chapter["summary"]).casefold(), quote=True)}" id="{escape(chapter["id"], quote=True)}">
      <header class="chapter-head">
        <div class="chapter-number">{chapter_number}</div>
        <div>
          <p class="eyebrow">流程节点 {chapter_number}</p>
          <h2>{escape(chapter["title"])}</h2>
          <p class="chapter-summary">{escape(chapter["summary"])}</p>
        </div>
      </header>
      <div class="snippet-stack">{snippets}</div>
    </section>
    '''


def render_html(data: dict, generated_at: str) -> str:
    """Render all chapters into one offline HTML document."""
    chapters = data["chapters"]
    snippet_count = sum(len(chapter["snippets"]) for chapter in chapters)
    chapter_links = []
    chapter_sections = []

    for index, chapter in enumerate(chapters, start=1):
        chapter_links.append(
            f'<a class="nav-link" href="#{escape(chapter["id"], quote=True)}" '
            f'data-nav-target="{escape(chapter["id"], quote=True)}">'
            f'<span class="nav-index">{index:02d}</span>'
            f'<span>{escape(chapter["title"])}</span></a>'
        )
        chapter_sections.append(_render_chapter(chapter, index))

    nav_html = "\n".join(chapter_links)
    chapter_html = "\n".join(chapter_sections)

    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(data["title"])}</title>
<style>
:root {{
  --ink: #0b1b24;
  --steel: #153441;
  --steel-soft: #244f5c;
  --paper: #edf2ee;
  --panel: #f8fbf8;
  --line: #cbd5d0;
  --muted: #66767b;
  --signal: #2e8f83;
  --signal-soft: #d8efea;
  --amber: #c78b2b;
  --amber-soft: #f4e7cc;
  --white: #ffffff;
  --mono: "Cascadia Code", "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  --body: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
}}
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  margin: 0;
  color: var(--ink);
  background:
    linear-gradient(90deg, rgba(21, 52, 65, 0.045) 1px, transparent 1px),
    linear-gradient(rgba(21, 52, 65, 0.045) 1px, transparent 1px),
    var(--paper);
  background-size: 28px 28px;
  font-family: var(--body);
  line-height: 1.65;
}}
button, a, input {{ font: inherit; }}
a {{ color: inherit; }}
button, .icon-button {{ cursor: pointer; }}

.sidebar {{
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 20;
  width: 318px;
  display: flex;
  flex-direction: column;
  padding: 28px 22px 22px;
  color: #eaf3f0;
  background:
    radial-gradient(circle at 20% 4%, rgba(46, 143, 131, 0.22), transparent 26%),
    linear-gradient(155deg, #0b1b24, #102a35 58%, #0d222c);
  box-shadow: 12px 0 38px rgba(11, 27, 36, 0.16);
}}
.brand {{ display: flex; gap: 12px; align-items: center; margin-bottom: 24px; }}
.brand-mark {{
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255,255,255,0.2);
  background: rgba(46,143,131,0.16);
  color: #9ae3d9;
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 700;
}}
.brand-copy strong {{ display: block; font-family: var(--mono); font-size: 15px; letter-spacing: 0.02em; }}
.brand-copy span {{ color: #9db3b8; font-size: 12px; }}
.nav-caption {{ color: #8fa8ae; font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; margin: 0 0 10px; }}
.nav {{ display: flex; flex-direction: column; gap: 4px; overflow-y: auto; padding-right: 4px; }}
.nav-link {{
  position: relative;
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 10px;
  align-items: center;
  padding: 11px 10px;
  border-left: 2px solid transparent;
  text-decoration: none;
  color: #c5d5d7;
  transition: color 160ms ease, background 160ms ease, border-color 160ms ease;
}}
.nav-link:hover, .nav-link.is-active {{
  color: #ffffff;
  background: rgba(255,255,255,0.055);
  border-left-color: var(--signal);
}}
.nav-link.is-active .nav-index {{ color: #a9e7df; }}
.nav-index {{ font-family: var(--mono); color: #6f9096; font-size: 12px; }}
.sidebar-stats {{ margin-top: auto; padding-top: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
.stat {{ padding: 12px; border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); }}
.stat strong {{ display: block; font-family: var(--mono); color: #a9e7df; font-size: 18px; }}
.stat span {{ color: #8fa8ae; font-size: 11px; }}

.main {{ margin-left: 318px; min-height: 100vh; }}
.hero {{
  position: relative;
  overflow: hidden;
  padding: 56px clamp(28px, 5vw, 76px) 42px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(125deg, rgba(255,255,255,0.94), rgba(248,251,248,0.84));
}}
.hero::after {{
  content: "";
  position: absolute;
  right: -90px;
  top: -150px;
  width: 420px;
  height: 420px;
  border: 1px solid rgba(46,143,131,0.16);
  transform: rotate(28deg);
  pointer-events: none;
}}
.hero-top {{ display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; position: relative; z-index: 1; }}
.hero-copy {{ max-width: 760px; }}
.kicker {{ margin: 0 0 12px; color: var(--signal); font-family: var(--mono); font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; }}
h1 {{
  margin: 0;
  max-width: 780px;
  font-family: var(--mono);
  font-size: clamp(34px, 5vw, 68px);
  line-height: 1.02;
  letter-spacing: -0.055em;
}}
.hero-subtitle {{ margin: 20px 0 0; color: var(--muted); max-width: 680px; font-size: 16px; }}
.hero-actions {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; position: relative; z-index: 2; }}
.mode-button {{
  border: 1px solid var(--steel);
  padding: 10px 14px;
  background: var(--steel);
  color: white;
  font-family: var(--mono);
  font-size: 12px;
}}
.mode-button:hover, .mode-button:focus-visible {{ background: var(--signal); border-color: var(--signal); outline: none; }}
.search-wrap {{ margin-top: 32px; max-width: 620px; position: relative; z-index: 1; }}
.search-wrap label {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 7px; }}
.search-input {{
  width: 100%;
  border: 1px solid #aebdb7;
  background: rgba(255,255,255,0.88);
  padding: 13px 15px;
  font-family: var(--mono);
  font-size: 13px;
  outline: none;
}}
.search-input:focus {{ border-color: var(--signal); box-shadow: 0 0 0 3px rgba(46,143,131,0.13); }}
.flow-note {{ margin-top: 25px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; color: var(--muted); font-size: 12px; }}
.flow-note code {{ font-family: var(--mono); color: var(--steel); background: var(--signal-soft); padding: 3px 7px; }}

.content {{ padding: 12px clamp(28px, 5vw, 76px) 80px; }}
.chapter {{ scroll-margin-top: 22px; padding: 54px 0 18px; border-bottom: 1px solid rgba(21,52,65,0.14); }}
.chapter-head {{ display: grid; grid-template-columns: 74px 1fr; gap: 22px; align-items: start; margin-bottom: 24px; }}
.chapter-number {{
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  background: var(--ink);
  color: #a9e7df;
  font-family: var(--mono);
  font-size: 19px;
  box-shadow: 7px 7px 0 var(--signal-soft);
}}
h2 {{ margin: 2px 0 5px; font-family: var(--mono); font-size: clamp(24px, 3vw, 38px); line-height: 1.15; letter-spacing: -0.035em; }}
.chapter-summary {{ margin: 0; max-width: 780px; color: var(--muted); }}
.eyebrow {{ margin: 0 0 6px; color: var(--signal); font-family: var(--mono); font-size: 10px; letter-spacing: 0.13em; text-transform: uppercase; }}
.snippet-stack {{ display: flex; flex-direction: column; gap: 22px; }}
.snippet-card {{
  scroll-margin-top: 18px;
  border: 1px solid var(--line);
  background: rgba(248,251,248,0.95);
  box-shadow: 0 12px 30px rgba(11,27,36,0.055);
}}
.snippet-card[hidden], .chapter[hidden] {{ display: none; }}
.snippet-head {{ display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; padding: 21px 22px 17px; border-bottom: 1px solid var(--line); }}
h3 {{ margin: 0; font-family: var(--mono); font-size: 20px; line-height: 1.25; }}
.method-name {{ margin: 5px 0 0; color: var(--muted); font-family: var(--mono); font-size: 12px; }}
.mastery-toggle {{ display: flex; gap: 7px; align-items: center; white-space: nowrap; color: var(--muted); font-size: 12px; padding-top: 4px; }}
.mastery-toggle input {{ accent-color: var(--signal); width: 17px; height: 17px; }}
.file-line {{ display: flex; justify-content: space-between; gap: 16px; padding: 9px 22px; background: var(--amber-soft); border-bottom: 1px solid #dfcda7; font-size: 11px; color: #735522; }}
.file-line code {{ font-family: var(--mono); overflow-wrap: anywhere; }}
.code-shell {{ margin: 18px 22px 0; border: 1px solid #203843; background: #0e222b; overflow: hidden; }}
.code-toolbar {{ display: flex; align-items: center; gap: 8px; padding: 8px 11px; color: #88a8ad; border-bottom: 1px solid #28434d; font-family: var(--mono); font-size: 10px; }}
.code-toolbar span {{ margin-right: auto; letter-spacing: 0.12em; }}
.icon-button {{ border: 1px solid #36535c; background: transparent; color: #c5dcde; padding: 5px 8px; text-decoration: none; font-size: 10px; font-family: var(--mono); }}
.icon-button:hover, .icon-button:focus-visible {{ border-color: #75bdb2; color: white; outline: none; }}
.code-lines {{ max-height: 540px; overflow: auto; padding: 13px 0; font-family: var(--mono); font-size: 12.5px; line-height: 1.62; tab-size: 4; }}
.code-line {{ display: grid; grid-template-columns: 68px minmax(0, 1fr); min-width: max-content; color: #d9e8e6; }}
.line-number {{ color: #638087; text-align: right; padding-right: 17px; user-select: none; border-right: 1px solid #29444e; }}
.line-text {{ white-space: pre; padding-left: 17px; padding-right: 24px; }}
.syntax-note {{
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin: 3px 22px 8px 86px;
  padding: 7px 10px;
  border-left: 2px solid #75bdb2;
  background: rgba(46,143,131,0.11);
  color: #b9d8d5;
  font-size: 11px;
  line-height: 1.55;
}}
.syntax-badge {{
  flex: 0 0 auto;
  color: #93d8ce;
  font-size: 10px;
  letter-spacing: 0.06em;
  white-space: nowrap;
}}
.syntax-note span:last-child {{ white-space: normal; }}
.answer-disclosure {{
  border: 1px solid #d8e1dc;
  background: #f8fbf8;
  margin: 6px 0;
}}
.answer-disclosure summary {{
  cursor: pointer;
  padding: 10px 12px;
  font-weight: 600;
  color: #23424b;
}}
.answer-disclosure summary:hover, .answer-disclosure summary:focus-visible {{
  color: var(--signal);
  outline: none;
}}
.answer-body {{ padding: 0 12px 12px; border-top: 1px solid #e2e9e5; }}
.answer-label {{ display: inline-block; margin-top: 10px; color: var(--signal); font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em; }}
.answer-body p {{ margin: 6px 0 0; color: #35494f; }}
.annotation {{ margin: 18px 22px 0; }}
.annotation-label {{ margin: 0 0 7px; color: var(--signal); font-family: var(--mono); font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; }}
.explain-block {{ padding: 16px 18px; border-left: 4px solid var(--signal); background: var(--signal-soft); }}
.explain-block p:last-child {{ margin: 0; }}
.interview-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; padding-bottom: 18px; }}
.interview-grid section {{ padding: 15px 17px; border: 1px solid var(--line); background: white; }}
.question-list, .pitfall-list {{ margin: 0; padding-left: 19px; }}
.question-list li, .pitfall-list li {{ margin: 5px 0; }}
.pitfall-list li::marker {{ color: var(--amber); }}
.snippet-footer {{ display: flex; justify-content: space-between; gap: 16px; padding: 10px 22px; border-top: 1px solid var(--line); color: var(--muted); font-family: var(--mono); font-size: 10px; }}

.interview-mode .annotation {{ display: none; }}
.interview-mode .snippet-footer span:first-child {{ display: none; }}
.interview-mode .content {{ max-width: 1200px; }}
.no-results {{
  display: none;
  margin: 40px 0;
  padding: 20px;
  border: 1px dashed #91aaa3;
  color: var(--muted);
  text-align: center;
}}
body.is-searching .no-results:not(.has-visible) {{ display: block; }}

@media (max-width: 900px) {{
  .sidebar {{ position: static; width: auto; padding: 20px; }}
  .nav {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); overflow: visible; }}
  .nav-link {{ grid-template-columns: 28px 1fr; }}
  .sidebar-stats {{ margin-top: 18px; }}
  .main {{ margin-left: 0; }}
  .hero {{ padding: 38px 22px 30px; }}
  .hero-top {{ flex-direction: column; }}
  .hero-actions {{ justify-content: flex-start; }}
  .content {{ padding: 8px 18px 60px; }}
  .interview-grid {{ grid-template-columns: 1fr; }}
}}
@media (max-width: 560px) {{
  .nav {{ grid-template-columns: 1fr; }}
  .chapter-head {{ grid-template-columns: 48px 1fr; gap: 15px; }}
  .chapter-number {{ width: 44px; height: 44px; font-size: 15px; }}
  .snippet-head, .file-line, .snippet-footer {{ flex-direction: column; }}
  .snippet-head, .file-line, .code-shell, .annotation, .snippet-footer {{ margin-left: 12px; margin-right: 12px; }}
  .code-line {{ grid-template-columns: 52px minmax(0, 1fr); }}
}}
@media (prefers-reduced-motion: reduce) {{
  html {{ scroll-behavior: auto; }}
  *, *::before, *::after {{ animation: none !important; transition: none !important; }}
}}
</style>
</head>
<body class="learning-mode">
<aside class="sidebar">
  <div class="brand">
    <div class="brand-mark">AI</div>
    <div class="brand-copy">
      <strong>CODE TRACE</strong>
      <span>异步建单代码讲解册</span>
    </div>
  </div>
  <p class="nav-caption">业务链路 / 09 NODES</p>
  <nav class="nav" aria-label="章节导航">{nav_html}</nav>
  <div class="sidebar-stats">
    <div class="stat"><strong>9</strong><span>流程章节</span></div>
    <div class="stat"><strong>{snippet_count}</strong><span>真实片段</span></div>
  </div>
</aside>

<main class="main">
  <header class="hero">
    <div class="hero-top">
      <div class="hero-copy">
        <p class="kicker">Interview Code Walkthrough / Offline Edition</p>
        <h1>{escape(data["title"])}</h1>
        <p class="hero-subtitle">{escape(data["subtitle"])}</p>
      </div>
      <div class="hero-actions">
        <button class="mode-button" id="mode-toggle" type="button">切换到面试模式</button>
      </div>
    </div>
    <div class="search-wrap">
      <label for="search-input">搜索章节、类名、方法、源码说明或面试追问</label>
      <input class="search-input" id="search-input" type="search" placeholder="例如 RelayWorker、requestId、幂等、SSE" autocomplete="off">
    </div>
    <div class="flow-note">
      <span>主线：</span>
      <code>Java SSE</code><span>→</span><code>LangGraph</code><span>→</span><code>Outbox</code><span>→</span><code>RabbitMQ</code><span>→</span><code>Java Listener</code><span>→</span><code>Polling</code>
      <span>·</span><span>生成于 {escape(generated_at)}</span>
    </div>
  </header>

  <div class="content">
    {chapter_html}
    <div class="no-results" id="no-results">没有匹配的章节或代码片段。</div>
  </div>
</main>

<script>
(() => {{
  const body = document.body;
  const modeButton = document.getElementById('mode-toggle');
  const searchInput = document.getElementById('search-input');
  const navLinks = Array.from(document.querySelectorAll('.nav-link'));
  const chapters = Array.from(document.querySelectorAll('.chapter'));
  const noResults = document.getElementById('no-results');
  const masteries = Array.from(document.querySelectorAll('[data-mastery-id]'));

  masteries.forEach((input) => {{
    const key = 'walkthrough-mastery:' + input.dataset.masteryId;
    input.checked = localStorage.getItem(key) === '1';
    input.addEventListener('change', () => {{
      localStorage.setItem(key, input.checked ? '1' : '0');
    }});
  }});

  function setMode(interview) {{
    body.classList.toggle('interview-mode', interview);
    body.classList.toggle('learning-mode', !interview);
    modeButton.textContent = interview ? '切换到学习模式' : '切换到面试模式';
    localStorage.setItem('walkthrough-mode', interview ? 'interview' : 'learning');
  }}

  setMode(localStorage.getItem('walkthrough-mode') === 'interview');
  modeButton.addEventListener('click', () => {{
    setMode(!body.classList.contains('interview-mode'));
  }});

  document.querySelectorAll('.copy-path').forEach((button) => {{
    button.addEventListener('click', async () => {{
      const original = button.textContent;
      try {{
        await navigator.clipboard.writeText(button.dataset.copy || '');
        button.textContent = '已复制';
      }} catch (error) {{
        button.textContent = '复制失败';
      }}
      setTimeout(() => {{ button.textContent = original; }}, 1400);
    }});
  }});

  function filterContent() {{
    const query = searchInput.value.trim().toLowerCase();
    body.classList.toggle('is-searching', Boolean(query));
    let visibleChapters = 0;
    chapters.forEach((chapter) => {{
      const snippets = Array.from(chapter.querySelectorAll('.snippet-card'));
      let chapterVisible = false;
      snippets.forEach((snippet) => {{
        const snippetMatch = !query || (snippet.dataset.search || '').includes(query);
        snippet.hidden = Boolean(query) && !snippetMatch;
        chapterVisible = chapterVisible || snippetMatch;
      }});
      chapter.hidden = Boolean(query) && !chapterVisible;
      if (chapterVisible) visibleChapters += 1;
    }});
    noResults.classList.toggle('has-visible', visibleChapters > 0);
  }}

  searchInput.addEventListener('input', filterContent);

  const observer = new IntersectionObserver((entries) => {{
    entries.forEach((entry) => {{
      if (!entry.isIntersecting) return;
      navLinks.forEach((link) => {{
        link.classList.toggle('is-active', link.dataset.navTarget === entry.target.id);
      }});
    }});
  }}, {{ rootMargin: '-18% 0px -66% 0px', threshold: 0 }});

  chapters.forEach((chapter) => observer.observe(chapter));
}})();
</script>
</body>
</html>
'''
