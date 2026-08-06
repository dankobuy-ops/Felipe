"""Close the #no-disponible popup, then enter Consulta causas — real mouse only.

Nothing here does anything a person at the keyboard could not: every click is cdp_scrape.
human_click (arc + dwell + real press duration) on the element's true screen coordinates. No
JS .click(), no dispatchEvent, no navigating straight to indexN.php.

This is also the HONEST gate-1 test. The earlier reentry_test.py reported GATE-1-BLOCKED
without ever clicking: its guest-entry selector found nothing (the popup had swallowed the
button) and the verdict fired purely on "no form appeared". Here the click is attempted
explicitly and reported separately from the outcome, so a miss cannot masquerade as a refusal.
"""
import sys, time
sys.path.insert(0, r"C:\Claude\felipe\pjud\scraper")
import cdp_scrape as cs
from playwright.sync_api import sync_playwright

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9333

COVER_JS = """(sel)=>{
  const els=[...document.querySelectorAll(sel)].map(e=>({e,r:e.getBoundingClientRect()}))
      .filter(o=>o.r.width>0&&o.r.height>0);
  return els.map((o,i)=>{
    const t=document.elementFromPoint(o.r.x+o.r.width/2,o.r.y+o.r.height/2);
    return {i, x:Math.round(o.r.x), y:Math.round(o.r.y),
            hit: !!t && (t===o.e||o.e.contains(t)),
            top: t?(t.id||t.className||t.tagName):null};});
}"""

with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
    ctx = b.contexts[0]
    page = next((p for p in ctx.pages if "oficinajudicial" in (p.url or "")), None)
    if page is None:
        sys.exit("no OJV tab")
    page.bring_to_front()
    print(f"url: {page.url}")

    # ── 1) close the popup by clicking its Cerrar button, like a person ──────────────
    modal_up = page.evaluate(
        "()=>{const m=document.getElementById('no-disponible');"
        " return !!m && getComputedStyle(m).display!=='none';}")
    print(f"popup #no-disponible visible: {modal_up}")
    if modal_up:
        cerrar = page.locator("#no-disponible button[data-dismiss='modal']").first
        print(f"  human_click -> Cerrar  ({cerrar.count()} match)")
        cs.human_click(page, cerrar, timeout=6000)
        # Poll until the modal AND its backdrop are gone AND body drops modal-open. Sampling
        # once right after the click caught the backdrop mid-fade and reported "still covered".
        for _ in range(40):
            page.wait_for_timeout(300)
            st = page.evaluate("""()=>{const m=document.getElementById('no-disponible');
              return {up: !!m && getComputedStyle(m).display!=='none',
                      backs: document.querySelectorAll('.modal-backdrop').length,
                      open: document.body.classList.contains('modal-open')};}""")
            if not st["up"] and st["backs"] == 0 and not st["open"]:
                break
        print(f"  after close: modal={st['up']} backdrops={st['backs']} modal-open={st['open']}")

    # ── 2) is the entry button now actually reachable? ───────────────────────────────
    cov = page.evaluate(COVER_JS, "[onclick*='accesoConsultaCausas']")
    for c in cov:
        print(f"  entry[{c['i']}] at ({c['x']},{c['y']}) hit={c['hit']} top={c['top']!r}")
    target = next((c for c in cov if c["hit"]), None)
    if target is None:
        print("\nRESULT: still covered — not clicking (that is the rule that avoids the block).")
        raise SystemExit(3)

    # ── 3) GATE 1, clicked for real ──────────────────────────────────────────────────
    btn = page.locator("[onclick*='accesoConsultaCausas']").nth(target["i"])
    print(f"  human_click -> Consulta causas (instance {target['i']})")
    clicked = cs.human_click(page, btn, timeout=8000)
    print(f"  click delivered: {clicked}")
    if not clicked:
        print("\nRESULT: CLICK-REFUSED — human_click declined (covered). Not a gate-1 verdict.")
        raise SystemExit(4)

    # Poll for the FORM, not just the URL. Breaking on the URL and then reading the form in the
    # same instant reported GATE-1-REFUSED for a navigation that had in fact succeeded — the
    # form renders a beat after indexN.php loads.
    before, formpg = page.url, None
    for _ in range(40):
        page.wait_for_timeout(500)
        formpg = next((p for p in ctx.pages if p.query_selector("#fecCompetencia")), None)
        if formpg is not None:
            break
    print(f"\n  url before: {before[:60]}")
    print(f"  url after : {page.url[:60]}")
    if formpg is not None:
        print("RESULT: ENTERED — scripted click passed gate 1, form present.")
        rej = sum(1 for fr in formpg.frames
                  if "soporte" in ((fr.evaluate("()=>document.body?document.body.innerText:''")
                                    or "").lower()))
        print(f"  rejection frames: {rej}")
        print(f"  form_ok: {cs.form_ok(formpg)}  (False just means the accordion is collapsed)")
    else:
        print("RESULT: NO-FORM after 20s — click delivered but no search form appeared.")
