"""CLI entry point for pyre-review."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from . import git_ops
from .generate import generate_html
from .server import run_server


def _find_repo(path: str | None) -> str:
    """Find the git repo root from a path or cwd."""
    start = path or os.getcwd()
    d = os.path.abspath(start)
    while d != "/":
        if os.path.exists(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    print("error: not inside a git repository", file=sys.stderr)
    sys.exit(1)


def cmd_review(args):
    """Open browser review UI."""
    repo = _find_repo(args.repo)
    topic = args.topic
    base = args.base

    print(f"Generating review: {topic} → {base}")
    files = git_ops.get_diff_files(repo, topic, base)
    if not files:
        print("No changes between branches.")
        sys.exit(0)

    comments = git_ops.read_notes(repo, topic)
    commits = git_ops.get_log(repo, topic, base)
    stats = git_ops.get_diff_stats(repo, topic, base)

    # Pass beads config to server so verdict can create/update beads
    bead_config = None
    if getattr(args, "review_bead", None):
        bead_config = {
            "review_bead": args.review_bead,
            "bead_tool": getattr(args, "bead_tool", "br"),
            "assignee": getattr(args, "assignee", "coder"),
        }
    elif getattr(args, "new_review_bead", False):
        bead_config = {
            "new_review_bead": True,
            "bead_tool": getattr(args, "bead_tool", "br"),
            "assignee": getattr(args, "assignee", "coder"),
        }

    html = generate_html(
        files, comments, topic, base, commits, stats,
        bead_config=bead_config,
    )

    if args.static:
        out_path = args.static
        with open(out_path, "w") as f:
            f.write(html)
        print(f"Static review written to {out_path}")
    else:
        run_server(
            html, repo, topic, base=base,
            port=args.port,
            bead_config=bead_config,
        )


def cmd_comments(args):
    """Dump comments as JSON."""
    repo = _find_repo(args.repo)
    notes = git_ops.read_notes(repo, args.topic)
    comments = [n for n in notes if n.get("type") == "comment"]
    if args.unresolved:
        comments = [c for c in comments if not c.get("resolved")]
    json.dump(comments, sys.stdout, indent=2)
    print()


def cmd_resolve(args):
    """Resolve a comment by ID."""
    repo = _find_repo(args.repo)
    notes = git_ops.read_notes(repo, args.topic)
    found = False
    for note in notes:
        if note.get("id") == args.comment_id:
            note["resolved"] = True
            note["resolved_by"] = git_ops.get_author()
            note["resolved_at"] = datetime.now(timezone.utc).isoformat()
            found = True
            break
    if not found:
        print(f"error: comment {args.comment_id} not found", file=sys.stderr)
        sys.exit(1)
    git_ops.write_notes(repo, args.topic, notes)
    print(f"Resolved {args.comment_id}")


def cmd_add_comment(args):
    """Add a comment programmatically."""
    repo = _find_repo(args.repo)
    notes = git_ops.read_notes(repo, args.topic)
    version = max((n.get("version", 0) for n in notes), default=0) + 1
    comment = {
        "id": git_ops.generate_comment_id(),
        "version": version,
        "type": "comment",
        "author": args.author or git_ops.get_author(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file": args.file,
        "line": args.line,
        "side": args.side,
        "body": args.body,
        "resolved": False,
        "resolved_by": None,
        "resolved_at": None,
    }
    notes.append(comment)
    git_ops.write_notes(repo, args.topic, notes)
    print(json.dumps(comment, indent=2))


def cmd_request(args):
    """Request a review by creating a bead."""
    from .beads import create_review_request
    create_review_request(
        args.topic,
        args.base,
        tool=args.bead_tool,
        assignee=args.assignee,
        repo_flag=args.repo or "",
        db=getattr(args, "bead_db", None),
        priority=args.priority,
    )


def main():
    # Manual dispatch: check if first non-flag arg is a known subcommand
    subcommands = {"comments", "resolve", "add-comment", "request"}
    argv = sys.argv[1:]
    first_positional = None
    skip_next = False
    for a in argv:
        if skip_next:
            skip_next = False
            continue
        if a in ("--repo", "-C"):
            skip_next = True
            continue
        if a.startswith("-"):
            continue
        first_positional = a
        break

    if first_positional in subcommands:
        _dispatch_subcommand(argv)
    else:
        _dispatch_review(argv)


def _dispatch_subcommand(argv):
    parser = argparse.ArgumentParser(prog="pyre-review")
    parser.add_argument("--repo", "-C", help="Path to git repository")
    sub = parser.add_subparsers(dest="command")

    p_comments = sub.add_parser("comments", help="Dump review comments as JSON")
    p_comments.add_argument("topic", help="Topic branch name")
    p_comments.add_argument("--unresolved", action="store_true")

    p_resolve = sub.add_parser("resolve", help="Resolve a comment by ID")
    p_resolve.add_argument("topic", help="Topic branch name")
    p_resolve.add_argument("comment_id", help="Comment ID to resolve")

    p_add = sub.add_parser("add-comment", help="Add a comment programmatically")
    p_add.add_argument("topic", help="Topic branch name")
    p_add.add_argument("--file", required=True)
    p_add.add_argument("--line", type=int, required=True)
    p_add.add_argument("--body", required=True)
    p_add.add_argument("--side", default="right", choices=["left", "right"])
    p_add.add_argument("--author", help="Comment author (default: git user or BR_ACTOR)")

    p_request = sub.add_parser("request", help="Request a review (creates a bead)")
    p_request.add_argument("topic", help="Topic branch to review")
    p_request.add_argument("base", help="Base branch to diff against")
    p_request.add_argument("--bead-tool", default="br", choices=["br", "bd"],
                           help="Bead tool to use (default: br)")
    p_request.add_argument("--assignee", default="human-review",
                           help="Who to assign the review to (default: human-review)")
    p_request.add_argument("--priority", "-p", type=int, default=1,
                           help="Bead priority 0-4 (default: 1)")
    p_request.add_argument("--bead-db", help="Beads database path")

    args = parser.parse_args(argv)
    if args.command == "comments":
        cmd_comments(args)
    elif args.command == "resolve":
        cmd_resolve(args)
    elif args.command == "add-comment":
        cmd_add_comment(args)
    elif args.command == "request":
        cmd_request(args)


def _dispatch_review(argv):
    parser = argparse.ArgumentParser(
        prog="pyre-review",
        description="Lightweight local code review tool for topic branches",
    )
    parser.add_argument("topic", help="Topic branch to review")
    parser.add_argument("base", help="Base branch to diff against")
    parser.add_argument("--repo", "-C", help="Path to git repository")
    parser.add_argument("--static", help="Write static HTML to file instead of server")
    parser.add_argument("--port", type=int, default=0, help="Server port (0=auto)")
    # Beads integration
    parser.add_argument("--review-bead", metavar="BEAD_ID",
                        help="Link this review to an existing bead (updates on verdict)")
    parser.add_argument("--new-review-bead", action="store_true",
                        help="Create a new bead on verdict (one-shot review)")
    parser.add_argument("--bead-tool", default="br", choices=["br", "bd"],
                        help="Bead tool to use (default: br)")
    parser.add_argument("--assignee", default="coder",
                        help="Who to assign the bead to on verdict (default: coder)")
    args = parser.parse_args(argv)
    cmd_review(args)


if __name__ == "__main__":
    main()
