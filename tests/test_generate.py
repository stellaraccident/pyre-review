"""Tests for HTML generation."""

import json
import re

from pyre_review import git_ops
from pyre_review.generate import generate_html


class TestGenerateHtml:
    def test_produces_valid_html(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        comments = []
        commits = git_ops.get_log(tmp_repo, "topic/test-review", "main")
        stats = git_ops.get_diff_stats(tmp_repo, "topic/test-review", "main")
        html = generate_html(files, comments, "topic/test-review", "main", commits, stats)

        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "topic/test-review" in html

    def test_embeds_valid_json_data(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        comments = []
        commits = git_ops.get_log(tmp_repo, "topic/test-review", "main")
        stats = git_ops.get_diff_stats(tmp_repo, "topic/test-review", "main")
        html = generate_html(files, comments, "topic/test-review", "main", commits, stats)

        # Extract and parse the embedded JSON
        idx = html.find("const DATA = ")
        end = html.find(";\n\nlet currentFileIdx")
        assert idx > 0
        assert end > idx
        data = json.loads(html[idx + len("const DATA = "):end])

        assert data["topic"] == "topic/test-review"
        assert data["base"] == "main"
        assert len(data["files"]) == 2
        assert data["stats"]["files"] == 2

    def test_includes_pygments_css(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        html = generate_html(files, [], "topic/test-review", "main", [], (2, 10, 2))
        # Pygments generates class-based CSS
        assert ".hl-" in html

    def test_syntax_highlights_python(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        html = generate_html(files, [], "topic/test-review", "main", [], (2, 10, 2))
        # Extract data and check for highlighted tokens
        idx = html.find("const DATA = ")
        end = html.find(";\n\nlet currentFileIdx")
        data = json.loads(html[idx + len("const DATA = "):end])
        hello = next(f for f in data["files"] if f["path"] == "hello.py")
        # At least some lines should have <span> tags from pygments
        html_lines = [l["html"] for l in hello["lines"]]
        has_spans = any("<span" in h for h in html_lines)
        assert has_spans

    def test_includes_comments(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        comments = [
            {
                "id": "r_test1",
                "type": "comment",
                "author": "tester",
                "timestamp": "2026-01-01T00:00:00Z",
                "file": "hello.py",
                "line": 3,
                "body": "Why not use a constant?",
                "resolved": False,
            }
        ]
        html = generate_html(files, comments, "topic/test-review", "main", [], (2, 10, 2))
        idx = html.find("const DATA = ")
        end = html.find(";\n\nlet currentFileIdx")
        data = json.loads(html[idx + len("const DATA = "):end])
        hello = next(f for f in data["files"] if f["path"] == "hello.py")
        assert len(hello["comments"]) == 1
        assert hello["comments"][0]["body"] == "Why not use a constant?"

    def test_bead_config_embedded(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        bead_config = {"review_bead": "abc123", "bead_tool": "br", "assignee": "coder"}
        html = generate_html(
            files, [], "topic/test-review", "main", [], (2, 10, 2),
            bead_config=bead_config,
        )
        idx = html.find("const DATA = ")
        end = html.find(";\n\nlet currentFileIdx")
        data = json.loads(html[idx + len("const DATA = "):end])
        assert data["bead_config"]["review_bead"] == "abc123"

    def test_no_bead_config_when_not_set(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        html = generate_html(files, [], "topic/test-review", "main", [], (2, 10, 2))
        idx = html.find("const DATA = ")
        end = html.find(";\n\nlet currentFileIdx")
        data = json.loads(html[idx + len("const DATA = "):end])
        assert data["bead_config"] is None
