"""Search for email addresses for demandados identified by RUT.

Reads demandados without emails from Supabase, tries each configured
source in order, and patches the email back into the record on first match.

Usage:
  python enrich_emails.py [--job-id <UUID>] [--all] [--dry-run]
  python enrich_emails.py --all --sources pjud,boletin_concursal

Sources (tried in order):
  linkedin, pjud, diario_oficial, boletin_concursal,
  hunter, rocketreach, lusha, facebook, instagram, genealogia

Sources that need credentials / keys (skipped if env var not set):
  LINKEDIN_EMAIL + LINKEDIN_PASSWORD  → linkedin
  HUNTER_API_KEY                      → hunter
  ROCKETREACH_API_KEY                 → rocketreach
  LUSHA_API_KEY                       → lusha
  FACEBOOK_EMAIL + FACEBOOK_PASSWORD  → facebook
  INSTAGRAM_EMAIL + INSTAGRAM_PASSWORD → instagram
"""
import argparse
import json
import os
import re
import sys
import time

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

_BLOCKED_DOMAINS = {
    "sentry.io", "wix.com", "example.com", "domain.com",
    "cloudflare.com", "jquery.com", "w3.org",
}


def norm_rut(rut):
    return re.sub(r"[.\s]", "", str(rut or "")).lower()


def extract_email(text):
    for m in EMAIL_RE.finditer(text or ""):
        addr = m.group(0).lower()
        domain = addr.split("@")[-1]
        if domain not in _BLOCKED_DOMAINS and not domain.endswith(".png"):
            return addr
    return None


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def fetch_all_rows(job_id=None):
    params = {"select": "job_id,record_id,status,text", "order": "job_id"}
    if job_id:
        params["job_id"] = f"eq.{job_id}"
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/checkpoints",
        headers=_sb_headers(), params=params, timeout=90,
    )
    r.raise_for_status()
    return r.json()


def patch_row(job_id, record_id, new_text):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/checkpoints",
        headers={**_sb_headers(), "Content-Type": "application/json"},
        params={"job_id": f"eq.{job_id}", "record_id": f"eq.{record_id}"},
        json={"text": new_text},
        timeout=30,
    )
    r.raise_for_status()


# ── Source functions ──────────────────────────────────────────────────────────
# Each receives (page, rut, nombre) and returns an email string or None.
# Page is a shared Playwright page — callers must not rely on page state
# persisting between sources.

def search_linkedin(page, rut, nombre):
    email_cred = os.environ.get("LINKEDIN_EMAIL", "")
    pwd        = os.environ.get("LINKEDIN_PASSWORD", "")
    if not (email_cred and pwd):
        return None
    try:
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=20_000)
        page.fill("#username", email_cred)
        page.fill("#password", pwd)
        page.click("button[type=submit]")
        page.wait_for_timeout(3_000)
        q = requests.utils.quote(nombre or rut)
        page.goto(f"https://www.linkedin.com/search/results/people/?keywords={q}",
                  wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(2_000)
        return extract_email(page.content())
    except Exception:
        return None


def search_pjud(page, rut, nombre):
    try:
        rut_clean = norm_rut(rut)
        page.goto(
            f"https://oficinajudicialvirtual.pjud.cl/indexN.php?vRut={requests.utils.quote(rut_clean)}",
            wait_until="domcontentloaded", timeout=25_000,
        )
        page.wait_for_timeout(2_000)
        return extract_email(page.content())
    except Exception:
        return None


def search_diario_oficial(page, rut, nombre):
    try:
        rut_clean = norm_rut(rut)
        page.goto(
            f"https://www.diariooficial.interior.gob.cl/publicaciones/buscar?q={requests.utils.quote(rut_clean)}",
            wait_until="domcontentloaded", timeout=20_000,
        )
        page.wait_for_timeout(1_500)
        return extract_email(page.content())
    except Exception:
        return None


def search_boletin_concursal(page, rut, nombre):
    try:
        rut_clean = norm_rut(rut)
        page.goto(
            f"https://www.boletinconcursal.cl/BulletinSearch/SearchPersons?rutOrName={requests.utils.quote(rut_clean)}",
            wait_until="domcontentloaded", timeout=20_000,
        )
        page.wait_for_timeout(2_000)
        return extract_email(page.content())
    except Exception:
        return None


def search_hunter(page, rut, nombre):
    api_key = os.environ.get("HUNTER_API_KEY", "")
    if not api_key or not nombre:
        return None
    try:
        parts = nombre.strip().split()
        first = parts[0] if parts else ""
        last  = parts[-1] if len(parts) > 1 else ""
        r = requests.get(
            "https://api.hunter.io/v2/email-finder",
            params={"first_name": first, "last_name": last, "api_key": api_key},
            timeout=15,
        )
        if r.ok:
            return r.json().get("data", {}).get("email") or None
    except Exception:
        pass
    return None


def search_rocketreach(page, rut, nombre):
    api_key = os.environ.get("ROCKETREACH_API_KEY", "")
    if not api_key or not nombre:
        return None
    try:
        r = requests.get(
            "https://api.rocketreach.co/v2/api/search",
            headers={"Api-Key": api_key},
            params={"name": nombre},
            timeout=15,
        )
        if r.ok:
            for profile in r.json().get("profiles", []):
                emails = profile.get("emails") or []
                if emails:
                    return emails[0]
    except Exception:
        pass
    return None


def search_lusha(page, rut, nombre):
    api_key = os.environ.get("LUSHA_API_KEY", "")
    if not api_key or not nombre:
        return None
    try:
        parts = nombre.strip().split()
        first = parts[0] if parts else ""
        last  = parts[-1] if len(parts) > 1 else ""
        r = requests.get(
            "https://api.lusha.com/person",
            headers={"api_key": api_key},
            params={"firstName": first, "lastName": last},
            timeout=15,
        )
        if r.ok:
            for entry in r.json().get("emailAddresses") or []:
                if entry.get("email"):
                    return entry["email"]
    except Exception:
        pass
    return None


def search_facebook(page, rut, nombre):
    email_cred = os.environ.get("FACEBOOK_EMAIL", "")
    pwd        = os.environ.get("FACEBOOK_PASSWORD", "")
    if not (email_cred and pwd) or not nombre:
        return None
    try:
        page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=20_000)
        page.fill("#email", email_cred)
        page.fill("#pass", pwd)
        page.click("button[name=login]")
        page.wait_for_timeout(3_000)
        q = requests.utils.quote(nombre)
        page.goto(f"https://www.facebook.com/search/people/?q={q}",
                  wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(2_000)
        return extract_email(page.content())
    except Exception:
        return None


def search_instagram(page, rut, nombre):
    email_cred = os.environ.get("INSTAGRAM_EMAIL", "")
    pwd        = os.environ.get("INSTAGRAM_PASSWORD", "")
    if not (email_cred and pwd) or not nombre:
        return None
    try:
        page.goto("https://www.instagram.com/accounts/login/",
                  wait_until="domcontentloaded", timeout=20_000)
        page.fill("input[name=username]", email_cred)
        page.fill("input[name=password]", pwd)
        page.click("button[type=submit]")
        page.wait_for_timeout(3_000)
        q = requests.utils.quote(nombre)
        page.goto(f"https://www.instagram.com/explore/search/keyword/?q={q}",
                  wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(2_000)
        return extract_email(page.content())
    except Exception:
        return None


def search_genealogia(page, rut, nombre):
    try:
        q = requests.utils.quote(nombre or rut)
        page.goto(f"https://www.genealogiacl.cl/search?q={q}",
                  wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(1_500)
        return extract_email(page.content())
    except Exception:
        return None


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
    ap.add_argument("--job-id", help="Enrich a single job.")
    ap.add_argument("--all", action="store_true", help="Enrich all jobs.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print findings without writing to Supabase.")
    ap.add_argument("--sources",
                    help="Comma-separated source names (default: all).")
    args = ap.parse_args()

    if not (args.job_id or args.all):
        sys.exit("ERROR: pass --job-id <JOB> or --all")
    if not (SUPABASE_URL and SUPABASE_KEY):
        sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    enabled = set(args.sources.split(",")) if args.sources else None
    active_sources = [(n, fn) for n, fn in ALL_SOURCES
                      if enabled is None or n in enabled]
    print(f"[enrich] sources: {[n for n, _ in active_sources]}")

    rows = fetch_all_rows(args.job_id if not args.all else None)

    # Index rows by job → rol
    rol_rows: dict[str, dict[str, dict]] = {}
    for row in rows:
        rid = row.get("record_id", "")
        if rid.startswith("__"):
            continue
        rol_rows.setdefault(row["job_id"], {})[rid] = row

    # Collect demandados that need an email
    targets = []  # (job_id, rol, dem_index, rut, nombre)
    for jid, rols in rol_rows.items():
        for rol, row in rols.items():
            try:
                d = json.loads(row.get("text") or "{}")
            except Exception:
                continue
            for i, dem in enumerate(d.get("demandados") or []):
                if not dem.get("email") and dem.get("rut"):
                    targets.append((jid, rol, i, dem["rut"], dem.get("nombre", "")))

    print(f"[enrich] {len(targets)} demandados without email")
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

        for (jid, rol, dem_idx, rut, nombre) in targets:
            print(f"\n[enrich] {rol} dem[{dem_idx}] RUT={rut!r} nombre={nombre!r}")
            email  = None
            source = None

            for src_name, src_fn in active_sources:
                try:
                    result = src_fn(page, rut, nombre)
                except Exception as exc:
                    print(f"  [{src_name}] ERROR: {exc}")
                    result = None

                if result:
                    email  = result
                    source = src_name
                    print(f"  [{src_name}] ✓ {email}")
                    break
                else:
                    print(f"  [{src_name}] —")
                time.sleep(0.4)

            if not email:
                print("  → not found")
                continue

            found += 1
            if args.dry_run:
                print(f"  → DRY RUN — would write email={email!r} source={source!r}")
                continue

            # Patch the Supabase row with the found email
            row = rol_rows[jid][rol]
            try:
                d = json.loads(row.get("text") or "{}")
                dem_list = d.get("demandados") or []
                if dem_idx < len(dem_list):
                    dem_list[dem_idx]["email"]        = email
                    dem_list[dem_idx]["email_source"] = source
                    d["demandados"] = dem_list
                    new_text = json.dumps(d, ensure_ascii=False)
                    patch_row(jid, rol, new_text)
                    row["text"] = new_text  # keep local index fresh
                    print("  → saved to Supabase")
            except Exception as exc:
                print(f"  → ERROR saving: {exc}")

        browser.close()

    print(f"\n[enrich] Done — {found}/{len(targets)} emails found")


if __name__ == "__main__":
    main()
