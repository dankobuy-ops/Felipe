"""Thin backend — triggers GitHub workflow_dispatch and proxies results from Supabase.

Run locally:  python server.py
Required env vars:
  DISPATCH_PAT         GitHub PAT with workflow scope
  GH_REPO             owner/repo  (e.g. dankobuy-ops/Felipe)
  SUPABASE_URL        Your Supabase project URL
  SUPABASE_SERVICE_KEY  Supabase service role key
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scraper"))
from checkpoint import read_checkpoint  # noqa: E402
from validate_inputs import validate    # noqa: E402

PORT = int(os.environ.get("PORT", 8080))
REQUIRED_VARS = ["DISPATCH_PAT", "GH_REPO", "SUPABASE_URL", "SUPABASE_SERVICE_KEY"]


def _check_env():
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def trigger_workflow(job_id: str, search_code: str, target_url: str) -> None:
    pat = os.environ["DISPATCH_PAT"]
    repo = os.environ["GH_REPO"]
    url = f"https://api.github.com/repos/{repo}/actions/workflows/scrape.yml/dispatches"
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={
            "ref": "main",
            "inputs": {
                "job_id": job_id,
                "search_code": search_code,
                "target_url": target_url,
                "resume_attempt": "0",
            },
        },
        timeout=15,
    )
    if r.status_code not in (200, 204):
        raise RuntimeError(f"GitHub API error {r.status_code}: {r.text}")


def get_results(job_id: str) -> dict:
    checkpoint = read_checkpoint(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
        job_id,
    )
    job_status = checkpoint.pop("__job__", "running")
    records = [
        {"record_id": rid, "status": st, "text": "", "pdf_url": ""}
        for rid, st in checkpoint.items()
    ]
    return {"status": job_status, "records": records}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args)

    def _send(self, code: int, body) -> None:
        if isinstance(body, dict):
            data = json.dumps(body).encode()
            ct = "application/json"
        else:
            data = str(body).encode()
            ct = "text/plain"
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path != "/api/trigger":
            self._send(404, "Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            validate(body["target_url"])
            trigger_workflow(body["job_id"], body["search_code"], body["target_url"])
            self._send(200, {"ok": True, "job_id": body["job_id"]})
        except (KeyError, json.JSONDecodeError) as e:
            self._send(400, f"Bad request: {e}")
        except ValueError as e:
            self._send(422, f"Invalid input: {e}")
        except RuntimeError as e:
            self._send(502, f"Upstream error: {e}")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/results":
            self._send(404, "Not found")
            return
        qs = parse_qs(parsed.query)
        job_ids = qs.get("job_id", [])
        if not job_ids:
            self._send(400, "Missing job_id")
            return
        try:
            self._send(200, get_results(job_ids[0]))
        except Exception as e:
            self._send(500, f"Error: {e}")


if __name__ == "__main__":
    _check_env()
    print(f"Backend running on http://localhost:{PORT}")
    HTTPServer(("", PORT), Handler).serve_forever()
