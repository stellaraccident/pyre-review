"""Tests for beads integration.

These tests mock the br/bd commands since we can't assume beads is installed
in the test environment.
"""

from unittest.mock import patch, MagicMock

from pyre_review.beads import (
    create_review_request,
    create_verdict_bead,
    update_with_verdict,
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
            tool="br", assignee="human-review",
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
        assert create_args[idx + 1] == "human-review"

    @patch("pyre_review.beads._run_bead_cmd")
    def test_default_assignee_is_human_review(self, mock_cmd):
        mock_cmd.return_value = "bead_010"
        create_review_request("topic/test", "main", tool="br")
        create_args = mock_cmd.call_args_list[0][0][1]
        idx = create_args.index("--assignee")
        assert create_args[idx + 1] == "human-review"

    @patch("pyre_review.beads._run_bead_cmd")
    def test_includes_review_command_in_description(self, mock_cmd):
        mock_cmd.return_value = "bead_002"
        create_review_request(
            "topic/test", "main",
            tool="br", assignee="human-review",
        )
        # Second call: update description with actual bead ID
        update_call = mock_cmd.call_args_list[1]
        args = update_call[0][1]
        assert "update" in args
        assert "bead_002" in args
        desc_idx = args.index("--description")
        desc = args[desc_idx + 1]
        assert "pyre-review" in desc
        assert "--review-bead bead_002" in desc


class TestUpdateWithVerdict:
    @patch("pyre_review.beads._run_bead_cmd")
    def test_approve(self, mock_cmd):
        mock_cmd.return_value = ""
        result = update_with_verdict(
            review_bead_id="bead_001",
            verdict="approve",
            comments=[],
            summary="LGTM",
            topic="topic/foo",
            base="main",
            tool="br",
            assignee="coder",
        )
        assert result.bead_id == "bead_001"  # same bead, not a new one
        assert "approved" in result.title
        assert "topic/foo" in result.title

        # Single update call — no create, no dep add
        assert mock_cmd.call_count == 1
        update_args = mock_cmd.call_args_list[0][0][1]
        assert update_args[0] == "update"
        assert update_args[1] == "bead_001"
        assert "--assignee" in update_args
        idx = update_args.index("--assignee")
        assert update_args[idx + 1] == "coder"

    @patch("pyre_review.beads._run_bead_cmd")
    def test_request_changes_with_comments(self, mock_cmd):
        mock_cmd.return_value = ""
        comments = [
            {"type": "comment", "file": "foo.py", "line": 10,
             "body": "Fix this", "resolved": False},
            {"type": "comment", "file": "bar.py", "line": 20,
             "body": "And this", "resolved": False},
            {"type": "comment", "file": "baz.py", "line": 5,
             "body": "Already fixed", "resolved": True},
        ]
        result = update_with_verdict(
            review_bead_id="bead_001",
            verdict="request-changes",
            comments=comments,
            topic="topic/foo",
            base="main",
            tool="br",
        )
        assert "changes requested" in result.title

        update_args = mock_cmd.call_args_list[0][0][1]
        desc_idx = update_args.index("--description")
        desc = update_args[desc_idx + 1]
        assert "2" in desc  # 2 unresolved
        assert "foo.py:10" in desc
        assert "bar.py:20" in desc
        assert "baz.py" not in desc  # resolved, not listed

    @patch("pyre_review.beads._run_bead_cmd")
    def test_assignee_passed(self, mock_cmd):
        mock_cmd.return_value = ""
        update_with_verdict(
            review_bead_id="bead_001",
            verdict="approve",
            comments=[],
            assignee="coder",
            tool="br",
        )
        update_args = mock_cmd.call_args_list[0][0][1]
        idx = update_args.index("--assignee")
        assert update_args[idx + 1] == "coder"

    @patch("pyre_review.beads._run_bead_cmd")
    def test_no_parent_or_dep(self, mock_cmd):
        """Verify single-bead pattern: no --parent, no dep add."""
        mock_cmd.return_value = ""
        update_with_verdict(
            review_bead_id="bead_001",
            verdict="approve",
            comments=[],
            tool="br",
        )
        assert mock_cmd.call_count == 1
        args = mock_cmd.call_args_list[0][0][1]
        assert "--parent" not in args
        assert "dep" not in args

    @patch("pyre_review.beads._run_bead_cmd")
    def test_includes_topic_and_base(self, mock_cmd):
        mock_cmd.return_value = ""
        update_with_verdict(
            review_bead_id="bead_001",
            verdict="approve",
            comments=[],
            topic="topic/phase0-kernels",
            base="main",
            tool="br",
        )
        update_args = mock_cmd.call_args_list[0][0][1]
        desc_idx = update_args.index("--description")
        desc = update_args[desc_idx + 1]
        assert "topic/phase0-kernels" in desc
        assert "main" in desc


class TestCreateVerdictBead:
    @patch("pyre_review.beads._run_bead_cmd")
    def test_approve_creates_bead(self, mock_cmd):
        mock_cmd.return_value = "bead_new_001"
        result = create_verdict_bead(
            verdict="approve",
            comments=[],
            summary="LGTM",
            topic="topic/foo",
            base="main",
            tool="br",
            assignee="coder",
        )
        assert result.bead_id == "bead_new_001"
        assert "approved" in result.title
        assert "topic/foo" in result.title

        # Single create call
        assert mock_cmd.call_count == 1
        create_args = mock_cmd.call_args_list[0][0][1]
        assert "create" in create_args
        idx = create_args.index("--assignee")
        assert create_args[idx + 1] == "coder"

    @patch("pyre_review.beads._run_bead_cmd")
    def test_request_changes_with_comments(self, mock_cmd):
        mock_cmd.return_value = "bead_new_002"
        comments = [
            {"type": "comment", "file": "foo.py", "line": 10,
             "body": "Fix this", "resolved": False},
            {"type": "comment", "file": "bar.py", "line": 20,
             "body": "Already fixed", "resolved": True},
        ]
        result = create_verdict_bead(
            verdict="request-changes",
            comments=comments,
            topic="topic/bar",
            base="main",
            tool="br",
        )
        assert "changes requested" in result.title

        create_args = mock_cmd.call_args_list[0][0][1]
        desc_idx = create_args.index("--description")
        desc = create_args[desc_idx + 1]
        assert "foo.py:10" in desc
        assert "bar.py" not in desc  # resolved, not listed

    @patch("pyre_review.beads._run_bead_cmd")
    def test_priority_passed(self, mock_cmd):
        mock_cmd.return_value = "bead_new_003"
        create_verdict_bead(
            verdict="approve",
            comments=[],
            topic="topic/baz",
            base="main",
            tool="br",
            priority=2,
        )
        create_args = mock_cmd.call_args_list[0][0][1]
        idx = create_args.index("-p")
        assert create_args[idx + 1] == "2"
