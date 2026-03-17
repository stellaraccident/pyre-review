"""Beads integration for pyre-review.

Creates review-request and review-response beads so agents can participate
in the code review lifecycle via `br` (beads_rust) or `bd` (beads).

Workflow:
  1. Coder finishes work, requests review:
       pyre-review request <topic> <base> --bead-tool br --assignee reviewer

     Creates a bead: "Review: <topic> → <base>" assigned to reviewer,
     with the command to run in the description.

  2. Reviewer runs the review command (from bead description):
       pyre-review <topic> <base> --review-bead <id> --bead-tool br --assignee coder

  3. On verdict, pyre-review creates a response bead blocking the request:
       - "Code review: approved"
       - "Code review: changes requested"
       - "Code review: comments"
     Assigned to the coder, so `br ready` surfaces it.
"""

import json
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
    assignee: str = "reviewer",
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


def create_review_response(
    review_bead_id: str,
    verdict: str,
    comments: list[dict],
    summary: str = "",
    *,
    tool: str = "br",
    assignee: str = "coder",
    db: str | None = None,
) -> BeadResult:
    """Create a response bead after a review verdict.

    The response bead blocks the review-request bead and is assigned
    to the coder so it shows up in `br ready`.
    """
    if verdict == "approve":
        title = "Code review: approved"
        priority = 2
    elif verdict == "request-changes":
        title = "Code review: changes requested"
        priority = 1
    else:
        title = "Code review: comments"
        priority = 2

    # Build description from comments
    lines = []
    if summary:
        lines.append(summary)
        lines.append("")
    unresolved = [c for c in comments if c.get("type") == "comment" and not c.get("resolved")]
    if unresolved:
        lines.append(f"**{len(unresolved)} unresolved comment(s):**\n")
        for c in unresolved:
            file_loc = f"`{c['file']}:{c['line']}`" if c.get("file") else ""
            lines.append(f"- {file_loc} — {c['body']}")
    elif verdict == "approve":
        lines.append("No outstanding comments. Ready to merge.")

    description = "\n".join(lines)

    args = [
        "create",
        "--title", title,
        "--type", "task",
        "--description", description,
        "--assignee", assignee,
        "--parent", review_bead_id,
        "-p", str(priority),
        "--silent",
    ]
    response_id = _run_bead_cmd(tool, args, db=db)

    # The response bead blocks the review-request bead:
    # review_bead depends-on response (can't close review until response addressed)
    _run_bead_cmd(tool, ["dep", "add", review_bead_id, response_id], db=db)

    print(f"Review response: {response_id} ({title})")
    print(f"Assigned to: {assignee}")
    print(f"Blocks: {review_bead_id}")
    return BeadResult(bead_id=response_id, title=title, tool=tool)
