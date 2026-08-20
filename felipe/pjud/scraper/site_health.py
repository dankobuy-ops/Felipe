"""SITE HEALTH — is the OJV reachable at all, and what does it serve?

    python site_health.py                 # one check, print, exit
    python site_health.py --watch 20      # check every 20 min until it comes UP, then exit 0

WARN: THIS EXISTS BECAUSE WE COULD NOT TELL AN OUTAGE FROM A BLOCK. On 2026-08-20 six sessions
died within thirteen seconds; it was diagnosed as a request-rate wall, written up, and published
before anyone established that the site itself had gone down. Two more hours went into a
"persistent escalating block" that was a redeployed landing page. Every one of those conclusions
needed one fact nobody had: is the site up for anybody?

WARN: IT CLICKS THROUGH FROM www.pjud.cl AND NEVER TYPES A DEEP URL, like everything else here.
It runs NO search and opens NO causa, so it cannot spend a session's allowance -- two page loads,
which is what a person does when they wonder whether a site is back.

WARN: DO NOT POLL IT FAST. The default 20 minutes is deliberate: a burst of brand-new sessions is
itself the trigger this project has documented most often. Checking whether a site is up must not
look like hammering it.
"""
import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cdp_scrape as C
import ojv
import worker_a as A
from ojv import note
from playwright.sync_api import sync_playwright

HREF = "https://oficinajudicialvirtual.pjud.cl/includes/sesion-consultaunificada.php"
PORT = 9590
# WARN: NOT A HARDCODED WINDOWS PATH. This also runs on Linux runners, where the block check
# is worth MORE than it is here -- a runner has no screen, and a blocked address there is
# served the same healthy-looking page with no search form. A Windows-only profile path
# would fail both checks on exactly the machine nobody can look at.
PROF = str(Path(tempfile.gettempdir()) / "pjud_health")


def check(pw):
    """(state, detail). state is 'form' | 'ojv-no-form' | 'no-ojv' | 'no-www'."""
    if not A.launch_chrome(PORT, PROF, 1, exe=A.chrome_executable(pw)):
        return "no-chrome", "could not launch"
    b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=20000)
    ctx = b.contexts[0]
    p = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        p.goto("https://www.pjud.cl/", wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        return "no-www", str(e)[:70]
    p.wait_for_timeout(3000)
    loc = p.locator(f"a[href='{HREF}']").first
    if not loc.count():
        return "no-www", "the OJV anchor is not on www.pjud.cl"
    # human_click, NOT page.click: a covered click and a dead link look identical from outside,
    # and this project has burned weeks on exactly that confusion.
    C.human_click(p, loc)
    deadline = time.time() + 40
    ojv_pg = None
    while time.time() < deadline:
        cands = [x for x in ctx.pages if "oficinajudicialvirtual" in (x.url or "")]
        if cands:
            ojv_pg = cands[0]
            ojv_pg.bring_to_front()
            break
        p.wait_for_timeout(1000)
    if ojv_pg is None:
        return "no-ojv", "clicked the anchor, no OJV tab in 40 s"
    ojv_pg.wait_for_timeout(4000)
    d = ojv.describe_pages(ctx)
    hit = next((x for x in d if "oficinajudicialvirtual" in (x.get("url") or "")), {})
    if hit.get("fec"):
        return "form", "the search form is present -- the site is usable"
    return "ojv-no-form", (f"OJV serves {hit.get('url','?')} without #fecCompetencia; "
                           f"entry points: {', '.join(hit.get('onclicks') or []) or 'none'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--watch", type=float, default=0.0,
                    help="minutes between checks; loops until the form is reachable. "
                         "Do not go below ~10 -- see the warning in this file.")
    a = ap.parse_args()
    gap = max(10.0, a.watch) if a.watch else 0.0
    with sync_playwright() as pw:
        while True:
            try:
                st, why = check(pw)
            except Exception as e:
                st, why = "error", str(e)[:90]
            note(f"SITE {st.upper()}: {why}")
            # close_chrome(proc, profile) -- the profile form kills exactly the Chrome this
            # profile owns, so a health check never touches the operator's own browser.
            try:
                A.close_chrome(None, PROF)
            except Exception as e:
                note(f"  (could not close chrome: {str(e)[:60]})")
            if st == "form":
                note("the OJV is usable again")
                return 0
            if not gap:
                return 1
            note(f"  next check in {gap:.0f} min")
            time.sleep(gap * 60)


if __name__ == "__main__":
    sys.exit(main())
