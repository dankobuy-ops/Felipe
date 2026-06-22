"""Local watcher — bridges the web app's "Buscar Patentes" button to your PC.

The app (GitHub Pages) can't scrape patentechile.com itself (Cloudflare blocks
headless/datacenter). Instead the button inserts a row in the `patente_requests`
table; this script — running on your machine, with a real browser — polls that
table, runs the search for each requested job, saves results to Supabase, and
marks the request done. Leave it running while you use the app.

Setup (once):
  1. Create the table — run scraper/patente_requests.sql in the Supabase SQL editor.
  2. Put creds in scraper/.env (see .env.example).
Run:
  cd scraper && python patente_watcher.py
"""
import os
import sys
import time

import requests

# Load scraper/.env (simple parser; no extra dependency) before importing config.
def _load_env():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

from enrich_patentes import SUPABASE_URL, SUPABASE_KEY  # read after .env load
# sync_playwright comes from enrich_patentes_local so the watcher uses the same
# driver it picks (patchright if available).
from enrich_patentes_local import (
    open_context, enrich_plates, job_to_enrich, sync_playwright,
)

POLL_SECONDS = 10
REQ = f"{SUPABASE_URL}/rest/v1/patente_requests"


def _hdr():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"}


def fetch_pending():
    # Only enrich requests run here; export now runs in the export.yml Action.
    r = requests.get(REQ, headers=_hdr(),
                     params={"select": "id,job_id,status", "status": "eq.pending",
                             "kind": "eq.enrich", "order": "created_at.asc"}, timeout=30)
    r.raise_for_status()
    return r.json()


def set_status(req_id, status, message=""):
    requests.patch(f"{REQ}?id=eq.{req_id}", headers={**_hdr(), "Prefer": "return=minimal"},
                   json={"status": status, "message": message[:500],
                         "updated_at": "now()"}, timeout=30)


def process(req, page):
    rid, job_id = req["id"], req["job_id"]
    print(f"\n=== request {rid[:8]} job {job_id} ===")
    set_status(rid, "running")
    try:
        plates = job_to_enrich(job_id)
        if not plates:
            set_status(rid, "done", "nothing to enrich")
            print("  nothing to enrich")
            return
        found, total = enrich_plates(page, plates)
        set_status(rid, "done", f"{found}/{total} enriched")
        print(f"  done: {found}/{total}")
    except Exception as e:
        set_status(rid, "error", str(e))
        print(f"  ERROR: {e}")


def main():
    if not (SUPABASE_URL and SUPABASE_KEY):
        sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY (scraper/.env)")
    print(f"[watcher] polling {REQ} every {POLL_SECONDS}s — Ctrl+C to stop")
    with sync_playwright() as pw:
        ctx = open_context(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            while True:
                try:
                    pending = fetch_pending()
                except Exception as e:
                    print(f"[watcher] poll error: {e}")
                    pending = []
                for req in pending:
                    if page.is_closed():
                        page = ctx.new_page()
                    process(req, page)
                time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            print("\n[watcher] stopped")
        finally:
            try:
                ctx.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
