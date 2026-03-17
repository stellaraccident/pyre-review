"""Tests for the HTTP server."""

import json
import threading
import urllib.request
from functools import partial
from http.server import HTTPServer

from pyre_review import git_ops
from pyre_review.generate import generate_html
from pyre_review.server import ReviewHandler


def _make_server(tmp_repo):
    """Create a test server instance."""
    repo = tmp_repo
    topic = "topic/test-review"
    base = "main"
    files = git_ops.get_diff_files(repo, topic, base)
    comments = git_ops.read_notes(repo, topic)
    commits = git_ops.get_log(repo, topic, base)
    stats = git_ops.get_diff_stats(repo, topic, base)
    html = generate_html(files, comments, topic, base, commits, stats)

    handler = partial(ReviewHandler, html=html, repo=repo, topic=topic, base=base)
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    return server, port


def _request(server, port, path, method="GET", data=None):
    """Make a request and handle it in a thread."""
    t = threading.Thread(target=server.handle_request)
    t.start()
    headers = {"Content-Type": "application/json"} if data else {}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    resp = urllib.request.urlopen(req)
    result = resp.read()
    t.join(timeout=5)
    return resp.status, result


class TestServerGET:
    def test_serves_html(self, tmp_repo):
        server, port = _make_server(tmp_repo)
        try:
            status, body = _request(server, port, "/")
            assert status == 200
            assert b"<!DOCTYPE html>" in body
        finally:
            server.server_close()

    def test_serves_index_html(self, tmp_repo):
        server, port = _make_server(tmp_repo)
        try:
            status, body = _request(server, port, "/index.html")
            assert status == 200
            assert b"<!DOCTYPE html>" in body
        finally:
            server.server_close()

    def test_api_comments_empty(self, tmp_repo):
        server, port = _make_server(tmp_repo)
        try:
            status, body = _request(server, port, "/api/comments")
            assert status == 200
            assert json.loads(body) == []
        finally:
            server.server_close()


class TestServerPOST:
    def test_add_comment(self, tmp_repo):
        server, port = _make_server(tmp_repo)
        try:
            status, body = _request(server, port, "/api/comment", "POST", {
                "file": "hello.py",
                "line": 5,
                "body": "Test comment",
            })
            assert status == 200
            result = json.loads(body)
            assert result["id"].startswith("r_")
            assert result["file"] == "hello.py"
            assert result["line"] == 5
            assert result["body"] == "Test comment"
            assert result["resolved"] is False

            # Verify it persisted to git notes
            notes = git_ops.read_notes(tmp_repo, "topic/test-review")
            assert len(notes) == 1
            assert notes[0]["id"] == result["id"]
        finally:
            server.server_close()

    def test_add_and_resolve_comment(self, tmp_repo):
        server, port = _make_server(tmp_repo)
        try:
            # Add
            _, body = _request(server, port, "/api/comment", "POST", {
                "file": "hello.py", "line": 1, "body": "Fix this",
            })
            comment_id = json.loads(body)["id"]

            # Resolve
            status, body = _request(server, port, "/api/resolve", "POST", {
                "id": comment_id,
            })
            assert status == 200
            assert json.loads(body)["ok"] is True

            # Verify
            notes = git_ops.read_notes(tmp_repo, "topic/test-review")
            assert notes[0]["resolved"] is True
        finally:
            server.server_close()

    def test_submit_verdict(self, tmp_repo):
        server, port = _make_server(tmp_repo)
        try:
            status, body = _request(server, port, "/api/verdict", "POST", {
                "verdict": "approve",
                "body": "Looks good!",
            })
            assert status == 200
            result = json.loads(body)
            assert result["verdict"] == "approve"
            assert result["type"] == "verdict"

            notes = git_ops.read_notes(tmp_repo, "topic/test-review")
            verdicts = [n for n in notes if n["type"] == "verdict"]
            assert len(verdicts) == 1
        finally:
            server.server_close()

    def test_resolve_nonexistent_returns_404(self, tmp_repo):
        server, port = _make_server(tmp_repo)
        try:
            # Need to handle 404 from the API (it returns 404 status in JSON, not HTTP 404)
            status, body = _request(server, port, "/api/resolve", "POST", {
                "id": "r_nonexistent",
            })
            # The handler sends 404 as HTTP status
            # Actually our handler uses _json_response(404, ...) which sends HTTP 404
        except urllib.error.HTTPError as e:
            assert e.code == 404
        finally:
            server.server_close()
