"""CENSUS pass: search every civil tribunal nationwide, open NOTHING.

Fully scripted, end to end: walk in from www.pjud.cl, dismiss the AVISO if present, enter
Consulta causas, build the form, sweep all ~230 tribunales with Corte = "Todos".

Why census-first: measured 2026-08-06, the search budget and the detail budget are separate and
detail is far scarcer — one session did 19 searches with no search-block, then died on its third
causa open. So enumerate everything cheaply first, then spend profiles only on detail.

NEVER touches #corteFec. It is the only control that fires a request on change, and walking it
with arrow keys fires one per step (ten in under a second to reach Concepción) — which produced
both the desynced tribunal lists and the blocks. Competencia=Civil is the single cascade we still
trigger, at startup. Tribunal is a leaf: no request, and one ArrowDown per step since we walk the
list in order.

EMPTY DETECTION (the thing this run also calibrates): today's live tribunales settled in
5.5-16.9 s, while phantom "ex" courts never settle and burned the full 60 s timeout each — about
two hours across the list. So we now declare empty early when the page is provably idle:
spinner idle AND no tracked in-flight request AND DOM quiet for EMPTY_QUIET ms AND at least
EMPTY_MIN_S elapsed. Every decision logs its elapsed time so the thresholds can be tuned from
real data rather than guessed.
"""
import sys, json, time, re
from pathlib import Path
sys.path.insert(0, r"C:\Claude\felipe\pjud\scraper")
sys.path.insert(0, str(Path(__file__).parent))
import cdp_scrape as C
import unattended_worker as uw
from settle import Settler
from playwright.sync_api import sync_playwright

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9337
START_AT = int(sys.argv[2]) if len(sys.argv) > 2 else 0
DESDE, HASTA = "15/07/2026", "06/08/2026"
CIVIL = "3"
HERE = Path(__file__).parent
CENSUS = HERE / "census.json"
SEARCH_GAP = 60.0
# Operator's call 2026-08-06: err on the side of waiting. Note the request rate is UNAFFECTED by
# these — the 60 s gap is measured from the search click, so faster detection only shortens idle
# time, never spacing. What longer waiting actually buys is protection against the silent failure
# that matters: calling a slow-but-live tribunal "empty" and recording a court as having no
# causas when it has some. Nothing downstream would ever flag that. Live tribunales settled in
# 5.5-16.9 s today, so a 25 s floor sits comfortably clear of the observed range.
EMPTY_MIN_S, EMPTY_QUIET, HARD_CAP = 25.0, 10000, 75.0
SHAPE_RE = re.compile(r"/[0-9a-f]{24,40}(\?|$)")
net = []


def note(m):
    s = time.strftime("%H:%M:%S")
    try:
        print(f"[{s}] {m}", flush=True)
    except UnicodeEncodeError:
        print(f"[{s}] {m.encode('ascii','replace').decode('ascii')}", flush=True)


def on_resp(r):
    if "pjud.cl" not in r.url or r.request.resource_type in ("image", "stylesheet", "font", "media"):
        return
    n, rej = None, False
    try:
        body = r.body()
        n = len(body)
        low = body.lower()
        rej = (b"numero de soporte" in low or b"requested url was rejected" in low
               or b"support id" in low)
    except Exception:
        pass
    net.append({"u": r.url.split("/")[-1].split("?")[0], "n": n, "rej": rej})


def click_away(p):
    try:
        pt = p.evaluate("""()=>{
          const bad = e => !e || ['A','BUTTON','INPUT','SELECT','TEXTAREA','LABEL','IMG','IFRAME','OPTION']
                                  .includes(e.tagName)
                          || e.getAttribute('onclick')
                          || e.closest('a,button,input,select,textarea,label,[onclick],.modal');
          for (let y=140; y<innerHeight-90; y+=35)
            for (let x=30; x<innerWidth-30; x+=55) {
              const el=document.elementFromPoint(x,y);
              if (el && !bad(el)) return {x:x,y:y};
            }
          return null; }""")
        if pt:
            C._human_pointer(p, pt["x"], pt["y"])
            p.wait_for_timeout(250)
    except Exception:
        pass


def rej_frames(p):
    n = 0
    for fr in p.frames:
        try:
            t = fr.evaluate("()=>document.body?document.body.innerText:''") or ""
        except Exception:
            continue
        if "soporte" in t.lower():
            n += 1
    return n


def find_form(ctx):
    """Find the page holding the search form, tolerating navigation.

    query_selector THROWS "Execution context was destroyed" while a page is navigating — which
    is exactly when we are polling for the form after the entry click. Unguarded, that kills the
    whole run at the moment the click SUCCEEDS.
    """
    for q in list(ctx.pages):
        try:
            if q.query_selector("#fecCompetencia"):
                return q
        except Exception:
            pass
    return None


def walk_in(ctx):
    """www.pjud.cl -> OJV /home/ -> dismiss AVISO -> Consulta causas -> form. Scripted."""
    p = find_form(ctx)
    if p:
        return p
    # ★ Close stale OJV tabs FIRST. Each failed walk-in used to leave another /home/ behind, and
    # human_click drives REAL MOUSE COORDINATES — which land on whatever tab is actually visible.
    # With two /home/ tabs open, retries were clicking those coordinates on the wrong tab, so
    # three "attempts" could fail without the button ever being touched. That also undermines the
    # "gate 1 is flaky" reading: the clicks may simply never have arrived.
    for q in list(ctx.pages):
        if "oficinajudicialvirtual" in (q.url or ""):
            try:
                q.close()
            except Exception:
                pass
    time.sleep(1.5)
    start = next((q for q in ctx.pages if "pjud.cl" in (q.url or "")), None) or ctx.new_page()
    try:
        start.goto("https://www.pjud.cl/", wait_until="domcontentloaded")
    except Exception:
        pass
    start.bring_to_front()
    start.wait_for_timeout(4000)
    page = uw.reach_ojv(ctx, start, wait=25.0)
    if page is None:
        note("could not reach the OJV"); return None
    page.bring_to_front()
    page.wait_for_timeout(4000)
    try:
        body = page.evaluate("()=>document.body?document.body.innerText.slice(0,300):''") or ""
    except Exception:
        body = ""
    if "code is in the image" in body.lower():
        note("*** TIER-3 IMAGE CAPTCHA — needs the operator. Not attempting to bypass. ***")
        return None
    # AVISO comes and goes (operator: "it comes and goes") — always check, never assume
    try:
        if page.evaluate("()=>{const m=document.getElementById('no-disponible');"
                         "return !!m && getComputedStyle(m).display!=='none';}"):
            note("dismissing #no-disponible AVISO")
            C.human_click(page, page.locator("#no-disponible button[data-dismiss='modal']").first,
                          timeout=6000)
            for _ in range(40):
                page.wait_for_timeout(300)
                if not page.evaluate("()=>{const m=document.getElementById('no-disponible');"
                                     "return !!m && getComputedStyle(m).display!=='none';}"):
                    break
    except Exception:
        pass
    # GATE 1 IS FLAKY, NOT REFUSING. Every fresh profile today failed the first entry click and
    # succeeded on a retry seconds later, with nothing changed. Treating one timeout as a verdict
    # produced several wrong "needs a human / reCAPTCHA refused" conclusions. So: retry, and only
    # give up after several honest attempts.
    for attempt in range(1, 4):
        sel = next((s for s in ("[onclick*='accesoConsultaCausas']",
                                "[onclick*='accesoInvitado']") if page.query_selector(s)), None)
        if sel is None:
            note("  no guest-entry button on the page")
            break
        # ★ THE BUG THAT FAKED EVERY "GATE-1 REFUSED" TODAY: /home/ has TWO
        # accesoConsultaCausas buttons. Playwright locators are strict, so passing the SELECTOR
        # to human_click makes bounding_box() throw ("resolved to 2 elements"); human_click
        # catches it, falls through to .click() which throws identically, and returns False.
        # No click is ever delivered — and the caller reports "no form appeared", i.e. a gate-1
        # refusal, for a click that never happened. Pick ONE element, and one that hit-tests.
        page.bring_to_front()            # real mouse coords hit the VISIBLE tab, not this object
        page.wait_for_timeout(800)
        cov = page.evaluate("""(s)=>{
          return [...document.querySelectorAll(s)]
            .map((e,i)=>({e:e,r:e.getBoundingClientRect(),i:i}))
            .filter(o=>o.r.width>0&&o.r.height>0)
            .map(o=>{const t=document.elementFromPoint(o.r.x+o.r.width/2,o.r.y+o.r.height/2);
                     return {i:o.i, hit: !!t && (t===o.e||o.e.contains(t))};});
        }""", sel)
        pick = next((c["i"] for c in cov if c["hit"]), None)
        if pick is None:
            note(f"  entry button covered ({cov}) — not clicking")
            page.wait_for_timeout(5000)
            continue
        note(f"human_click guest entry {sel} nth({pick}) (attempt {attempt}/3)")
        ok = C.human_click(page, page.locator(sel).nth(pick), timeout=8000)
        note(f"  click delivered: {ok}")
        for _ in range(90):                      # 45 s per attempt
            page.wait_for_timeout(500)
            fp = find_form(ctx)
            if fp:
                note(f"  entered on attempt {attempt}")
                return fp
        # re-check for the AVISO: it "comes and goes" and can appear between attempts
        try:
            if page.evaluate("()=>{const m=document.getElementById('no-disponible');"
                             "return !!m && getComputedStyle(m).display!=='none';}"):
                note("  AVISO reappeared - dismissing")
                C.human_click(page, page.locator("#no-disponible button[data-dismiss='modal']").first,
                              timeout=6000)
                page.wait_for_timeout(1500)
        except Exception:
            pass
        note(f"  no form after attempt {attempt}; pausing before retry")
        page.wait_for_timeout(20000)
    return find_form(ctx)


def results_sig(p):
    """Fingerprint of what the results area currently shows."""
    try:
        return p.evaluate("""()=>{
          const t=document.querySelector('.loadTotalFec');
          const tot=t?t.innerText.replace(/\\s+/g,' ').trim():'';
          const rows=[...document.querySelectorAll('#dtaTableDetalleFecha tbody tr')];
          const head=rows.slice(0,3)
              .map(r=>r.innerText.replace(/\\s+/g,' ').trim().slice(0,70)).join('|');
          return tot+'##'+rows.length+'##'+head;
        }""") or ""
    except Exception:
        return ""


def wait_results(p, S, before):
    """('results'|'empty'|'stale'|'timeout', elapsed_s) — freshness is PROVEN, not assumed.

    ⚠️ The previous version asked "does .loadTotalFec contain 'Total de registros'?" — which is
    TRUE from the PREVIOUS search, because the site leaves the old results on screen while the
    new one runs. It therefore returned at 0.0 s every time and recorded each tribunal with the
    PREVIOUS tribunal's totals: 35 entries, zero empties, phantom 'ex' courts credited with bank
    causas. Exactly the trap HANDOFF_CDP warns about ("never judge readiness by the results
    table"). Now we snapshot before the click and require the fingerprint to CHANGE.

    A search that finds nothing also changes the fingerprint (the table clears), so empty is a
    positive observation too — not merely the absence of one. If nothing changes at all we
    return 'stale' and record NOTHING, because unverifiable data is worse than a gap.
    """
    t0 = time.time()
    S.arm_observer()
    while True:
        el = time.time() - t0
        # GROUND TRUTH: a consultaFechaCivil.php response arriving AFTER this click proves the
        # search actually ran. `net` is cleared immediately before the click.
        #
        # The DOM-fingerprint version could not tell empty->empty apart: an empty tribunal
        # clears the table, so two empties in a row leave it identical and "changed" never
        # becomes true. That burned the full hard cap and would have dropped the second of
        # every consecutive-empty pair from the census — silent gaps in exactly the phantom-
        # heavy regions where empties cluster. The network does not have that ambiguity.
        got_resp = [r for r in net if "consultaFechaCivil" in r["u"] and r["n"] is not None]
        idle = (not C.page_busy(p)) and S.inflight == 0 and S.dom_quiet_ms() >= EMPTY_QUIET
        if got_resp and idle and el >= 2.0:
            sig = results_sig(p)
            has_total = "total de registros" in sig.lower()
            if has_total:
                return "results", el
            if el >= EMPTY_MIN_S:          # operator's rule: never rush an "empty"
                return "empty", el
        if el >= HARD_CAP:
            # ★ Do NOT give up while the SITE says it is still working. 2026-08-06: two
            # consecutive STALEs looked like a block, but the probe showed zero rejection
            # frames, Buscar disabled-because-searching, and page_busy TRUE — a request
            # genuinely in flight. The site had simply slowed from 11-35 s to over 75 s, and
            # we were discarding valid slow searches. Extend while its own spinner is up.
            if C.page_busy(p) and el < HARD_CAP * 3:
                p.wait_for_timeout(500)
                continue
            # no response at all = we cannot prove the search ran; record NOTHING
            return ("stale" if not got_resp else "timeout"), el
        p.wait_for_timeout(250)


with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=60000)
    ctx = b.contexts[0]
    p = walk_in(ctx)
    if p is None:
        raise SystemExit("could not reach the form")
    note(f"in: {p.url[:60]}")
    p.on("response", on_resp)
    S = Settler(p)
    C.open_fecha_panel(p)

    if p.eval_on_selector("#fecCompetencia", "e=>e.value") != CIVIL:
        note("Competencia = Civil")
        C.select_by_kbd(p, "#fecCompetencia", CIVIL)
        click_away(p)
        S.wait(need="document.querySelectorAll('#fecTribunal option').length>50",
               quiet_ms=1200, timeout=60, label="all-tribunales")
    corte = p.eval_on_selector("#corteFec", "e=>e.value")
    if corte not in ("", "0"):
        note(f"[!] corte={corte}, expected Todos — refusing to change it (that is the burst)")
        raise SystemExit(2)
    for sel, val in (("#fecDesde", DESDE), ("#fecHasta", HASTA)):
        if p.eval_on_selector(sel, "e=>e.value") != val:
            C.type_date_kbd(p, sel, val)
            click_away(p)

    tl = p.eval_on_selector_all("#fecTribunal option",
                                "e=>e.filter(o=>o.value&&o.value!=='0')"
                                ".map(o=>({v:o.value,t:(o.textContent||'').trim()}))")
    note(f"tribunales={len(tl)} corte=Todos dates "
         f"{p.eval_on_selector('#fecDesde','e=>e.value')}..{p.eval_on_selector('#fecHasta','e=>e.value')}")
    if len(tl) < 50:
        raise SystemExit("not the national list — aborting")

    cen = json.loads(CENSUS.read_text(encoding="utf-8")) if CENSUS.exists() else {}
    last = 0.0
    for idx in range(START_AT, len(tl)):
        tgt = tl[idx]
        if tgt["v"] in cen:
            continue
        if not C.select_tribunal_kbd(p, tgt["v"]):
            note(f"  [{idx}] {tgt['v']} could not select — skip")
            continue
        click_away(p)
        if last:
            gap = SEARCH_GAP - (time.time() - last)
            if gap > 0:
                time.sleep(gap)
        net.clear()
        before_sig = results_sig(p)          # what is on screen BEFORE this search
        C.human_click(p, "#btnConConsultaFec")
        last = time.time()
        kind, el = wait_results(p, S, before_sig)
        rf = rej_frames(p)
        hard = [r for r in net if r["rej"] and r["n"] is not None and 100 < r["n"] < 1000]
        if rf or hard:
            note(f"  *** BLOCKED at idx {idx} ({tgt['v']} {tgt['t'][:28]}) rejF={rf} — resume idx {idx}")
            break
        if kind in ("stale", "timeout"):
            note(f"  [{idx}/{len(tl)}] {tgt['v']:>5} {tgt['t'][:34]:36} {kind.upper()} after {el:.1f}s"
                 f" - results never proved fresh, NOT recording")
            continue
        total = C.total_registros(p) if kind == "results" else None
        banks = C.page_bank_causas(p) if total is not None else []
        note(f"  [{idx}/{len(tl)}] {tgt['v']:>5} {tgt['t'][:34]:36} {kind:7} {el:5.1f}s "
             f"total={total} banks={len(banks)}")
        cen[tgt["v"]] = {"idx": idx, "name": tgt["t"], "kind": kind, "elapsed": round(el, 1),
                         "total": total, "banks": len(banks),
                         "causas": [{"rol": c["rol"], "car": c["car"], "fecha": c["fecha"]}
                                    for c in banks]}
        CENSUS.write_text(json.dumps(cen, ensure_ascii=False, indent=2), encoding="utf-8")

    res = [v for v in cen.values() if v["kind"] == "results"]
    emp = [v for v in cen.values() if v["kind"] == "empty"]
    note(f"DONE. tribunales={len(cen)} withResults={len(res)} empty={len(emp)} "
         f"causas={sum(v['banks'] for v in cen.values())}")
    if res:
        note(f"  results elapsed: min={min(v['elapsed'] for v in res)} "
             f"max={max(v['elapsed'] for v in res)}")
    if emp:
        note(f"  empty  elapsed: min={min(v['elapsed'] for v in emp)} "
             f"max={max(v['elapsed'] for v in emp)}")
