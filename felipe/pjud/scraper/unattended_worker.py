"""unattended_worker.py — bring a worker up with NO human step, and say honestly whether the
site accepts it.

The one manual step in this whole pipeline is a person warming a profile: browse pjud.cl, click
into Consulta Causas, run a couple of searches by hand. If that step can be dropped, workers
become disposable and the job scales with machines instead of with the operator's evening.

    python unattended_worker.py --worker 4                  # launch, click through, ONE search
    python unattended_worker.py --worker 4 --warmup 240      # ...after 4 min of scripted browsing
    python unattended_worker.py --worker 4 --keep            # leave Chrome open on success

It launches its own Chrome on a FRESH profile dir, waits for CDP, clicks through from
www.pjud.cl (never pastes the OJV URL — arriving by click is part of what the site scores),
opens the Busqueda-por-Fecha panel, establishes the form by trusted keyboard, and fires exactly
ONE search. Every click goes through cdp_scrape.human_click.

VERDICTS
  OK          the search returned rows -> unattended workers are possible.
  BLOCKED     an F5 rejection page. The profile has no behavioural history to score;
              reCAPTCHA v3 is invisible and score-based, so there is nothing to "solve".
  NO-FORM     never reached the date form (navigation problem, not a WAF problem).
  NO-CHROME   Chrome never came up on the debug port.

PRIOR RESULT (2026-07-22): BLOCKED on the first scripted search. Treat that as UNRELIABLE —
that run predates the `#BusFecha-collapse` fix, so it was driving a COLLAPSED (invisible) form
and its "block" may have been misread. That is why this script exists as a repeatable test
instead of a one-off probe.
"""
import argparse
import os
import re
import subprocess
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

import cdp_scrape as cs

PORTS = {1: 9333, 2: 9335, 3: 9336, 4: 9337, 5: 9338}
PROFILES = {1: "pjud_cdp", 2: "pjud_cdp_w2", 3: "pjud_cdp_w3", 4: "pjud_cdp_w4", 5: "pjud_cdp_w5"}
CHROMES = (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")
# The ONE link that opens the OJV from www.pjud.cl is an anchor whose href points at the OJV
# host: <a href="https://oficinajudicialvirtual.pjud.cl/home/">Plataforma para el ingreso de
# causas y escritos…</a>. Recorded live from the operator's click-through 2026-07-23. The old
# regex used "oficina judicial" WITH A SPACE, so it never matched "oficinajudicialvirtual" in
# the href, and the link text has no "consulta" — the picker fell through to the e-filing portal.
OJV_HOST = "oficinajudicialvirtual"


def _has_form(page):
    """True if this tab holds the Busqueda-por-Fecha form (present in the DOM, visible or not)."""
    try:
        return bool(page.query_selector("#fecCompetencia"))
    except Exception:
        return False


def on_form(ctx):
    """True if ANY tab already shows the search form — the warm-profile shortcut."""
    return any(_has_form(p) for p in ctx.pages)


def launch(port, profile_dir, url="https://www.pjud.cl"):
    """Start Chrome on its own profile + debug port. Returns the Popen, or None if no Chrome."""
    exe = next((c for c in CHROMES if os.path.exists(c)), None)
    if not exe:
        return None
    return subprocess.Popen([
        exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile_dir}",
        "--no-first-run", "--no-default-browser-check", "--start-maximized", url])


def wait_cdp(port, secs=60):
    """Block until the debug port answers. Chrome takes a few seconds on a brand-new profile."""
    deadline = time.time() + secs
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read()
            return True
        except Exception:
            time.sleep(1.0)      # plain sleep is fine here: no Playwright loop is running yet
    return False


def warm_up(page, seconds):
    """Scripted browsing before the first search: scroll, pause, move the pointer along human
    arcs. This is a GUESS at what reCAPTCHA v3 scores, not a validated recipe — if the bare run
    is BLOCKED and this one is OK, the difference is the finding."""
    end = time.time() + seconds
    n = 0
    while time.time() < end:
        n += 1
        try:
            box = page.viewport_size or {"width": 1280, "height": 800}
            cs._human_pointer(page, 80 + (n * 137) % max(box["width"] - 160, 200),
                              90 + (n * 211) % max(box["height"] - 180, 200))
            page.mouse.wheel(0, 220 if n % 3 else -260)
            page.wait_for_timeout(900 + (n * 173) % 1600)
        except Exception:
            page.wait_for_timeout(1000)
    print(f"    [warmup] {n} interacciones en {seconds}s")


def reach_ojv(ctx, start, wait=15.0):
    """Click through from www.pjud.cl to the OJV. Returns the OJV page or None.

    Pick by HREF pointing at the OJV host — the only reliable signal. The link text
    ("Plataforma para el ingreso de causas y escritos…") mentions neither 'consulta' nor
    'oficina judicial', so text matching lands on the wrong card."""
    cands = start.eval_on_selector_all(
        "a", "els=>els.map(a=>({t:(a.textContent||'').trim().slice(0,60),"
             " h:a.getAttribute('href')||''}))")
    hits = [c for c in cands if OJV_HOST in c["h"].lower()]
    if not hits:
        print(f"    [nav] no encuentro ningun <a href*='{OJV_HOST}'> en {start.url[:50]}")
        return None
    # Prefer /home/ (the landing) over any deep-link into a specific case view.
    hits.sort(key=lambda c: 0 if "/home" in c["h"].lower() else 1)
    best = hits[0]
    print(f"    [nav] human_click -> {best['t'][:44]!r}  href={best['h'][:50]}")
    before = set(ctx.pages)
    cs.human_click(start, start.locator(f"a[href='{best['h']}']").first)
    deadline = time.time() + wait
    while time.time() < deadline:
        for p in [q for q in ctx.pages if q not in before] + [start]:
            try:
                if OJV_HOST in (p.url or ""):
                    return p
            except Exception:
                pass
        start.wait_for_timeout(500)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=int, default=4, choices=sorted(PORTS))
    ap.add_argument("--corte", default="90")
    ap.add_argument("--desde", default="01/01/2026")
    ap.add_argument("--hasta", default="31/01/2026")
    ap.add_argument("--warmup", type=float, default=0.0,
                    help="seconds of scripted browsing before the first search (0 = none)")
    ap.add_argument("--keep", action="store_true", help="leave Chrome open if the search works")
    args = ap.parse_args()

    port = PORTS[args.worker]
    profile = os.path.join(os.environ["LOCALAPPDATA"], PROFILES[args.worker])
    if os.path.exists(profile):
        sys.exit(f"[ALTO] {profile} ya existe. Este test necesita un perfil VIRGEN: renombralo "
                 f"o usa otro --worker.")
    print(f"[1/5] lanzando Chrome · puerto {port} · perfil NUEVO {profile}")
    proc = launch(port, profile)
    if proc is None:
        print("\nVERDICT: NO-CHROME  (no encuentro chrome.exe)")
        return 4
    if not wait_cdp(port):
        print("\nVERDICT: NO-CHROME  (el puerto de depuracion nunca respondio)")
        return 4

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]
        start = None
        for _ in range(20):
            start = next((p for p in ctx.pages if "pjud.cl" in (p.url or "")), None)
            if start:
                break
            ctx.pages[0].wait_for_timeout(500) if ctx.pages else time.sleep(0.5)
        if start is None:
            print("\nVERDICT: NO-FORM  (Chrome abrio pero no hay pestana en pjud.cl)")
            return 1
        start.wait_for_timeout(3000)

        if args.warmup:
            print(f"[2/5] calentamiento scripted: {args.warmup:.0f}s")
            warm_up(start, args.warmup)
        else:
            print("[2/5] SIN calentamiento (prueba desnuda)")

        print("[3/5] click-through hacia la OJV")
        page = reach_ojv(ctx, start)
        if page is None:
            print("\nVERDICT: NO-FORM  (el click no abrio la OJV)")
            return 1
        page.wait_for_timeout(3000)
        page.on("dialog", lambda d: d.accept())

        print("[4/5] navegando al formulario de busqueda")
        # A WARM profile lands /home/ and auto-redirects to indexN.php (it already has a guest
        # session). A VIRGIN profile sees the /home/ LOGIN landing and must click the guest entry
        # button: <button onclick="accesoConsultaCausas()">Consulta causas</button>. That opens a
        # new tab on indexN.php with the Consulta Unificada console (recorded 2026-07-23).
        page.wait_for_timeout(1500)
        if not on_form(ctx):
            for sel in ("[onclick*='accesoConsultaCausas']", "[onclick*='accesoInvitado']"):
                btn = page.query_selector(sel)
                if not btn:
                    continue
                print(f"    [nav] click guest entry -> {sel}")
                before = set(ctx.pages)
                cs.human_click(page, sel, timeout=6000)
                # accesoConsultaCausas() navigates the SAME tab to indexN.php (seen 2026-07-23,
                # not a new tab), then the form loads a beat later. It also runs an invisible
                # reCAPTCHA first: a real human click passes silently (operator saw NO checkbox
                # and went "straight to the search"), but a COLD scripted click did NOT navigate
                # at all — the gate scored it too low. So this step is the one that decides
                # whether a worker can be born with zero human input; watch for it stalling on
                # /home/.
                for _ in range(30):
                    page.wait_for_timeout(500)
                    if _has_form(page) or "indexN.php" in (page.url or ""):
                        break
                    nt = next((p for p in ctx.pages
                               if p not in before and "indexN.php" in (p.url or "")), None)
                    if nt:
                        page = nt
                        break
                if "/home" in (page.url or "") and not _has_form(page):
                    print("    [nav] sigo en /home/ tras el click — la reCAPTCHA invisible de "
                          "'Consulta causas' no dejo pasar al perfil (scripted).")
                break
        # settle on whichever tab now holds the form
        formpg = next((p for p in ctx.pages if _has_form(p)), None)
        if formpg is None:
            print(f"\nVERDICT: NO-FORM  (llegue a {page.url[:56]} pero no aparece el formulario)")
            return 1
        page = formpg
        page.on("dialog", lambda d: d.accept())
        print("    abriendo el panel y estableciendo el formulario (teclado)")
        if not cs.open_fecha_panel(page):
            print("\nVERDICT: NO-FORM  (no puedo abrir 'Busqueda por Fecha')")
            return 1
        if not cs.establish_form_kbd(page, args.corte, args.desde, args.hasta):
            print("\nVERDICT: NO-FORM  (no pude establecer competencia/corte/fechas)")
            return 1
        tribs = page.eval_on_selector_all(
            "#fecTribunal option",
            "els=>els.filter(o=>o.value&&o.value!=='0').map(o=>({v:o.value,t:o.textContent.trim()}))")
        if not tribs:
            print("\nVERDICT: NO-FORM  (la corte no cargo tribunales)")
            return 1
        if not cs.select_tribunal_kbd(page, tribs[0]["v"]):
            print("\nVERDICT: NO-FORM  (no pude seleccionar el primer tribunal)")
            return 1

        print(f"[5/5] UNA busqueda: {tribs[0]['t'][:40]} · {args.desde}..{args.hasta}")
        ok = cs.fire_search(page)
        rows = 0
        try:
            rows = page.eval_on_selector_all("#dtaTableDetalleFecha tbody tr", "e=>e.length")
        except Exception:
            pass
        total = cs.total_registros(page)
        blocked = cs.waf_blocked(page)
        print(f"    filas={rows}  total_registros={total}  rechazo_F5={blocked}")

        if blocked:
            print("\nVERDICT: BLOCKED — el perfil virgen no pasa la primera busqueda.")
            print("  reCAPTCHA v3 es invisible y puntua el historial de la sesion: un perfil sin")
            print("  historia humana no tiene nada que puntuar. Si --warmup no lo cambia, el")
            print("  paso humano sigue siendo obligatorio (uno por sesion).")
            rc = 2
        elif ok and rows:
            print("\nVERDICT: OK — busqueda sin humano. Los workers pueden ser desechables.")
            print(f"  Sigue con: cdp_scrape.py --port {port} --corte {args.corte} --resume")
            rc = 0
        else:
            print("\nVERDICT: NO-FORM — la busqueda no devolvio filas y no hay pagina de rechazo.")
            print("  Ni bloqueo ni exito: mira la ventana antes de concluir nada.")
            rc = 1

        if rc != 0 or not args.keep:
            print("  (Chrome queda abierto para inspeccion; cierralo tu.)"
                  if args.keep or rc else "")
        browser.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
