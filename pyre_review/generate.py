"""Generate self-contained review HTML from diff data."""

import html
import json
import os

from pygments import highlight as pyg_highlight
from pygments.lexers import get_lexer_for_filename, TextLexer
from pygments.formatters import HtmlFormatter

from .git_ops import FileDiff, DiffLine


def _classify_lang(path: str) -> str:
    """Get a language hint for a file path."""
    ext_map = {
        ".py": "python", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
        ".c": "c", ".h": "cpp", ".hpp": "cpp", ".cmake": "cmake",
        ".js": "javascript", ".ts": "typescript", ".rs": "rust",
        ".go": "go", ".java": "java", ".sh": "bash", ".yaml": "yaml",
        ".yml": "yaml", ".json": "json", ".toml": "toml", ".md": "markdown",
    }
    _, ext = os.path.splitext(path)
    return ext_map.get(ext, "text")


def _get_lexer(path: str):
    try:
        return get_lexer_for_filename(path, stripall=True)
    except Exception:
        return TextLexer()


def _highlight_lines(path: str, lines: list[DiffLine]) -> list[tuple[DiffLine, str]]:
    """Syntax-highlight content using pygments, returning (DiffLine, highlighted_html) pairs."""
    lexer = _get_lexer(path)
    # We highlight all lines together for consistent tokenization, then split
    full_text = "\n".join(dl.content for dl in lines)
    formatter = HtmlFormatter(nowrap=True, classprefix="hl-")
    highlighted = pyg_highlight(full_text, lexer, formatter)
    hl_lines = highlighted.split("\n")
    # Pad if needed (pygments may add/remove trailing newlines)
    while len(hl_lines) < len(lines):
        hl_lines.append("")
    return list(zip(lines, hl_lines[: len(lines)]))


def _build_file_data(files: list[FileDiff], comments: list[dict]) -> list[dict]:
    """Build JSON-serializable file data for the template."""
    # Group comments by file
    comments_by_file: dict[str, list[dict]] = {}
    for c in comments:
        if c.get("type") == "comment":
            f = c.get("file", "")
            comments_by_file.setdefault(f, []).append(c)

    file_data = []
    for fd in files:
        # Highlight lines
        hl_pairs = _highlight_lines(fd.path, fd.lines)
        rendered_lines = []
        for dl, hl_html in hl_pairs:
            rendered_lines.append({
                "type": dl.type,
                "old": dl.old_lineno,
                "new": dl.new_lineno,
                "html": hl_html,
                "raw": dl.content,
            })
        file_data.append({
            "path": fd.path,
            "status": fd.status,
            "additions": fd.additions,
            "deletions": fd.deletions,
            "lines": rendered_lines,
            "comments": comments_by_file.get(fd.path, []),
        })
    return file_data


def generate_html(
    files: list[FileDiff],
    comments: list[dict],
    topic: str,
    base: str,
    commits: list[dict],
    stats: tuple[int, int, int],
    bead_config: dict | None = None,
) -> str:
    """Generate a self-contained HTML review page."""
    verdicts = [c for c in comments if c.get("type") == "verdict"]
    file_data = _build_file_data(files, comments)
    # Get pygments CSS
    formatter = HtmlFormatter(classprefix="hl-")
    pygments_css = formatter.get_style_defs()

    review_data = {
        "topic": topic,
        "base": base,
        "commits": commits,
        "stats": {"files": stats[0], "insertions": stats[1], "deletions": stats[2]},
        "files": file_data,
        "verdicts": verdicts,
        "bead_config": bead_config,
    }

    return _TEMPLATE.replace("/* __PYGMENTS_CSS__ */", pygments_css).replace(
        '"__REVIEW_DATA__"', json.dumps(review_data)
    )


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pyre-review</title>
<style>
/* __PYGMENTS_CSS__ */

:root {
  --bg: #fff;
  --bg-secondary: #f6f8fa;
  --bg-hover: #ebedf0;
  --border: #d0d7de;
  --text: #1f2328;
  --text-muted: #656d76;
  --added-bg: #dafbe1;
  --added-line-bg: #ccffd8;
  --deleted-bg: #ffebe9;
  --deleted-line-bg: #ffc1ba;
  --comment-bg: #fff8c5;
  --comment-border: #d4a72c;
  --accent: #0969da;
  --accent-emphasis: #0550ae;
  --header-bg: #24292f;
  --header-text: #fff;
  --line-num: #656d76;
  --scrollbar-bg: #ddd;
  --scrollbar-thumb: #aaa;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117;
    --bg-secondary: #161b22;
    --bg-hover: #21262d;
    --border: #30363d;
    --text: #e6edf3;
    --text-muted: #8b949e;
    --added-bg: #12261e;
    --added-line-bg: #1a4028;
    --deleted-bg: #2d1214;
    --deleted-line-bg: #4c1a1e;
    --comment-bg: #2d2200;
    --comment-border: #9e6a03;
    --accent: #58a6ff;
    --accent-emphasis: #79c0ff;
    --header-bg: #010409;
    --header-text: #e6edf3;
    --line-num: #484f58;
    --scrollbar-bg: #21262d;
    --scrollbar-thumb: #484f58;
  }
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); }

#header {
  background: var(--header-bg);
  color: var(--header-text);
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  position: sticky;
  top: 0;
  z-index: 100;
}
#header h1 { font-size: 14px; font-weight: 600; }
#header .stats { font-size: 13px; color: var(--text-muted); }
#header .stats .add { color: #3fb950; }
#header .stats .del { color: #f85149; }
#header .actions { margin-left: auto; display: flex; gap: 8px; }
.btn {
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}
.btn:hover { background: var(--bg-hover); }
.btn-approve { background: #238636; color: #fff; border-color: #238636; }
.btn-approve:hover { background: #2ea043; }
.btn-changes { background: #da3633; color: #fff; border-color: #da3633; }
.btn-changes:hover { background: #e5534b; }

#main {
  display: flex;
  height: calc(100vh - 40px);
}

/* File tree */
#file-tree {
  width: 280px;
  min-width: 200px;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  background: var(--bg-secondary);
  font-size: 13px;
}
#file-tree::-webkit-scrollbar { width: 6px; }
#file-tree::-webkit-scrollbar-track { background: var(--scrollbar-bg); }
#file-tree::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); border-radius: 3px; }

.tree-item {
  padding: 4px 8px 4px 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border-left: 3px solid transparent;
}
.tree-item:hover { background: var(--bg-hover); }
.tree-item.active { background: var(--bg-hover); border-left-color: var(--accent); font-weight: 600; }
.tree-item .status { font-size: 11px; font-weight: 600; width: 16px; text-align: center; }
.tree-item .status.A { color: #3fb950; }
.tree-item .status.M { color: #d29922; }
.tree-item .status.D { color: #f85149; }
.tree-item .has-comments { color: var(--comment-border); font-size: 11px; }
.tree-dir {
  padding: 4px 8px;
  cursor: pointer;
  font-weight: 600;
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}
.tree-dir:hover { background: var(--bg-hover); }
.tree-dir .arrow { transition: transform 0.15s; display: inline-block; }
.tree-dir.collapsed .arrow { transform: rotate(-90deg); }
.tree-dir.collapsed + .tree-children { display: none; }

/* File view */
#file-view {
  flex: 1;
  overflow: auto;
  font-family: "SF Mono", "Fira Code", "Fira Mono", Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 20px;
}
#file-view::-webkit-scrollbar { width: 8px; height: 8px; }
#file-view::-webkit-scrollbar-track { background: var(--scrollbar-bg); }
#file-view::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); border-radius: 4px; }

.file-header {
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  gap: 12px;
  align-items: center;
}
.file-header .file-stats { font-weight: normal; color: var(--text-muted); font-size: 12px; }
.file-header .file-stats .add { color: #3fb950; }
.file-header .file-stats .del { color: #f85149; }

table.code {
  border-collapse: collapse;
  width: 100%;
  table-layout: fixed;
}
table.code td {
  vertical-align: top;
  padding: 0 8px;
  white-space: pre;
  overflow: hidden;
}
.ln {
  width: 50px;
  min-width: 50px;
  text-align: right;
  color: var(--line-num);
  user-select: none;
  cursor: pointer;
  padding-right: 12px !important;
  border-right: 1px solid var(--border);
}
.ln:hover { color: var(--accent); }
.ln-old { width: 50px; min-width: 50px; }
.ln-new { width: 50px; min-width: 50px; }
.code-content { width: 100%; }

tr.line-added { background: var(--added-bg); }
tr.line-added .code-content { background: var(--added-line-bg); }
tr.line-deleted { background: var(--deleted-bg); }
tr.line-deleted .code-content { background: var(--deleted-line-bg); }

/* Change markers */
tr.line-added .ln-new::before { content: "+"; color: #3fb950; margin-right: 4px; }
tr.line-deleted .ln-old::before { content: "-"; color: #f85149; margin-right: 4px; }

/* Comments */
.comment-row td {
  padding: 8px 16px 8px 120px !important;
  background: var(--comment-bg);
  border-top: 1px solid var(--comment-border);
  border-bottom: 1px solid var(--comment-border);
  white-space: normal;
}
.comment-block {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 13px;
  line-height: 1.5;
  max-width: 700px;
}
.comment-block .comment-header {
  font-weight: 600;
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 4px;
}
.comment-block .comment-body { color: var(--text); }
.comment-block.resolved { opacity: 0.5; }
.comment-block.resolved .comment-body { display: none; }
.comment-block.resolved:hover { opacity: 1; cursor: pointer; }
.resolve-btn {
  font-size: 11px;
  color: var(--accent);
  cursor: pointer;
  border: none;
  background: none;
  padding: 2px 4px;
}

/* Comment input */
.comment-input-row td {
  padding: 8px 16px 8px 120px !important;
  background: var(--comment-bg);
  white-space: normal;
}
.comment-input-row textarea {
  width: 100%;
  max-width: 600px;
  min-height: 80px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 13px;
  resize: vertical;
}
.comment-input-row .input-actions {
  margin-top: 6px;
  display: flex;
  gap: 6px;
}

/* Verdict dialog */
#verdict-dialog {
  display: none;
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
  z-index: 200;
  min-width: 400px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
}
#verdict-dialog textarea {
  width: 100%;
  min-height: 80px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  margin: 12px 0;
  background: var(--bg);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
}
#verdict-dialog .dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
#overlay {
  display: none;
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  z-index: 150;
}

/* Toast notifications */
.toast {
  position: fixed;
  bottom: 20px;
  right: 20px;
  padding: 10px 16px;
  background: var(--header-bg);
  color: var(--header-text);
  border-radius: 6px;
  font-size: 13px;
  z-index: 300;
  opacity: 0;
  transition: opacity 0.3s;
}
.toast.show { opacity: 1; }

/* Keyboard help */
#keyboard-help {
  position: fixed;
  bottom: 20px;
  left: 20px;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-secondary);
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
}
kbd {
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 4px;
  font-size: 11px;
  font-family: inherit;
}
</style>
</head>
<body>

<div id="header">
  <h1 id="review-title"></h1>
  <span class="stats" id="review-stats"></span>
  <div class="actions">
    <button class="btn btn-approve" onclick="showVerdict('approve')">Approve</button>
    <button class="btn btn-changes" onclick="showVerdict('request-changes')">Request Changes</button>
  </div>
</div>

<div id="main">
  <div id="file-tree"></div>
  <div id="file-view">
    <div style="padding: 40px; color: var(--text-muted); text-align: center;">
      Select a file from the tree to begin reviewing.
    </div>
  </div>
</div>

<div id="overlay" onclick="hideVerdict()"></div>
<div id="verdict-dialog">
  <h3 id="verdict-title">Submit Review</h3>
  <textarea id="verdict-body" placeholder="Add a summary comment (optional)..."></textarea>
  <div class="dialog-actions">
    <button class="btn" onclick="hideVerdict()">Cancel</button>
    <button class="btn" id="verdict-submit-btn" onclick="submitVerdict()">Submit</button>
  </div>
</div>

<div id="keyboard-help">
  <kbd>j</kbd>/<kbd>k</kbd> files &nbsp;
  <kbd>n</kbd>/<kbd>N</kbd> comments &nbsp;
  <kbd>]</kbd>/<kbd>[</kbd> changes
</div>

<div class="toast" id="toast"></div>

<script>
const DATA = "__REVIEW_DATA__";

let currentFileIdx = -1;
let currentVerdictType = null;
let openCommentInput = null; // track open comment input row

function init() {
  document.getElementById('review-title').textContent =
    `Review: ${DATA.topic} → ${DATA.base}`;
  const s = DATA.stats;
  let statsHtml = `${s.files} files &nbsp; <span class="add">+${s.insertions}</span> <span class="del">-${s.deletions}</span>`;
  if (DATA.bead_config) {
    statsHtml += ` &nbsp; <span style="color:var(--accent)">bead:${DATA.bead_config.review_bead}</span>`;
  }
  document.getElementById('review-stats').innerHTML = statsHtml;
  buildFileTree();
  if (DATA.files.length > 0) selectFile(0);
  document.addEventListener('keydown', handleKey);
}

// --- File Tree ---
function buildFileTree() {
  const tree = document.getElementById('file-tree');
  let html = '';
  let currentDir = null;
  DATA.files.forEach((f, i) => {
    const parts = f.path.split('/');
    const dir = parts.slice(0, -1).join('/');
    const name = parts[parts.length - 1];
    if (dir !== currentDir) {
      if (currentDir !== null) html += `</div>`; // close previous tree-children
      currentDir = dir;
      html += `<div class="tree-dir" onclick="toggleDir(this)"><span class="arrow">▼</span> ${esc(dir || '(root)')}</div>`;
      html += `<div class="tree-children">`;
    }
    const hasComments = f.comments && f.comments.some(c => !c.resolved);
    html += `<div class="tree-item" data-idx="${i}" onclick="selectFile(${i})">`;
    html += `<span class="status ${f.status}">${f.status}</span>`;
    html += `<span title="${esc(f.path)}">${esc(name)}</span>`;
    if (hasComments) html += `<span class="has-comments">●</span>`;
    html += `</div>`;
  });
  if (currentDir !== null) html += `</div>`; // close last tree-children
  tree.innerHTML = html;
}

function toggleDir(el) {
  el.classList.toggle('collapsed');
}

function selectFile(idx) {
  if (idx < 0 || idx >= DATA.files.length) return;
  currentFileIdx = idx;
  // Update tree active state
  document.querySelectorAll('.tree-item').forEach(el => el.classList.remove('active'));
  const item = document.querySelector(`.tree-item[data-idx="${idx}"]`);
  if (item) { item.classList.add('active'); item.scrollIntoView({block: 'nearest'}); }
  renderFile(DATA.files[idx]);
}

// --- File Rendering ---
function renderFile(file, preserveScroll) {
  const view = document.getElementById('file-view');
  let html = `<div class="file-header">
    <span>${esc(file.path)}</span>
    <span class="file-stats"><span class="add">+${file.additions}</span> <span class="del">-${file.deletions}</span></span>
  </div>`;

  html += `<table class="code">`;

  // Group comments by new line number
  const commentsByLine = {};
  (file.comments || []).forEach(c => {
    const key = c.line;
    if (!commentsByLine[key]) commentsByLine[key] = [];
    commentsByLine[key].push(c);
  });

  file.lines.forEach((line, lineIdx) => {
    const cls = line.type === 'added' ? 'line-added' :
                line.type === 'deleted' ? 'line-deleted' : '';
    const oldNum = line.old !== null ? line.old : '';
    const newNum = line.new !== null ? line.new : '';
    const clickTarget = line.new !== null ? line.new : (line.old !== null ? line.old : '');

    html += `<tr class="${cls}" data-line-idx="${lineIdx}">`;
    html += `<td class="ln ln-old">${oldNum}</td>`;
    html += `<td class="ln ln-new" onclick="addCommentAt('${esc(file.path)}', ${clickTarget || 0}, this)">${newNum}</td>`;
    html += `<td class="code-content">${line.html || esc(line.raw)}</td>`;
    html += `</tr>`;

    // Render comments on this new line number
    const lineNum = line.new;
    if (lineNum && commentsByLine[lineNum]) {
      commentsByLine[lineNum].forEach(c => {
        html += renderCommentRow(c);
      });
      delete commentsByLine[lineNum];
    }
  });

  html += `</table>`;
  const prevScroll = view.scrollTop;
  view.innerHTML = html;
  if (!preserveScroll) view.scrollTop = 0;
  else view.scrollTop = prevScroll;
  openCommentInput = null;
}

function renderCommentRow(c) {
  const resolved = c.resolved ? 'resolved' : '';
  const time = new Date(c.timestamp).toLocaleString();
  let h = `<tr class="comment-row"><td colspan="3">`;
  h += `<div class="comment-block ${resolved}" data-id="${c.id}">`;
  h += `<div class="comment-header">${esc(c.author)} · ${time}`;
  if (!c.resolved) {
    h += ` <button class="resolve-btn" onclick="resolveComment('${c.id}')">[resolve]</button>`;
  } else {
    h += ` <span style="color:#3fb950">✓ resolved</span>`;
  }
  h += `</div>`;
  h += `<div class="comment-body">${esc(c.body)}</div>`;
  h += `</div></td></tr>`;
  return h;
}

// --- Comments ---
function addCommentAt(filePath, lineNum, td) {
  if (openCommentInput) {
    openCommentInput.remove();
    openCommentInput = null;
  }
  const tr = td.closest('tr');
  const inputRow = document.createElement('tr');
  inputRow.className = 'comment-input-row';
  inputRow.innerHTML = `<td colspan="3">
    <textarea id="comment-textarea" placeholder="Leave a comment..." autofocus></textarea>
    <div class="input-actions">
      <button class="btn" onclick="submitComment('${escAttr(filePath)}', ${lineNum})">Comment</button>
      <button class="btn" onclick="cancelComment()">Cancel</button>
    </div>
  </td>`;
  tr.after(inputRow);
  openCommentInput = inputRow;
  inputRow.querySelector('textarea').focus();
  // Allow Ctrl+Enter to submit
  inputRow.querySelector('textarea').addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      submitComment(filePath, lineNum);
    }
    if (e.key === 'Escape') cancelComment();
  });
}

function cancelComment() {
  if (openCommentInput) { openCommentInput.remove(); openCommentInput = null; }
}

async function submitComment(filePath, lineNum) {
  const textarea = document.getElementById('comment-textarea');
  if (!textarea || !textarea.value.trim()) return;
  const body = textarea.value.trim();
  try {
    const resp = await fetch('/api/comment', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({file: filePath, line: lineNum, body: body}),
    });
    const comment = await resp.json();
    // Update local data
    const file = DATA.files[currentFileIdx];
    if (!file.comments) file.comments = [];
    file.comments.push(comment);
    renderFile(file, true);
    buildFileTree(); // refresh markers
    toast('Comment added');
  } catch (e) {
    toast('Failed to save comment: ' + e.message);
  }
}

async function resolveComment(id) {
  try {
    await fetch('/api/resolve', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: id}),
    });
    // Update local data
    const file = DATA.files[currentFileIdx];
    const c = file.comments.find(c => c.id === id);
    if (c) { c.resolved = true; c.resolved_at = new Date().toISOString(); }
    renderFile(file, true);
    buildFileTree();
    toast('Comment resolved');
  } catch (e) {
    toast('Failed to resolve: ' + e.message);
  }
}

// --- Verdict ---
function showVerdict(type) {
  currentVerdictType = type;
  document.getElementById('overlay').style.display = 'block';
  document.getElementById('verdict-dialog').style.display = 'block';
  document.getElementById('verdict-title').textContent =
    type === 'approve' ? 'Approve Review' : 'Request Changes';
  const btn = document.getElementById('verdict-submit-btn');
  btn.textContent = type === 'approve' ? 'Approve' : 'Request Changes';
  btn.className = type === 'approve' ? 'btn btn-approve' : 'btn btn-changes';
  document.getElementById('verdict-body').focus();
}

function hideVerdict() {
  document.getElementById('overlay').style.display = 'none';
  document.getElementById('verdict-dialog').style.display = 'none';
}

async function submitVerdict() {
  const body = document.getElementById('verdict-body').value.trim();
  try {
    const resp = await fetch('/api/verdict', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({verdict: currentVerdictType, body: body}),
    });
    const result = await resp.json();
    hideVerdict();
    let msg = currentVerdictType === 'approve' ? 'Review approved!' : 'Changes requested.';
    if (result.bead) {
      if (result.bead.error) {
        msg += ` (bead error: ${result.bead.error})`;
      } else {
        msg += ` Bead created: ${result.bead.bead_id}`;
      }
    }
    toast(msg);
  } catch (e) {
    toast('Failed to submit verdict: ' + e.message);
  }
}

// --- Keyboard Navigation ---
function handleKey(e) {
  // Don't capture when typing in textarea
  if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;

  if (e.key === 'j') {
    selectFile(currentFileIdx + 1);
  } else if (e.key === 'k') {
    selectFile(currentFileIdx - 1);
  } else if (e.key === 'n') {
    scrollToNextComment(e.shiftKey ? -1 : 1);
  } else if (e.key === 'N') {
    scrollToNextComment(-1);
  } else if (e.key === ']') {
    scrollToNextChange(1);
  } else if (e.key === '[') {
    scrollToNextChange(-1);
  }
}

function scrollToNextComment(dir) {
  const comments = document.querySelectorAll('.comment-row');
  if (!comments.length) return;
  const view = document.getElementById('file-view');
  const viewTop = view.scrollTop;
  let target = null;
  if (dir > 0) {
    for (const c of comments) {
      if (c.offsetTop > viewTop + 50) { target = c; break; }
    }
    if (!target) target = comments[0];
  } else {
    for (let i = comments.length - 1; i >= 0; i--) {
      if (comments[i].offsetTop < viewTop - 10) { target = comments[i]; break; }
    }
    if (!target) target = comments[comments.length - 1];
  }
  if (target) target.scrollIntoView({behavior: 'smooth', block: 'center'});
}

function scrollToNextChange(dir) {
  const view = document.getElementById('file-view');
  const rows = view.querySelectorAll('tr.line-added, tr.line-deleted');
  if (!rows.length) return;
  const viewTop = view.scrollTop;
  let target = null;
  if (dir > 0) {
    for (const r of rows) {
      if (r.offsetTop > viewTop + 50) { target = r; break; }
    }
    if (!target) target = rows[0];
  } else {
    for (let i = rows.length - 1; i >= 0; i--) {
      if (rows[i].offsetTop < viewTop - 10) { target = rows[i]; break; }
    }
    if (!target) target = rows[rows.length - 1];
  }
  if (target) target.scrollIntoView({behavior: 'smooth', block: 'center'});
}

// --- Utilities ---
function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}
function escAttr(s) {
  return String(s).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

// --- Init ---
init();
</script>
</body>
</html>
"""
