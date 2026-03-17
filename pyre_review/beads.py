"""Beads integration for pyre-review.

Single-bead lifecycle for human code review:

  1. Agent finishes work, requests human review:
       pyre-review request <topic> <base>
     Creates a bead assigned to @human-review with the review command
     in the description.

  2. Human runs /human-review to see the queue, picks a review,
     runs the pyre-review command from the bead description.

  3. On verdict, pyre-review updates the SAME bead:
     - Title updated to "Review result: approved (topic/foo)"
     - Description replaced with full review results
     - Assignee changed to @coder
     The coder picks it up via `br ready`, addresses comments,
     then closes the bead when done.
"""

import subprocess
import sys
from dataclasses import dataclass


@dataclass
class BeadResult:
    bead_id: str
    title: str
    tool: str


def _run_bead_cmd(tool: str, args: list[str], db: str | None = None) -> str:
    """Run a br/bd command and return stdout."""
    cmd = [tool] + args
    if db:
        cmd.extend(["--db", db])
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"error: {tool} command failed: {' '.join(cmd)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def create_review_request(
    topic: str,
    base: str,
    *,
    tool: str = "br",
    assignee: str = "human-review",
    repo_flag: str = "",
    db: str | None = None,
    priority: int = 1,
) -> BeadResult:
    """Create a bead requesting review of a topic branch.

    Returns the created bead's ID so callers can reference it.
    """
    title = f"Review: {topic} → {base}"

    # Build the review command the reviewer should run
    repo_arg = f" -C {repo_flag}" if repo_flag else ""
    review_cmd = (
        f"pyre-review{repo_arg} {topic} {base}"
        f" --review-bead {{this_bead_id}} --bead-tool {tool}"
        f" --assignee coder"
    )

    description = (
        f"**Code review requested**\n\n"
        f"Topic: `{topic}`\n"
        f"Base: `{base}`\n\n"
        f"Run this command to review:\n"
        f"```\n{review_cmd}\n```"
    )

    args = [
        "create",
        "--title", title,
        "--type", "task",
        "--description", description,
        "--assignee", assignee,
        "-p", str(priority),
        "--silent",
    ]
    bead_id = _run_bead_cmd(tool, args, db=db)

    # Patch the description to include the actual bead ID
    description = description.replace("{this_bead_id}", bead_id)
    _run_bead_cmd(
        tool,
        ["update", bead_id, "--description", description],
        db=db,
    )

    print(f"Review requested: {bead_id} ({title})")
    print(f"Assigned to: {assignee}")
    return BeadResult(bead_id=bead_id, title=title, tool=tool)


def update_with_verdict(
    review_bead_id: str,
    verdict: str,
    comments: list[dict],
    summary: str = "",
    *,
    topic: str = "",
    base: str = "",
    tool: str = "br",
    assignee: str = "coder",
    db: str | None = None,
) -> BeadResult:
    """Update the review bead with verdict results and reassign to coder.

    Updates title, description, and assignee on the existing bead.
    The coder picks it up via `br ready` and closes it when done.
    """
    if verdict == "approve":
        verdict_label = "approved"
    elif verdict == "request-changes":
        verdict_label = "changes requested"
    else:
        verdict_label = "comments"

    title = f"Review result: {verdict_label} ({topic})"

    # Build description with full review results
    lines = [f"**Review: {verdict_label}**\n"]
    if topic:
        lines.append(f"Topic: `{topic}`  Base: `{base}`\n")
    if summary:
        lines.append(f"## Summary\n{summary}\n")

    unresolved = [
        c for c in comments
        if c.get("type") == "comment" and not c.get("resolved")
    ]
    if unresolved:
        lines.append(f"## Unresolved comments ({len(unresolved)})\n")
        for c in unresolved:
            file_loc = f"`{c['file']}:{c['line']}`" if c.get("file") else ""
            lines.append(f"- {file_loc} — {c['body']}")
    elif verdict == "approve":
        lines.append("No outstanding comments. Ready to merge.")

    description = "\n".join(lines)

    _run_bead_cmd(
        tool,
        [
            "update", review_bead_id,
            "--title", title,
            "--description", description,
            "--assignee", assignee,
        ],
        db=db,
    )

    print(f"Review updated: {review_bead_id} → {verdict_label}")
    print(f"Reassigned to: {assignee}")
    return BeadResult(bead_id=review_bead_id, title=title, tool=tool)
