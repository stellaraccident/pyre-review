"""Tiny HTTP server for pyre-review. Serves the review UI and handles comment/verdict POSTs."""

import json
import sys
from datetime import datetime, timezone
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler

from . import git_ops


class ReviewHandler(BaseHTTPRequestHandler):
    """Handles GET for the review page and POST for comments/verdicts."""

    def __init__(self, *args, html: str, repo: str, topic: str, base: str = "",
                 bead_config: dict | None = None, **kwargs):
        self.html = html
        self.repo = repo
        self.topic = topic
        self.base = base
        self.bead_config = bead_config
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.html.encode("utf-8"))
        elif self.path == "/api/comments":
            notes = git_ops.read_notes(self.repo, self.topic)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(notes).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/api/comment":
            self._handle_add_comment(body)
        elif self.path == "/api/verdict":
            self._handle_verdict(body)
        elif self.path == "/api/resolve":
            self._handle_resolve(body)
        else:
            self.send_error(404)

    def _handle_add_comment(self, body: dict):
        notes = git_ops.read_notes(self.repo, self.topic)
        version = max((n.get("version", 0) for n in notes), default=0) + 1
        comment = {
            "id": git_ops.generate_comment_id(),
            "version": version,
            "type": "comment",
            "author": body.get("author", git_ops.get_author()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file": body["file"],
            "line": body["line"],
            "side": body.get("side", "right"),
            "body": body["body"],
            "resolved": False,
            "resolved_by": None,
            "resolved_at": None,
        }
        notes.append(comment)
        git_ops.write_notes(self.repo, self.topic, notes)
        self._json_response(200, comment)

    def _handle_verdict(self, body: dict):
        notes = git_ops.read_notes(self.repo, self.topic)
        version = max((n.get("version", 0) for n in notes), default=0) + 1
        verdict_entry = {
            "id": git_ops.generate_comment_id(),
            "version": version,
            "type": "verdict",
            "author": body.get("author", git_ops.get_author()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "body": body.get("body", ""),
            "verdict": body["verdict"],
        }
        notes.append(verdict_entry)
        git_ops.write_notes(self.repo, self.topic, notes)

        # Create or update beads if configured
        bead_result = None
        if self.bead_config:
            try:
                comments = [n for n in notes if n.get("type") == "comment"]
                bead_kwargs = dict(
                    verdict=body["verdict"],
                    comments=comments,
                    summary=body.get("body", ""),
                    topic=self.topic,
                    base=self.base,
                    tool=self.bead_config.get("bead_tool", "br"),
                    assignee=self.bead_config.get("assignee", "coder"),
                )
                if self.bead_config.get("new_review_bead"):
                    from .beads import create_verdict_bead
                    result = create_verdict_bead(**bead_kwargs)
                else:
                    from .beads import update_with_verdict
                    result = update_with_verdict(
                        review_bead_id=self.bead_config["review_bead"],
                        **bead_kwargs,
                    )
                bead_result = {"bead_id": result.bead_id, "title": result.title}
            except Exception as e:
                bead_result = {"error": str(e)}

        response = dict(verdict_entry)
        if bead_result:
            response["bead"] = bead_result
        self._json_response(200, response)

    def _handle_resolve(self, body: dict):
        comment_id = body["id"]
        notes = git_ops.read_notes(self.repo, self.topic)
        for note in notes:
            if note.get("id") == comment_id:
                note["resolved"] = True
                note["resolved_by"] = body.get("author", git_ops.get_author())
                note["resolved_at"] = datetime.now(timezone.utc).isoformat()
                break
        else:
            self._json_response(404, {"error": f"Comment {comment_id} not found"})
            return
        git_ops.write_notes(self.repo, self.topic, notes)
        self._json_response(200, {"ok": True})

    def _json_response(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass


def run_server(
    html: str,
    repo: str,
    topic: str,
    base: str = "",
    port: int = 0,
    bead_config: dict | None = None,
) -> None:
    """Start server, open browser, block until Ctrl-C."""
    handler = partial(
        ReviewHandler, html=html, repo=repo, topic=topic, base=base,
        bead_config=bead_config,
    )
    server = HTTPServer(("127.0.0.1", port), handler)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/"

    print(f"pyre-review server running at {url}")
    if bead_config and bead_config.get("new_review_bead"):
        print(f"Will create bead on verdict (tool: {bead_config.get('bead_tool', 'br')})")
    elif bead_config:
        print(f"Linked to bead: {bead_config['review_bead']} (tool: {bead_config.get('bead_tool', 'br')})")
    print("Press Ctrl-C to stop.")

    import webbrowser
    webbrowser.open(url)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
