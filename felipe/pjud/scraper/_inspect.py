"""Connect to the user-driven Chrome (CDP 9222) and dump the current OJV page."""
import sys
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    pages = [p for c in b.contexts for p in c.pages]
    page = next((p for p in pages if "pjud.cl" in p.url), pages[0] if pages else None)
    if not page:
        print("no page"); sys.exit()
    print("URL:", page.url, "| TITLE:", page.title())

    # Active search tab
    active = page.eval_on_selector_all(
        ".nav-tabs li.active a, .nav-tabs a.active, a[aria-selected='true']",
        "els=>els.map(e=>(e.innerText||'').trim())")
    print("ACTIVE TAB:", active)

    # Visible inputs/selects (with a sample of select options)
    print("\n=== VISIBLE FIELDS ===")
    for f in page.eval_on_selector_all(
        "input:not([type=hidden]), select",
        "els=>els.filter(e=>e.offsetParent!==null).map(e=>({tag:e.tagName,type:e.type,id:e.id,name:e.name,ph:e.placeholder||'',val:(e.value||'').slice(0,30),nopt:(e.tagName==='SELECT'?e.options.length:0),opt0:(e.tagName==='SELECT'&&e.options.length?e.options[Math.min(1,e.options.length-1)].textContent.trim():'')}))"):
        print(" ", f)

    # Results table (if present)
    print("\n=== TABLES (headers + first row) ===")
    for t in page.eval_on_selector_all(
        "table",
        "els=>els.filter(e=>e.offsetParent!==null).map(e=>({headers:Array.from(e.querySelectorAll('thead th,thead td')).map(h=>h.innerText.trim()), firstRow:Array.from((e.querySelector('tbody tr')||{querySelectorAll:()=>[]}).querySelectorAll('td')).map(d=>d.innerText.trim().slice(0,40)), rows:e.querySelectorAll('tbody tr').length}))"):
        if t["headers"] or t["firstRow"]:
            print(" ", t)

    # Open modal?
    print("\n=== OPEN MODAL ===")
    modal = page.query_selector(".modal.show, .modal.in, #modalDetalleCivil:visible")
    if modal:
        print("modal id:", modal.get_attribute("id"))
        print("modal text (first 1500):", (modal.inner_text() or "")[:1500])
        # links inside modal (docs/anexos)
        links = page.eval_on_selector_all(
            ".modal.show a, .modal.in a, .modal.show [onclick]",
            "els=>els.map(e=>({txt:(e.innerText||'').trim().slice(0,30),href:e.getAttribute('href'),oc:(e.getAttribute('onclick')||'').slice(0,90)})).filter(x=>x.href||x.oc).slice(0,25)")
        print("modal links/onclicks:")
        for l in links: print("   ", l)
    else:
        print("(none open)")
