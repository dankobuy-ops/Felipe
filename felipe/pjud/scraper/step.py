"""One controlled step at a time on a given port. Operator-driven.

    python step.py <port> setup                  -> Civil + Todos + dates, report form state
    python step.py <port> trib "<name fragment>" -> select that tribunal (no search)
    python step.py <port> search                 -> click Buscar, report results
    python step.py <port> state                  -> report only, touch nothing

Verdicts use the network as ground truth (a consultaFechaCivil.php response proves the search
ran); the DOM alone cannot tell "empty" from "stale results left on screen".
"""
import sys, time, re
from pathlib import Path
sys.path.insert(0, r"C:\Claude\felipe\pjud\scraper")
sys.path.insert(0, str(Path(__file__).parent))
import cdp_scrape as C
from settle import Settler
from playwright.sync_api import sync_playwright

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9339
CMD = sys.argv[2] if len(sys.argv) > 2 else "state"
ARG = sys.argv[3] if len(sys.argv) > 3 else ""
DESDE, HASTA, CIVIL = "15/07/2026", "06/08/2026", "3"
net = []


def on_resp(r):
    if "pjud.cl" not in r.url or r.request.resource_type in ("image", "stylesheet", "font", "media"):
        return
    n = None
    try:
        n = len(r.body())
    except Exception:
        pass
    net.append({"u": r.url.split("/")[-1].split("?")[0], "n": n})


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
            p.wait_for_timeout(300)
    except Exception:
        pass


def report(p):
    print(f"  competencia : {p.eval_on_selector('#fecCompetencia','e=>e.value')}")
    print(f"  corte       : {p.eval_on_selector('#corteFec','e=>e.value')!r} "
          f"{p.eval_on_selector('#corteFec','e=>e.options[e.selectedIndex].text.trim()')}")
    n = p.eval_on_selector_all("#fecTribunal option",
                               "e=>e.filter(o=>o.value&&o.value!=='0').length")
    print(f"  tribunales  : {n}")
    print(f"  tribunal    : {p.eval_on_selector('#fecTribunal','e=>e.options[e.selectedIndex].text.trim()')[:44]}")
    print(f"  dates       : {p.eval_on_selector('#fecDesde','e=>e.value')} .. "
          f"{p.eval_on_selector('#fecHasta','e=>e.value')}")
    print(f"  form_ok     : {C.form_ok(p)}   total_registros: {C.total_registros(p)}")
    rf = sum(1 for fr in p.frames
             if "soporte" in ((fr.evaluate("()=>document.body?document.body.innerText:''") or "").lower()))
    print(f"  rejection frames: {rf}")


with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=60000)
    ctx = b.contexts[0]
    p = C.find_ojv_page(ctx)
    if p is None or not p.query_selector("#fecCompetencia"):
        sys.exit("no form on this port — walk in first")
    p.bring_to_front()
    p.on("response", on_resp)
    S = Settler(p)

    if CMD == "state":
        report(p)

    elif CMD == "setup":
        C.open_fecha_panel(p)
        if p.eval_on_selector("#fecCompetencia", "e=>e.value") != CIVIL:
            print("  setting Competencia = Civil")
            C.select_by_kbd(p, "#fecCompetencia", CIVIL)
            click_away(p)
            S.wait(need="document.querySelectorAll('#fecTribunal option').length>50",
                   quiet_ms=1200, timeout=90, label="all-tribunales")
        corte = p.eval_on_selector("#corteFec", "e=>e.value")
        if corte not in ("", "0"):
            print(f"  [!] corte is {corte!r}, not Todos — NOT changing it (that fires the burst)")
        for sel, val in (("#fecDesde", DESDE), ("#fecHasta", HASTA)):
            if p.eval_on_selector(sel, "e=>e.value") != val:
                print(f"  typing {sel} = {val}")
                C.type_date_kbd(p, sel, val)
                click_away(p)
        report(p)

    elif CMD == "trib":
        opts = p.eval_on_selector_all("#fecTribunal option",
                                      "e=>e.filter(o=>o.value&&o.value!=='0')"
                                      ".map(o=>({v:o.value,t:(o.textContent||'').trim()}))")
        hits = [o for o in opts if ARG.lower() in o["t"].lower()]
        if not hits:
            print(f"  no tribunal matching {ARG!r}. Sample:")
            for o in opts[:8]:
                print("   ", o["v"], o["t"][:44])
            sys.exit(1)
        if len(hits) > 1:
            print(f"  {len(hits)} matches for {ARG!r}:")
            for o in hits[:10]:
                print("   ", o["v"], o["t"][:44])
        tgt = hits[0]
        print(f"  selecting {tgt['v']} {tgt['t'][:44]}")
        ok = C.select_tribunal_kbd(p, tgt["v"])
        click_away(p)
        print(f"  selected: {ok} -> {p.eval_on_selector('#fecTribunal','e=>e.options[e.selectedIndex].text.trim()')[:44]}")
        report(p)

    elif CMD == "search":
        before = p.evaluate("""()=>{const t=document.querySelector('.loadTotalFec');
          const rows=[...document.querySelectorAll('#dtaTableDetalleFecha tbody tr')];
          return (t?t.innerText.trim():'')+'##'+rows.length;}""")
        net.clear()
        print(f"  clicking Buscar (tribunal: "
              f"{p.eval_on_selector('#fecTribunal','e=>e.options[e.selectedIndex].text.trim()')[:40]})")
        C.human_click(p, "#btnConConsultaFec")
        t0 = time.time()
        S.arm_observer()
        kind = "?"
        while True:
            el = time.time() - t0
            got = [r for r in net if "consultaFechaCivil" in r["u"] and r["n"] is not None]
            idle = (not C.page_busy(p)) and S.inflight == 0 and S.dom_quiet_ms() >= 8000
            if got and idle and el >= 2:
                has = p.evaluate("()=>{var e=document.querySelector('.loadTotalFec');"
                                 "return !!e && /Total de registros/i.test(e.innerText);}")
                if has:
                    kind = "results"; break
                if el >= 25:
                    kind = "empty"; break
            if el >= 180:
                kind = "stale" if not got else "timeout"; break
            p.wait_for_timeout(250)
        print(f"  verdict: {kind} after {el:.1f}s")
        print(f"  responses: {[(r['u'][:26], r['n']) for r in net if r['n'] is not None and (r['n']>400)][:6]}")
        report(p)
        if kind == "results":
            banks = C.page_bank_causas(p)
            print(f"  bank C-causas: {len(banks)}")
            for c in banks:
                print(f"    {c['rol']} | {c['fecha']} | {c['car'][:56]}")
    elif CMD == "open":
        banks = C.page_bank_causas(p)
        if not banks:
            sys.exit("no matching causas on the current results page — search first")
        pick = next((c for c in banks if ARG and ARG in c["rol"]), banks[0])
        print(f"  opening {pick['rol']} | {pick['car'][:52]}  (row {pick['i']})")
        net.clear()
        ok = C.human_click(p, p.locator("#dtaTableDetalleFecha tbody tr").nth(pick["i"])
                           .locator("a[onclick*='detalleCausaCivil']").first, timeout=8000)
        print(f"  click delivered: {ok}")
        t0 = time.time()
        S.arm_observer()
        opened = False
        while time.time() - t0 < 120:
            p.wait_for_timeout(400)
            try:
                if p.evaluate("(rol)=>{var m=document.querySelector('#modalDetalleCivil');"
                              "return !!m && m.innerText.indexOf('ROL')>=0"
                              " && m.innerText.indexOf(rol)>=0;}", pick["rol"]):
                    opened = True
                    break
            except Exception:
                pass
        el = time.time() - t0
        print(f"  modal open: {opened} after {el:.1f}s")
        rf = sum(1 for fr in p.frames
                 if "soporte" in ((fr.evaluate("()=>document.body?document.body.innerText:''") or "").lower()))
        print(f"  rejection frames: {rf}")
        print(f"  responses: {[(r['u'][:26], r['n']) for r in net if r['n'] is not None and r['n']>400][:8]}")
        if not opened:
            sys.exit(2)
        p.wait_for_timeout(800)
        hdr = C.parse_header(p)
        lit = C.parse_litigantes(p)
        cu = C.cuaderno_options(p) or []
        hist = C.parse_historia(p)
        for k, v in hdr.items():
            print(f"    {k:14}: {v}")
        print(f"    litigantes    : {len(lit)}")
        for l in lit:
            print(f"      {l.get('participante',''):8} {l.get('rut',''):12} {(l.get('nombre') or '')[:42]}")
        print(f"    cuadernos     : {[x['txt'][:34] for x in cu]}")
        print(f"    historia (c1) : {len(hist)} rows")
        ndoc = sum(1 for h in hist if h.get("doc") or h.get("anexo"))
        ngeo = sum(1 for h in hist if h.get("geo"))
        print(f"    rows with doc : {ndoc}     rows with georref: {ngeo}")
        hd = C.grab_header_docs(p) if hasattr(C, "grab_header_docs") else []
        print(f"    header docs   : {[h.get('key') for h in hd]}")
        print("  (nothing downloaded — read-only)")

    elif CMD == "close":
        if not C.modal_open(p, "#modalDetalleCivil"):
            print("  no detalle modal open")
        else:
            print("  closing detalle modal via its own control")
            C.close_modal(p, "#modalDetalleCivil")
            for _ in range(30):
                p.wait_for_timeout(300)
                if not C.modal_open(p, "#modalDetalleCivil"):
                    break
            backs = p.evaluate("()=>document.querySelectorAll('.modal-backdrop').length")
            print(f"  modal_open now: {C.modal_open(p,'#modalDetalleCivil')}  backdrops: {backs}")
        banks = C.page_bank_causas(p)
        print(f"  results table still shows {len(banks)} matching causas")
        for c in banks:
            print(f"    {c['rol']} | {c['fecha']} | {c['car'][:54]}")

    else:
        sys.exit(f"unknown command {CMD}")
