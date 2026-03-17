"""Tests for git_ops module."""

import json

from pyre_review import git_ops


class TestGetChangedFiles:
    def test_lists_modified_and_added(self, tmp_repo):
        files = git_ops.get_changed_files(tmp_repo, "topic/test-review", "main")
        status_map = {path: status for status, path in files}
        assert status_map["hello.py"] == "M"
        assert status_map["utils.py"] == "A"
        assert "README.md" not in status_map

    def test_empty_diff(self, tmp_repo):
        files = git_ops.get_changed_files(tmp_repo, "main", "main")
        assert files == []


class TestGetDiffFiles:
    def test_parses_modified_file(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        by_path = {f.path: f for f in files}

        hello = by_path["hello.py"]
        assert hello.status == "M"
        assert hello.additions > 0
        # Should have full file content (context + added + deleted lines)
        assert len(hello.lines) > 0
        line_types = {dl.type for dl in hello.lines}
        assert "context" in line_types
        assert "added" in line_types

    def test_parses_added_file(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        by_path = {f.path: f for f in files}

        utils = by_path["utils.py"]
        assert utils.status == "A"
        # All non-empty lines should be 'added' (trailing empty context is OK)
        for dl in utils.lines:
            if dl.content.strip():
                assert dl.type == "added"
        assert utils.additions > 0

    def test_line_numbers_are_sequential(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        for fd in files:
            prev_old = 0
            prev_new = 0
            for dl in fd.lines:
                if dl.old_lineno is not None:
                    assert dl.old_lineno >= prev_old
                    prev_old = dl.old_lineno
                if dl.new_lineno is not None:
                    assert dl.new_lineno >= prev_new
                    prev_new = dl.new_lineno

    def test_no_duplicate_files(self, tmp_repo):
        files = git_ops.get_diff_files(tmp_repo, "topic/test-review", "main")
        paths = [f.path for f in files]
        assert len(paths) == len(set(paths))


class TestGetLog:
    def test_returns_commits(self, tmp_repo):
        commits = git_ops.get_log(tmp_repo, "topic/test-review", "main")
        assert len(commits) == 2
        subjects = [c["subject"] for c in commits]
        assert "Add reverse_string" in subjects
        assert "Add farewell and utils" in subjects

    def test_commit_fields(self, tmp_repo):
        commits = git_ops.get_log(tmp_repo, "topic/test-review", "main")
        for c in commits:
            assert len(c["sha"]) == 40
            assert c["author"] == "Test User"
            assert c["date"]  # ISO format date


class TestGetDiffStats:
    def test_returns_stats(self, tmp_repo):
        files, ins, dels = git_ops.get_diff_stats(tmp_repo, "topic/test-review", "main")
        assert files == 2
        assert ins > 0


class TestNotes:
    def test_read_empty_notes(self, tmp_repo):
        notes = git_ops.read_notes(tmp_repo, "topic/test-review")
        assert notes == []

    def test_write_and_read_notes(self, tmp_repo):
        data = [
            {"id": "r_test1", "type": "comment", "body": "Test comment"},
        ]
        git_ops.write_notes(tmp_repo, "topic/test-review", data)
        result = git_ops.read_notes(tmp_repo, "topic/test-review")
        assert len(result) == 1
        assert result[0]["id"] == "r_test1"

    def test_overwrite_notes(self, tmp_repo):
        data1 = [{"id": "r_1", "body": "first"}]
        git_ops.write_notes(tmp_repo, "topic/test-review", data1)

        data2 = [{"id": "r_1", "body": "first"}, {"id": "r_2", "body": "second"}]
        git_ops.write_notes(tmp_repo, "topic/test-review", data2)

        result = git_ops.read_notes(tmp_repo, "topic/test-review")
        assert len(result) == 2


class TestGenerateCommentId:
    def test_has_prefix(self):
        cid = git_ops.generate_comment_id()
        assert cid.startswith("r_")

    def test_unique(self):
        ids = {git_ops.generate_comment_id() for _ in range(100)}
        assert len(ids) == 100


class TestGetAuthor:
    def test_uses_br_actor(self, monkeypatch):
        monkeypatch.setenv("BR_ACTOR", "test-agent")
        assert git_ops.get_author() == "test-agent"

    def test_falls_back_to_git_config(self, monkeypatch):
        monkeypatch.delenv("BR_ACTOR", raising=False)
        author = git_ops.get_author()
        assert isinstance(author, str)
        assert len(author) > 0
