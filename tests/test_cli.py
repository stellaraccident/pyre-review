"""Tests for CLI dispatch and commands."""

import json
import os
import subprocess
import sys


def _run_cli(args, repo=None, env_extra=None):
    """Run pyre-review CLI as a subprocess."""
    script = os.path.join(os.path.dirname(__file__), "..", "pyre-review")
    cmd = [sys.executable, script] + args
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        cmd, capture_output=True, text=True, cwd=repo, env=env, check=False,
    )


class TestReviewCommand:
    def test_static_output(self, tmp_repo, tmp_path):
        out_file = str(tmp_path / "review.html")
        result = _run_cli(
            ["topic/test-review", "main", "--static", out_file],
            repo=tmp_repo,
        )
        assert result.returncode == 0
        assert "Generating review" in result.stdout
        assert os.path.exists(out_file)
        with open(out_file) as f:
            html = f.read()
        assert "<!DOCTYPE html>" in html

    def test_static_with_repo_flag(self, tmp_repo, tmp_path):
        out_file = str(tmp_path / "review2.html")
        result = _run_cli(
            ["-C", tmp_repo, "topic/test-review", "main", "--static", out_file],
        )
        assert result.returncode == 0
        assert os.path.exists(out_file)

    def test_no_changes(self, tmp_repo, tmp_path):
        out_file = str(tmp_path / "empty.html")
        result = _run_cli(
            ["main", "main", "--static", out_file],
            repo=tmp_repo,
        )
        assert result.returncode != 0 or "No changes" in result.stdout


class TestCommentsCommand:
    def test_empty_comments(self, tmp_repo):
        result = _run_cli(["comments", "topic/test-review"], repo=tmp_repo)
        assert result.returncode == 0
        assert json.loads(result.stdout) == []

    def test_comments_after_add(self, tmp_repo):
        # Add a comment first
        _run_cli([
            "add-comment", "topic/test-review",
            "--file", "hello.py", "--line", "3", "--body", "Test",
        ], repo=tmp_repo)

        result = _run_cli(["comments", "topic/test-review"], repo=tmp_repo)
        assert result.returncode == 0
        comments = json.loads(result.stdout)
        assert len(comments) == 1
        assert comments[0]["body"] == "Test"

    def test_unresolved_filter(self, tmp_repo):
        # Add and resolve a comment
        result = _run_cli([
            "add-comment", "topic/test-review",
            "--file", "hello.py", "--line", "1", "--body", "Will resolve",
        ], repo=tmp_repo)
        comment = json.loads(result.stdout)
        comment_id = comment["id"]

        _run_cli(["resolve", "topic/test-review", comment_id], repo=tmp_repo)

        # Add another unresolved comment
        _run_cli([
            "add-comment", "topic/test-review",
            "--file", "hello.py", "--line", "5", "--body", "Still open",
        ], repo=tmp_repo)

        # All comments
        result = _run_cli(["comments", "topic/test-review"], repo=tmp_repo)
        all_comments = json.loads(result.stdout)
        assert len(all_comments) == 2

        # Unresolved only
        result = _run_cli(
            ["comments", "topic/test-review", "--unresolved"], repo=tmp_repo,
        )
        unresolved = json.loads(result.stdout)
        assert len(unresolved) == 1
        assert unresolved[0]["body"] == "Still open"


class TestResolveCommand:
    def test_resolve_existing(self, tmp_repo):
        result = _run_cli([
            "add-comment", "topic/test-review",
            "--file", "hello.py", "--line", "1", "--body", "Fix this",
        ], repo=tmp_repo)
        comment_id = json.loads(result.stdout)["id"]

        result = _run_cli(["resolve", "topic/test-review", comment_id], repo=tmp_repo)
        assert result.returncode == 0
        assert f"Resolved {comment_id}" in result.stdout

    def test_resolve_nonexistent(self, tmp_repo):
        result = _run_cli(["resolve", "topic/test-review", "r_nonexistent"], repo=tmp_repo)
        assert result.returncode != 0
        assert "not found" in result.stderr


class TestAddCommentCommand:
    def test_add_comment(self, tmp_repo):
        result = _run_cli([
            "add-comment", "topic/test-review",
            "--file", "utils.py", "--line", "2",
            "--body", "Consider using title() instead",
        ], repo=tmp_repo)
        assert result.returncode == 0
        comment = json.loads(result.stdout)
        assert comment["file"] == "utils.py"
        assert comment["line"] == 2
        assert comment["side"] == "right"

    def test_add_comment_with_side(self, tmp_repo):
        result = _run_cli([
            "add-comment", "topic/test-review",
            "--file", "hello.py", "--line", "1",
            "--body", "Old code was better", "--side", "left",
        ], repo=tmp_repo)
        assert result.returncode == 0
        comment = json.loads(result.stdout)
        assert comment["side"] == "left"

    def test_add_comment_with_br_actor(self, tmp_repo):
        result = _run_cli([
            "add-comment", "topic/test-review",
            "--file", "hello.py", "--line", "1", "--body", "Agent note",
        ], repo=tmp_repo, env_extra={"BR_ACTOR": "coder-agent"})
        assert result.returncode == 0
        comment = json.loads(result.stdout)
        assert comment["author"] == "coder-agent"
