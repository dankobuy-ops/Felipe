"""bootstrap_probe.py — can the scraper reach Consulta Causas WITHOUT a human?

The operator's hypothesis (2026-07-22): arriving at Consulta Causas by clicking through from
www.pjud.cl does not raise the CAPTCHA, unlike landing on the OJV directly. If that holds, a
run needs no human at all: fresh profile -> click through -> establish the form by keyboard ->
sweep. If it does not hold, the CAPTCHA stays the one manual step per session.

RESULT 2026-07-22: the hypothesis is HALF right and the conclusion is NO.
Clicking through from www.pjud.cl reaches the date form with no visible challenge — the probe
found `#fecCompetencia` present and no puzzle to solve. But a virgin profile (never touched by
a human) was **F5-BLOCKED on its very first scripted search**, while the operator's warmed
profile stayed HEALTHY through 20 causas at the same moment. The site runs **reCAPTCHA v3
enterprise**: invisible, score-based, and the score comes from the session's behavioural
history. A profile with no human history has nothing to score, so it fails no matter how good
the pointer motion is. **The human step is the session earning trust, not solving a puzzle.**
NB that test changed two things at once (no warm-up AND `establish_form_kbd`'s keyboard arrow
bursts); pass the CAPTCHA by hand and stop, then run `--corte`, to separate them.

⚠️ Do NOT read a verdict off the DOM. reCAPTCHA v3 iframes are ALWAYS in the page — their
presence means nothing. Only an actual search settles it.

This probe only NAVIGATES and REPORTS. It opens no causa, downloads nothing, and runs no
search, so it costs a profile almost nothing. Every click goes through cdp_scrape.human_click.

    python bootstrap_probe.py --port 9334            # click through and report
    python bootstrap_probe.py --port 9334 --list-only # just show the candidate links

Verdict: NO-CAPTCHA (form reachable unattended) / CAPTCHA (human needed) / NO-FORM.
"""

import argparse
import re
import time

from playwright.sync_api import sync_playwright

import cdp_scrape as cs

# Text/href patterns for the link that leads to the Oficina Judicial Virtual / Consulta Causas.
WANT = re.compile(r"(consulta.*causa|causa|oficina judicial|ojv)", re.I)
CAPTCHA_SEL = ("iframe[src*='recaptcha']", "iframe[title*='captcha' i]", ".g-recaptcha",
               "#captcha", "[id*='captcha' i]", "[class*='captcha' i]")


def links(page):
    """[{text, href}] for every anchor whose text or href smells like Consulta Causas."""
    try:
        got = page.eval_on_selector_all(
            "a", "els=>els.map(a=>({t:(a.textContent||'').trim().slice(0,70),"
                 " h:a.getAttribute('href')||'', oc:(a.getAttribute('onclick')||'').slice(0,90)}))")
    except Exception:
        return []
    return [g for g in got if WANT.search(g["t"]) or WANT.search(g["h"]) or WANT.search(g["oc"])]


def captcha_state(page):
    """(present, detail) — is a CAPTCHA widget rendered on this page?"""
    hits = []
    for sel in CAPTCHA_SEL:
        try:
            n = page.eval_on_selector_all(sel, "e=>e.length")
        except Exception:
            n = 0
        if n:
            hits.append(f"{sel}={n}")
    return (bool(hits), ", ".join(hits))


def report(target):
    """Print the verdict for an OJV page: is the date form reachable, is a CAPTCHA in the way?"""
    try:
        target.wait_for_timeout(2500)
    except Exception:
        pass
    print(f"[ojv] {target.url}")
    cap, detail = captcha_state(target)
    has_form = False
    try:
        has_form = bool(target.query_selector("#fecCompetencia"))
    except Exception:
        pass
    # The date form lives behind the "Consulta Causas" menu item inside the OJV, so its absence
    # is not necessarily a CAPTCHA — say which it is.
    print(f"[captcha widgets] {'SI' if cap else 'no'}  {detail}")
    print(f"[form #fecCompetencia] {'SI' if has_form else 'no'}")
    if has_form:
        # reCAPTCHA v3 is invisible and always present, so `cap` is NOT a blocker signal —
        # reporting CAPTCHA here just because iframes exist was wrong (2026-07-22).
        print("\nVERDICT: FORM-REACHABLE — se llega al formulario sin resolver nada.")
        print("  Esto NO significa que la sesion tenga permiso: el v3 puntua el comportamiento.")
        print("  Compruebalo con una BUSQUEDA real:")
        print("    python cdp_scrape.py --port <p> --count-only --corte 90 --max-tribs 1")
        print("  (2026-07-22: un perfil virgen fue BLOQUEADO en esa primera busqueda.)")
        return 0
    print("\nVERDICT: NO-FORM — estamos en la OJV pero sin el formulario de fecha; falta "
          "entrar a 'Consulta Causas' y a la pestana 'Busqueda por Fecha'.")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9334)
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--wait", type=float, default=12.0, help="seconds to wait for the new tab")
    args = ap.parse_args()

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        ctx = browser.contexts[0]
        start = next((p for p in ctx.pages if "pjud.cl" in (p.url or "")), None)
        if not start:
            raise SystemExit("[ERROR] No hay pestana en pjud.cl. Abre Chrome en www.pjud.cl.")
        print(f"[start] {start.url}")

        # If the OJV is already open (previous run, or the operator got there), report on it
        # rather than clicking through a second time and stacking tabs.
        already = next((p for p in ctx.pages
                        if "oficinajudicialvirtual" in (p.url or "")), None)
        if already is not None:
            return report(already)

        cands = links(start)
        print(f"[links] {len(cands)} candidatos:")
        for c in cands[:12]:
            print(f"    {c['t'][:52]:54} href={c['h'][:60]}")
        if args.list_only:
            return 0
        if not cands:
            print("VERDICT: NO-FORM  (no encuentro el enlace a Consulta Causas)")
            return 1

        # Pick by HREF, not by link text: on www.pjud.cl the Consulta-Causas card is described
        # as "Seccion que permite la revision de causas" — the word "consulta" appears only in
        # the URL (/includes/sesion-consulta...). Text matching lands on the login area instead.
        def score(c):
            h = c["h"].lower()
            if "sesion-consu" in h or "consulta" in h:
                return 0
            if "oficinajudicialvirtual" in h:
                return 1
            return 2
        best = sorted(cands, key=score)[0]
        print(f"[act] human_click -> {best['t'][:50]!r}  href={best['h'][:70]}")
        before = set(ctx.pages)
        sel = f"a[href='{best['h']}']" if best["h"] else None
        cs.human_click(start, start.locator(sel).first if sel
                       else start.locator(f"a:has-text({best['t'][:40]!r})").first)

        # The OJV opens in a NEW tab; wait for it (or for this tab to navigate).
        target, deadline = None, time.time() + args.wait
        while time.time() < deadline:
            fresh = [p for p in ctx.pages if p not in before]
            for p in fresh + [start]:
                try:
                    if "oficinajudicialvirtual" in (p.url or ""):
                        target = p
                        break
                except Exception:
                    pass
            if target:
                break
            time.sleep(0.5)
        if not target:
            print("VERDICT: NO-FORM  (el click no abrio la OJV)")
            return 1

        target.wait_for_timeout(3000)
        print(f"[ojv] {target.url}")
        cap, detail = captcha_state(target)
        has_form = False
        try:
            has_form = bool(target.query_selector("#fecCompetencia"))
        except Exception:
            pass
        print(f"[captcha] {'SI' if cap else 'no'}  {detail}")
        print(f"[form #fecCompetencia] {'SI' if has_form else 'no'}")

        if has_form and not cap:
            print("\nVERDICT: NO-CAPTCHA — el formulario es alcanzable sin humano.")
            rc = 0
        elif cap:
            print("\nVERDICT: CAPTCHA — hace falta un humano una vez por sesion.")
            rc = 2
        else:
            print("\nVERDICT: NO-FORM — llegamos a la OJV pero sin el formulario de fecha "
                  "(quiza hay un paso intermedio: 'Consulta Causas' dentro de la OJV).")
            rc = 1
        browser.close()
        return rc


if __name__ == "__main__":
    raise SystemExit(main())
