#!/usr/bin/env python3
"""waf_check.py — read-only health check of the CDP Chrome session against the OJV WAF.

Run this BEFORE a scrape (is the session usable?) and AFTER a suspected block
(what kind of block is it?). It only reads: no clicks, no searches, no downloads,
so it never costs you reputation.

    python waf_check.py [--port 9333]

Verdicts:
  HEALTHY        session is live, results table has rows, no rejection frames.
  BLOCKED-DETAIL the F5 WAF is rejecting detalleCausaCivil. Search still works.
                 -> the profile is burned. Rename %LOCALAPPDATA%\\pjud_cdp aside and
                    re-pass the CAPTCHA. See rule 8 in HANDOFF_CDP.md.
  THROTTLED      no rejection page, but the results table is empty / modals hang.
                 -> rate throttling, not the device flag. A fresh session may suffice.
  NO-SESSION     Chrome not on the CDP port, or OJV not open.

Why both matter: they look the same from the scraper's side (a causa that won't
open) but have different fixes, and confusing them wastes profiles.
"""
import argparse
import sys

from playwright.sync_api import sync_playwright

REJECT_MARKERS = ("requested URL was rejected", "Support ID", "consult with your administrator")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--cookies", action="store_true", help="also dump the F5 cookie set")
    args = ap.parse_args()

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        except Exception as e:
            print(f"VERDICT: NO-SESSION  (cannot reach CDP on {args.port}: {str(e)[:60]})")
            print("  -> open felipe\\pjud\\Abrir_CDP.cmd first.")
            return 2

        ojv = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "oficinajudicialvirtual" in pg.url:
                    ojv = pg
                    break
        if ojv is None:
            print("VERDICT: NO-SESSION  (Chrome is up but OJV is not open in any tab)")
            browser.close()
            return 2

        print(f"page: {ojv.url[:100]}")

        # --- rejection frames (the F5 block renders INTO the detail-modal iframes) ---
        support_ids, rejected = set(), 0
        for fr in ojv.frames:
            try:
                txt = fr.evaluate("document.body?document.body.innerText.slice(0,600):''") or ""
            except Exception:
                continue
            if any(m.lower() in txt.lower() for m in REJECT_MARKERS):
                rejected += 1
                for tok in txt.split():
                    if tok.startswith("<") and tok.endswith(">") and tok[1:-1].isdigit():
                        support_ids.add(tok[1:-1])
        print(f"rejection frames: {rejected}")
        if support_ids:
            print(f"support IDs     : {', '.join(sorted(support_ids))}")

        # --- session state ---
        try:
            trib = ojv.eval_on_selector(
                "#fecTribunal",
                "e=>e.options[e.selectedIndex]?e.options[e.selectedIndex].text.trim()+' / '+e.value:'(none)'")
        except Exception:
            trib = "(no #fecTribunal — not on Busqueda por Fecha?)"
        rows = 0
        try:
            rows = ojv.locator("#dtaTableDetalleFecha tbody tr").count()
        except Exception:
            pass
        print(f"tribunal        : {trib}")
        print(f"result rows     : {rows}")

        # --- F5 cookies: TSPD_101_DID is the device id that survives IP changes ---
        did = []
        try:
            for c in browser.contexts[0].cookies():
                if "pjud" in c.get("domain", "") and c.get("name", "").startswith("TS"):
                    if c["name"].endswith("_DID"):
                        did.append(f"{c['domain']}:{c['name']}")
                    if args.cookies:
                        print(f"  cookie {c['domain']:34} {c['name']:16} len={len(c.get('value',''))}")
        except Exception as e:
            print(f"  (cookie read failed: {str(e)[:50]})")
        print(f"device-id cookies: {len(did)} {'(' + ', '.join(did) + ')' if did else ''}")

        browser.close()

    if rejected:
        print("\nVERDICT: BLOCKED-DETAIL")
        print("  The WAF is rejecting detail opens. Search may still work — that is the tell.")
        print("  FIX: close Chrome, rename %LOCALAPPDATA%\\pjud_cdp to pjud_cdp.burned-<date>,")
        print("       reopen Abrir_CDP.cmd, re-pass the CAPTCHA. A new IP alone will NOT help.")
        return 1
    if rows == 0:
        print("\nVERDICT: THROTTLED (or no search run yet)")
        print("  No rejection page, but no results either. If you HAVE searched, this is the")
        print("  throttle symptom — stop and take a fresh session.")
        return 1
    print("\nVERDICT: HEALTHY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
