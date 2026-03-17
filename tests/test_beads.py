"""Tests for beads integration.

These tests mock the br/bd commands since we can't assume beads is installed
in the test environment.
"""

import json
from unittest.mock import patch, MagicMock

from pyre_review.beads import (
    create_review_request,
    create_review_response,
    _run_bead_cmd,
)


class TestRunBeadCmd:
    def test_runs_command(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n", stderr="")
            result = _run_bead_cmd("br", ["create", "--title", "Test"])
            mock_run.assert_called_once()
            assert result == "abc123"

    def test_passes_db_flag(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            _run_bead_cmd("br", ["list"], db="/path/to/db")
            cmd = mock_run.call_args[0][0]
            assert "--db" in cmd
            assert "/path/to/db" in cmd


class TestCreateReviewRequest:
    @patch("pyre_review.beads._run_bead_cmd")
    def test_creates_bead(self, mock_cmd):
        mock_cmd.return_value = "bead_001"
        result = create_review_request(
            "topic/phase0-kernels", "main",
            tool="br", assignee="reviewer",
        )
        assert result.bead_id == "bead_001"
        assert result.title == "Review: topic/phase0-kernels → main"
        assert result.tool == "br"

        # First call: create
        create_call = mock_cmd.call_args_list[0]
        args = create_call[0]
        assert args[0] == "br"
        create_args = args[1]
        assert "create" in create_args
        assert "--assignee" in create_args
        idx = create_args.index("--assignee")
        assert create_args[idx + 1] == "reviewer"

    @patch("pyre_review.beads._run_bead_cmd")
    def test_includes_review_command_in_description(self, mock_cmd):
        mock_cmd.return_value = "bead_002"
        create_review_request(
            "topic/test", "main",
            tool="br", assignee="reviewer",
        )
        # Second call: update description with actual bead ID
        update_call = mock_cmd.call_args_list[1]
        args = update_call[0][1]
        assert "update" in args
        assert "bead_002" in args
        # Description should contain the review command
        desc_idx = args.index("--description")
        desc = args[desc_idx + 1]
        assert "pyre-review" in desc
        assert "--review-bead bead_002" in desc


class TestCreateReviewResponse:
    @patch("pyre_review.beads._run_bead_cmd")
    def test_approve(self, mock_cmd):
        mock_cmd.return_value = "resp_001"
        result = create_review_response(
            review_bead_id="bead_001",
            verdict="approve",
            comments=[],
            summary="LGTM",
            tool="br",
            assignee="coder",
        )
        assert result.bead_id == "resp_001"
        assert result.title == "Code review: approved"

        # Should create the bead then add dependency
        assert mock_cmd.call_count == 2
        # First call: create
        create_args = mock_cmd.call_args_list[0][0][1]
        assert "create" in create_args
        assert "--parent" in create_args
        parent_idx = create_args.index("--parent")
        assert create_args[parent_idx + 1] == "bead_001"
        # Second call: dep add
        dep_args = mock_cmd.call_args_list[1][0][1]
        assert dep_args[:2] == ["dep", "add"]
        assert "bead_001" in dep_args
        assert "resp_001" in dep_args

    @patch("pyre_review.beads._run_bead_cmd")
    def test_request_changes_with_comments(self, mock_cmd):
        mock_cmd.return_value = "resp_002"
        comments = [
            {"type": "comment", "file": "foo.py", "line": 10,
             "body": "Fix this", "resolved": False},
            {"type": "comment", "file": "bar.py", "line": 20,
             "body": "And this", "resolved": False},
            {"type": "comment", "file": "baz.py", "line": 5,
             "body": "Already fixed", "resolved": True},
        ]
        result = create_review_response(
            review_bead_id="bead_001",
            verdict="request-changes",
            comments=comments,
            tool="br",
        )
        assert result.title == "Code review: changes requested"

        # Description should list unresolved comments
        create_args = mock_cmd.call_args_list[0][0][1]
        desc_idx = create_args.index("--description")
        desc = create_args[desc_idx + 1]
        assert "2 unresolved" in desc
        assert "foo.py:10" in desc
        assert "bar.py:20" in desc
        assert "baz.py" not in desc  # resolved, not listed

    @patch("pyre_review.beads._run_bead_cmd")
    def test_assignee_passed(self, mock_cmd):
        mock_cmd.return_value = "resp_003"
        create_review_response(
            review_bead_id="bead_001",
            verdict="approve",
            comments=[],
            assignee="coder",
            tool="br",
        )
        create_args = mock_cmd.call_args_list[0][0][1]
        idx = create_args.index("--assignee")
        assert create_args[idx + 1] == "coder"
