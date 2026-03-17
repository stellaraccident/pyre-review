"""Git operations for pyre-review: diff, log, notes."""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field


@dataclass
class DiffLine:
    type: str  # 'context', 'added', 'deleted'
    old_lineno: int | None
    new_lineno: int | None
    content: str


@dataclass
class FileDiff:
    path: str
    status: str  # 'A', 'M', 'D'
    lines: list[DiffLine] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0


def _run(cmd: list[str], repo: str) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=repo, check=False
    )
    if result.returncode != 0 and result.stderr:
        # Some git commands return non-zero for normal conditions
        pass
    return result.stdout


def get_changed_files(repo: str, topic: str, base: str) -> list[tuple[str, str]]:
    """Return list of (status, path) for changed files."""
    out = _run(["git", "diff", "--name-status", f"{base}..{topic}"], repo)
    files = []
    for line in out.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t", 1)
        status, path = parts[0][0], parts[-1]  # Handle renames (R100\told\tnew)
        files.append((status, path))
    return files


def get_diff_files(repo: str, topic: str, base: str) -> list[FileDiff]:
    """Parse full-context unified diff into FileDiff objects."""
    out = _run(
        ["git", "diff", "-U99999", "--no-color", f"{base}..{topic}"],
        repo,
    )
    # Also get name-status for file status info (path → status)
    status_map = {path: status for status, path in get_changed_files(repo, topic, base)}

    files: list[FileDiff] = []
    current: FileDiff | None = None
    old_line = 0
    new_line = 0

    for line in out.split("\n"):
        # New file header
        if line.startswith("diff --git"):
            if current:
                files.append(current)
            current = None
            continue

        if line.startswith("--- "):
            continue

        if line.startswith("+++ "):
            path = line[6:]  # strip '+++ b/'
            if path == "/dev/null":
                continue
            status = status_map.get(path, "M")
            current = FileDiff(path=path, status=status)
            continue

        if line.startswith("@@"):
            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                old_line = int(m.group(1))
                new_line = int(m.group(2))
            continue

        if current is None:
            continue

        if line.startswith("+"):
            current.lines.append(DiffLine("added", None, new_line, line[1:]))
            current.additions += 1
            new_line += 1
        elif line.startswith("-"):
            current.lines.append(DiffLine("deleted", old_line, None, line[1:]))
            current.deletions += 1
            old_line += 1
        elif line.startswith("\\"):
            # "\ No newline at end of file"
            continue
        else:
            # Context line (starts with space or is empty after the diff prefix)
            content = line[1:] if line.startswith(" ") else line
            current.lines.append(DiffLine("context", old_line, new_line, content))
            old_line += 1
            new_line += 1

    if current:
        files.append(current)

    # For files with no diff output (e.g., binary), fill in from status_map
    diffed_paths = {f.path for f in files}
    for path, status in status_map.items():
        if path not in diffed_paths:
            files.append(FileDiff(path=path, status=status))

    return files


def get_log(repo: str, topic: str, base: str) -> list[dict]:
    """Return commit log between base and topic."""
    out = _run(
        ["git", "log", "--format=%H%n%an%n%aI%n%s%n---", f"{base}..{topic}"],
        repo,
    )
    commits = []
    lines = out.strip().split("\n")
    i = 0
    while i < len(lines):
        if i + 3 >= len(lines):
            break
        sha, author, date, subject = lines[i], lines[i + 1], lines[i + 2], lines[i + 3]
        commits.append(
            {"sha": sha, "author": author, "date": date, "subject": subject}
        )
        i += 5  # skip the '---' separator
    return commits


def get_diff_stats(repo: str, topic: str, base: str) -> tuple[int, int, int]:
    """Return (files_changed, insertions, deletions)."""
    out = _run(["git", "diff", "--shortstat", f"{base}..{topic}"], repo)
    files = ins = dels = 0
    m = re.search(r"(\d+) file", out)
    if m:
        files = int(m.group(1))
    m = re.search(r"(\d+) insertion", out)
    if m:
        ins = int(m.group(1))
    m = re.search(r"(\d+) deletion", out)
    if m:
        dels = int(m.group(1))
    return files, ins, dels


# --- Git Notes ---

NOTES_REF = "refs/notes/pyre-review"


def _resolve_topic_head(repo: str, topic: str) -> str:
    """Resolve topic branch to its HEAD commit SHA."""
    out = _run(["git", "rev-parse", topic], repo)
    return out.strip()


def read_notes(repo: str, topic: str) -> list[dict]:
    """Read review notes for topic branch HEAD."""
    sha = _resolve_topic_head(repo, topic)
    out = _run(["git", "notes", "--ref", NOTES_REF, "show", sha], repo)
    if not out.strip():
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def write_notes(repo: str, topic: str, data: list[dict]) -> None:
    """Write review notes for topic branch HEAD."""
    sha = _resolve_topic_head(repo, topic)
    payload = json.dumps(data, indent=2)

    # Try to add first; if note exists, use overwrite flag
    result = subprocess.run(
        ["git", "notes", "--ref", NOTES_REF, "add", "-f", "-m", payload, sha],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to write git notes: {result.stderr}")


def generate_comment_id() -> str:
    """Generate a unique comment ID."""
    import secrets
    return "r_" + secrets.token_hex(8)


def get_author() -> str:
    """Get author name from BR_ACTOR env or git config."""
    author = os.environ.get("BR_ACTOR")
    if author:
        return author
    result = subprocess.run(
        ["git", "config", "user.name"], capture_output=True, text=True
    )
    return result.stdout.strip() or "anonymous"
