"""Dump the open Detalle Causa Civil modal: cuaderno options, doc links, all tab-panes."""
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    pages = [p for c in b.contexts for p in c.pages]
    page = next((p for p in pages if "pjud.cl" in p.url), pages[0])
    m = page.query_selector("#modalDetalleCivil")
    if not m:
        print("modal not found"); raise SystemExit

    print("=== selCuaderno options ===")
    print(page.eval_on_selector_all("#selCuaderno option",
        "els=>els.map(e=>({txt:e.textContent.trim(), val:(e.value||'').slice(0,25)}))"))

    print("\n=== header doc links (Texto Demanda / Anexos / Certificado / Ebook) ===")
    print(page.eval_on_selector_all(
        "#modalDetalleCivil a, #modalDetalleCivil [onclick]",
        "els=>els.map(e=>({txt:(e.innerText||'').trim().slice(0,25),href:e.getAttribute('href'),oc:(e.getAttribute('onclick')||'').slice(0,120)})).filter(x=>x.oc||(x.href&&x.href!=='#')).slice(0,12)"))

    print("\n=== tab panes (id + table headers + first row) ===")
    panes = page.eval_on_selector_all(
        "#modalDetalleCivil .tab-pane",
        """els=>els.map(e=>({
            id:e.id,
            headers:Array.from(e.querySelectorAll('table thead th,table thead td')).map(h=>h.innerText.trim()),
            firstRow:Array.from((e.querySelector('table tbody tr')||{querySelectorAll:()=>[]}).querySelectorAll('td')).map(d=>d.innerText.trim().slice(0,40)),
            nrows:e.querySelectorAll('table tbody tr').length
        }))""")
    for p in panes:
        print(" ", p)

    print("\n=== one historia row's Doc cell innerHTML (to see the download link) ===")
    print(page.eval_on_selector_all(
        "#modalDetalleCivil .tab-pane table tbody tr",
        "els=>els.slice(0,4).map(r=>{const td=r.querySelectorAll('td'); return {folio:(td[0]?td[0].innerText.trim():''), docHTML:(td[1]?td[1].innerHTML.trim().slice(0,200):''), anexoHTML:(td[2]?td[2].innerHTML.trim().slice(0,150):'')}})"))
