"""inspect_detalle.py — one-causa read-only DOM map of the detalle modal, so the doc-filter
(Texto demanda / Anexos de la Causa / Certificados de envío / ebook at causa level; "Ingreso
Demanda" in cuaderno 1; all of cuaderno 2) can be wired to real selectors, not guesses.

Opens the FIRST displayed bank causa (trusted click) if no modal is open, then dumps:
  - the modal's HEADER controls (buttons/links/forms outside the historia/litigantes panes)
    -> reveals Texto demanda, Certificados de envío, ebook, Anexos de la Causa (anexoCausaCivil)
  - the #selCuaderno options (Book 1 / Book 2 names)
  - cuaderno-1 historia rows (folio/etapa/tramite/desc + has doc/anexo/geo)
    -> reveals how "Ingreso Demanda" is labelled
Read-only: no downloads. One detail open = ~1 causa of burn budget. Run on a HEALTHY profile.
"""
import json, sys
sys.path.insert(0, r"C:\Claude\felipe\pjud\scraper")
from playwright.sync_api import sync_playwright
import cdp_scrape as C

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9333

with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
    ctx = b.contexts[0]
    page = C.find_ojv_page(ctx)
    if not page:
        print("[no OJV page]"); raise SystemExit

    if not C.modal_open(page, "#modalDetalleCivil"):
        a = page.query_selector("#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']")
        if not a:
            print("No detail modal open and no results row. Do a manual search first."); raise SystemExit
        print("opening first displayed causa (trusted click)...")
        a.click()
        page.wait_for_function(
            "()=>{const m=document.querySelector('#modalDetalleCivil');return m&&m.innerText.indexOf('ROL')>=0;}",
            timeout=30000)
        page.wait_for_timeout(1000)

    print("\n=== HEADER CONTROLS (outside historia/litigantes/escritos panes) ===")
    ctrls = page.evaluate(r"""() => {
      const modal = document.querySelector('#modalDetalleCivil');
      if(!modal) return [];
      const panes = ['#historiaCiv','#litigantesCiv','#escritosCiv']
          .map(s=>modal.querySelector(s)).filter(Boolean);
      const inPane = el => panes.some(p=>p.contains(el));
      const out = [];
      modal.querySelectorAll("a[onclick], button, form, [data-toggle='modal'], [title]").forEach(el=>{
        if(inPane(el)) return;
        const inp = el.querySelector ? el.querySelector('input') : null;
        const t = (el.innerText||el.textContent||'').trim().slice(0,50);
        const oc = (el.getAttribute('onclick')||'').slice(0,70);
        const act = el.getAttribute('action')||'';
        const ttl = el.getAttribute('title')||'';
        if(!t && !oc && !act && !ttl) return;
        out.push({tag:el.tagName, text:t, title:ttl, onclick:oc, action:act,
                  input:(inp?inp.getAttribute('name'):'')});
      });
      return out;
    }""")
    for c in ctrls:
        print(f"  <{c['tag']}> text={c['text']!r} title={c['title']!r}")
        if c['onclick']: print(f"        onclick={c['onclick']!r}")
        if c['action']:  print(f"        form action={c['action']!r} input={c['input']!r}")

    print("\n=== CUADERNO OPTIONS (#selCuaderno) ===")
    for o in C.cuaderno_options(page):
        print(f"  {o['txt']!r}")

    print("\n=== CUADERNO 1 HISTORIA ROWS (folio | etapa | tramite | desc | doc/anexo/geo) ===")
    for h in C.parse_historia(page):
        flags = "".join([("D" if h.get("doc") else "-"), ("A" if h.get("anexo") else "-"),
                         ("G" if h.get("geo") else "-")])
        print(f"  [{flags}] folio={h['folio']!r:8} etapa={h['etapa'][:18]!r:20} "
              f"tramite={h['tramite'][:24]!r:26} desc={h['desc'][:34]!r}")

    print("\n(read-only — no downloads. Close the modal by hand or leave it.)")
