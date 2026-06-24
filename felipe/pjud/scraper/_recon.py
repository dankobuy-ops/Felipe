"""Recon the OJV Consulta Unificada — reach it via the home button, dump the form."""
import sys
from playwright.sync_api import sync_playwright

HOME = "https://oficinajudicialvirtual.pjud.cl/home/index.php"
HEADLESS = "--headed" not in sys.argv

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=HEADLESS)
    ctx = b.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
        locale="es-CL", viewport={"width": 1400, "height": 1000})
    page = ctx.new_page()
    page.goto(HOME, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(2000)

    print("clicking 'Consulta causas'…")
    popup = None
    try:
        with ctx.expect_page(timeout=8000) as pinfo:
            page.click("text=Consulta causas")
        popup = pinfo.value
    except Exception:
        pass
    target = popup or page
    target.wait_for_load_state("domcontentloaded")
    target.wait_for_timeout(4000)
    print("AFTER CLICK -> URL:", target.url, "| TITLE:", target.title())

    print("\n=== TABS (search modes) ===")
    for t in target.eval_on_selector_all(
        ".nav-tabs a, ul.nav a, a[data-toggle='tab']",
        "els=>els.map(e=>({txt:(e.innerText||'').trim(), href:e.getAttribute('href'), id:e.id}))"):
        if t["txt"]:
            print(" ", t)

    print("\n=== INPUTS/SELECTS ===")
    for f in target.eval_on_selector_all(
        "input, select",
        "els=>els.map(e=>({tag:e.tagName,type:e.type,id:e.id,name:e.name,ph:e.placeholder||'',opts:(e.tagName==='SELECT'?Array.from(e.options).slice(0,5).map(o=>o.textContent.trim()):undefined)}))"):
        if f.get("id") or f.get("name"):
            print(" ", f)

    print("\n=== BUTTONS ===")
    for x in target.eval_on_selector_all(
        "button, input[type=button], input[type=submit], a.btn",
        "els=>els.map(e=>({txt:(e.innerText||e.value||'').trim(),id:e.id,oc:(e.getAttribute('onclick')||'').slice(0,60)})).filter(x=>x.txt)"):
        print(" ", x)

    target.screenshot(path="pjud/screenshots/_recon_form.png", full_page=True)
    print("\nscreenshot -> pjud/screenshots/_recon_form.png")
    ctx.close()
