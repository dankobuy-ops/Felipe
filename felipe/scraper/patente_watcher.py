"""Local watcher — enriches the vehicle plates the scraper writes to the Sheet.

Beating Cloudflare requires a real Chrome on your machine (see patente_browser.py),
so this runs locally: it opens Chrome once (you solve the Cloudflare check a single
time), then polls the **Patentes** tab of the JPL Sheet for rows still missing
vehicle data and enriches each behind your solved cookie, writing results back to
the Sheet. Leave it running while you use the app.

Run:
  cd scraper && python patente_watcher.py
"""
import time

import gstore
from enrich_patentes_local import Session, enrich_plates, plates_to_enrich

POLL_SECONDS = 30


def main():
    print(f"[watcher] vigilando la pestaña Patentes cada {POLL_SECONDS}s — Ctrl+C para salir")
    session = Session().start()          # opens Chrome; solve Cloudflare once
    try:
        while True:
            # Fresh Store each cycle so the column-A index reflects plates added
            # by scrapes that ran since the last poll.
            try:
                store = gstore.Store()
                plates = plates_to_enrich(store)
            except Exception as e:
                print(f"[watcher] error al consultar: {e}")
                plates = []
            if plates:
                if not session.alive():
                    print("[watcher] la ventana de Chrome se cerró — reabriendo")
                    session = Session().start()
                enrich_plates(store, session, plates)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n[watcher] detenido")
    finally:
        session.close()


if __name__ == "__main__":
    main()
