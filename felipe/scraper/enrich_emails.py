"""Search for email addresses for personas identified by RUT.

Reads personas without an email from the Sheet's Ruts tab, tries each source
anonymously in order, and writes the email back to that RUT's row on first match.

Usage:
  python enrich_emails.py [--dry-run]
  python enrich_emails.py --sources pjud,boletin_concursal
"""
import argparse
import json
import os
import re
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

import gstore

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

_NOISE_DOMAINS = {
    "sentry.io", "wix.com", "example.com", "domain.com",
    "cloudflare.com", "jquery.com", "w3.org", "schema.org",
    "google.com", "facebook.com", "instagram.com", "linkedin.com",
    "apple.com", "microsoft.com", "amazon.com",
}


def norm_rut(rut):
    return re.sub(r"[.\s]", "", str(rut or "")).lower()


def extract_email(text):
    for m in EMAIL_RE.finditer(text or ""):
        addr = m.group(0).lower()
        domain = addr.split("@")[-1]
        if domain not in _NOISE_DOMAINS and not domain.endswith((".png", ".jpg", ".svg")):
            return addr
    return None


def _go(page, url, wait=1_500):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        page.wait_for_timeout(wait)
        return page.content()
    except Exception:
        return ""


# ── Sheet helpers ─────────────────────────────────────────────────────────────

def full_name(rut_row):
    """Reconstruct a search name from the Ruts tab's split-name columns."""
    parts = [rut_row.get("nombre", ""), rut_row.get("ap_paterno", ""),
             rut_row.get("ap_materno", "")]
    return " ".join(p for p in parts if p).strip() or rut_row.get("razon_social", "")


# ── Sources ───────────────────────────────────────────────────────────────────

def search_linkedin(page, rut, nombre):
    q = requests.utils.quote(nombre or rut)
    html = _go(page, f"https://www.linkedin.com/search/results/people/?keywords={q}", wait=2_000)
    return extract_email(html)


def search_pjud(page, rut, nombre):
    rut_clean = norm_rut(rut)
    html = _go(page, f"https://oficinajudicialvirtual.pjud.cl/indexN.php?vRut={requests.utils.quote(rut_clean)}", wait=2_000)
    return extract_email(html)


def search_diario_oficial(page, rut, nombre):
    rut_clean = norm_rut(rut)
    html = _go(page, f"https://www.diariooficial.interior.gob.cl/publicaciones/buscar?q={requests.utils.quote(rut_clean)}")
    return extract_email(html)


def search_boletin_concursal(page, rut, nombre):
    rut_clean = norm_rut(rut)
    html = _go(page, f"https://www.boletinconcursal.cl/BulletinSearch/SearchPersons?rutOrName={requests.utils.quote(rut_clean)}", wait=2_000)
    return extract_email(html)


def search_hunter(page, rut, nombre):
    q = requests.utils.quote(nombre or rut)
    html = _go(page, f"https://hunter.io/search?query={q}")
    return extract_email(html)


def search_rocketreach(page, rut, nombre):
    q = requests.utils.quote(nombre or rut)
    html = _go(page, f"https://rocketreach.co/search?name={q}")
    return extract_email(html)


def search_lusha(page, rut, nombre):
    q = requests.utils.quote(nombre or rut)
    html = _go(page, f"https://www.lusha.com/people-search/?name={q}")
    return extract_email(html)


def search_facebook(page, rut, nombre):
    q = requests.utils.quote(nombre or rut)
    html = _go(page, f"https://www.facebook.com/search/people/?q={q}", wait=2_000)
    return extract_email(html)


def search_instagram(page, rut, nombre):
    q = requests.utils.quote(nombre or rut)
    html = _go(page, f"https://www.instagram.com/explore/search/keyword/?q={q}", wait=2_000)
    return extract_email(html)


def search_genealogia(page, rut, nombre):
    q = requests.utils.quote(nombre or rut)
    html = _go(page, f"https://www.genealogiacl.cl/search?q={q}")
    return extract_email(html)


# ── Source registry (order = priority) ───────────────────────────────────────

ALL_SOURCES = [
    ("linkedin",          search_linkedin),
    ("pjud",              search_pjud),
    ("diario_oficial",    search_diario_oficial),
    ("boletin_concursal", search_boletin_concursal),
    ("hunter",            search_hunter),
    ("rocketreach",       search_rocketreach),
    ("lusha",             search_lusha),
    ("facebook",          search_facebook),
    ("instagram",         search_instagram),
    ("genealogia",        search_genealogia),
]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-id", help="Accepted for CI compatibility; ignored "
                    "(the Sheet is the source — all personas w/o email are enriched).")
    ap.add_argument("--all", action="store_true", help="Accepted for compatibility.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sources", help="Comma-separated source names (default: all).")
    args = ap.parse_args()

    enabled = set(args.sources.split(",")) if args.sources else None
    active  = [(n, fn) for n, fn in ALL_SOURCES if enabled is None or n in enabled]
    print(f"[enrich] sources: {[n for n, _ in active]}")

    store = gstore.Store()
    ruts = store.read_tab("Ruts")
    targets = [r for r in ruts
               if r.get("tipo") == "persona" and r.get("rut") and not r.get("email")]
    print(f"[enrich] {len(targets)} personas without email")
    if not targets:
        return

    found = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page = ctx.new_page()

        for r in targets:
            rut, nombre = r["rut"], full_name(r)
            print(f"\n[enrich] RUT={rut!r} nombre={nombre!r}")
            email = source = None

            for src_name, src_fn in active:
                try:
                    result = src_fn(page, rut, nombre)
                except Exception as exc:
                    print(f"  [{src_name}] ERROR: {exc}")
                    result = None

                if result:
                    email, source = result, src_name
                    print(f"  [{src_name}] ✓ {email}")
                    break
                print(f"  [{src_name}] —")
                time.sleep(0.4)

            if not email:
                print("  → not found")
                continue

            found += 1
            if args.dry_run:
                print(f"  → DRY RUN: email={email!r} source={source!r}")
                continue

            r["email"] = email
            r["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            try:
                store.upsert("Ruts", [r])      # full row back -> only email changes
                print(f"  → saved (source {source})")
            except Exception as exc:
                print(f"  → ERROR saving: {exc}")

        browser.close()

    print(f"\n[enrich] Done — {found}/{len(targets)} emails found")


if __name__ == "__main__":
    main()
