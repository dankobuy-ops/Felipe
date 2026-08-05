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

# ⚠️ The rejection page is served in the browser's language. Ours is SPANISH, and until
# 2026-08-05 this tuple was English-only — so a real block (4 rejection frames, 2 support IDs,
# Buscar stuck disabled) read as "THROTTLED". Keep BOTH languages. The Spanish page reads:
#     [X] CLOSE  .  (2)  .   Su numero de soporte es : <11224827243296953039>   [Go Back]
# Note it is unaccented ("numero"), but match the accented form too in case that varies.
REJECT_MARKERS = ("requested URL was rejected", "Support ID", "consult with your administrator",
                  "numero de soporte", "número de soporte", "Go Back")

# Language-independent tells, for when F5 changes the wording again:
#   TSBrPFrame_* / TSPD_* iframes are Shape's own client-side challenge frames, and one of them
#   parks itself ON TOP of the Buscar button (elementFromPoint returns it, so human_click's
#   hit-test correctly refuses to click — which is why a block also shows up as "objetivo tapado").
CHALLENGE_FRAME_RE = r"TSBrPFrame|TSPD_.*chlg|cs_chlg"


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

        # Prefer the tab that actually holds the search form. A leftover document tab
        # (docu.php / docCertificadoDemanda.php from a manual download) is also on the OJV
        # domain, and picking it reports "no #fecTribunal / 0 rows" -> a bogus THROTTLED
        # verdict while the real session is perfectly healthy (seen 2026-07-22).
        ojv = None
        for ctx in browser.contexts:
            for pg in ctx.pages:
                try:
                    if pg.query_selector("#fecTribunal"):
                        ojv = pg
                        break
                except Exception:
                    pass
            if ojv:
                break
        if ojv is None:
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    if "oficinajudicialvirtual" in pg.url:
                        ojv = pg
                        break
                if ojv:
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

        # Is a modal currently open? Decides whether a rejection page is live or just trapped.
        modal_open = False
        for msel in ("#modalDetalleCivil", "#modalReceptorCivil"):
            try:
                if ojv.eval_on_selector(
                        msel, "e=>e && (e.classList.contains('show')"
                              "||e.classList.contains('in')||getComputedStyle(e).display!=='none')"):
                    modal_open = True
                    print(f"modal abierto   : {msel}")
            except Exception:
                pass

        # --- language-independent block tell: F5 parks a challenge iframe ON Buscar ---
        # Wording changes with the browser locale (that is how the English-only marker list
        # missed a real block on 2026-08-05), but this does not: Shape injects a
        # TSBrPFrame_cs_chlg_* iframe and it covers #btnConConsultaFec, which is left disabled.
        challenge = None
        try:
            challenge = ojv.evaluate(
                """(re)=>{
                  const rx = new RegExp(re);
                  const named = [...document.querySelectorAll('iframe,div')]
                      .map(e=>e.id||'').filter(id=>rx.test(id));
                  const b = document.querySelector('#btnConConsultaFec');
                  let cover = null, disabled = null;
                  if (b) { disabled = b.disabled;
                    const r = b.getBoundingClientRect();
                    const t = document.elementFromPoint(r.x+r.width/2, r.y+r.height/2);
                    cover = t ? (t.id || t.className || t.tagName) : null; }
                  return {frames: named, buscar_disabled: disabled, buscar_covered_by: cover};
                }""", CHALLENGE_FRAME_RE)
        except Exception:
            pass
        challenged = False
        if challenge:
            import re as _re
            covered_by_f5 = bool(challenge.get("buscar_covered_by")
                                 and _re.search(CHALLENGE_FRAME_RE, challenge["buscar_covered_by"]))
            challenged = bool(challenge.get("frames")) or covered_by_f5
            if challenged:
                print(f"F5 challenge    : frames={challenge['frames']} "
                      f"buscar_disabled={challenge['buscar_disabled']} "
                      f"covered_by={challenge['buscar_covered_by']!r}")

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
        # A rejection page inside an OPEN modal is usually STALE: one causa open went wrong,
        # the modal never closed, and the dead page is just sitting there. That is not a burned
        # profile — closing the modal fixes it. Reporting it as BLOCKED-DETAIL cost several
        # perfectly good profiles on 2026-07-22, so say which case this is.
        if modal_open:
            print("\nVERDICT: STUCK-MODAL (probablemente NO bloqueado)")
            print("  Hay una pagina de rechazo DENTRO de un modal abierto. Casi siempre es un")
            print("  modal viejo que no se cerro, no un bloqueo vivo: mientras siga abierto, su")
            print("  backdrop tapa Buscar y todo 'falla'.")
            print("  FIX: cierra el modal (Escape) o recarga; cdp_scrape ya lo hace solo")
            print("       (clear_stuck_modal). Reintenta ANTES de quemar el perfil.")
            print("  Para confirmar que la sesion vive:  cdp_scrape.py --no-search --max-causas 1")
            return 4
        print("\nVERDICT: BLOCKED-DETAIL")
        print("  The WAF is rejecting detail opens. Search may still work — that is the tell.")
        print("  FIX: close Chrome, rename %LOCALAPPDATA%\\pjud_cdp to pjud_cdp.burned-<date>,")
        print("       reopen Abrir_CDP.cmd, re-pass the CAPTCHA. A new IP alone will NOT help.")
        return 1
    if challenged:
        # No rejection text matched, but F5's own challenge frame is sitting on Buscar. Trust
        # the structure over the wording — this is the case the marker list will keep missing.
        print("\nVERDICT: BLOCKED-CHALLENGE")
        print("  No hay texto de rechazo reconocido, pero F5 tiene su iframe de desafio")
        print("  (TSBrPFrame/cs_chlg) encima de Buscar, que quedo disabled. Es un bloqueo.")
        print("  FIX: cierra la pestana OJV y reentra desde www.pjud.cl; si vuelve a bloquear")
        print("       enseguida, el perfil esta gastado -> perfil nuevo + warm-up manual.")
        return 1
    if rows == 0:
        # No rows + no tribunal selected = nobody has searched yet (fresh tab, or a reload reset
        # the form). Calling that THROTTLED and advising a fresh session condemns a perfectly
        # healthy profile — exactly what happened to worker 3 on 2026-07-23, which had zero
        # rejection frames and was simply sitting on a reloaded page.
        if not trib or trib.startswith("Seleccione") or trib.startswith("(no"):
            print("\nVERDICT: SIN-BUSQUEDA (sesion sana, sin bloqueo)")
            print("  No hay rechazo F5 y no hay tribunal seleccionado: aqui todavia no se ha")
            print("  buscado (pestana nueva, o una recarga reseteo el formulario).")
            print("  Si la recarga dejo el panel 'Busqueda por Fecha' colapsado, el scraper lo")
            print("  reabre solo con --corte (open_fecha_panel).")
            return 0
        print("\nVERDICT: THROTTLED (or no search run yet)")
        print("  No rejection page, but no results either. If you HAVE searched, this is the")
        print("  throttle symptom — stop and take a fresh session.")
        return 1
    print("\nVERDICT: HEALTHY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
