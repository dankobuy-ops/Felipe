"""Local watcher — enriches the vehicle plates the scraper writes to the Sheet.

The web page can't scrape patentechile.com itself (Cloudflare blocks headless /
datacenter IPs). Run this on your own machine, with a real browser: it polls the
**Patentes** tab of the JPL Sheet for rows still missing vehicle data, scrapes
each behind your solved Cloudflare cookie, and writes the result back to the Sheet.
Leave it running while you use the app — no Supabase queue anymore.

Run:
  cd scraper && python patente_watcher.py
"""
import time

import gstore
# sync_playwright comes from enrich_patentes_local so the watcher uses the same
# driver it picks (patchright if available).
from enrich_patentes_local import (
    open_context, enrich_plates, plates_to_enrich, sync_playwright,
)

POLL_SECONDS = 30


def main():
    print(f"[watcher] polling the Patentes tab every {POLL_SECONDS}s — Ctrl+C to stop")
    with sync_playwright() as pw:
        ctx = open_context(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            while True:
                # Fresh Store each cycle so the column-A index reflects plates added
                # by scrapes that ran since the last poll.
                try:
                    store = gstore.Store()
                    plates = plates_to_enrich(store)
                except Exception as e:
                    print(f"[watcher] poll error: {e}")
                    plates = []
                if plates:
                    if page.is_closed():
                        page = ctx.new_page()
                    enrich_plates(store, page, plates)
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
