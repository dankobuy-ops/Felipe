"""nav_record.py — watch a human click through www.pjud.cl -> the OJV, and record EXACTLY which
link did it. Read-mostly: it injects one capturing click-listener (Runtime.evaluate, proven
innocent for this site) and otherwise only polls tab URLs.

    python nav_record.py --port 9335

Prints, live:
  - each anchor the human clicks on the pjud.cl page (text / href / onclick)
  - every new tab and every URL change
So when the operator lands on the Busqueda-por-Fecha form, the log shows the precise link the
auto-navigator should have chosen. The auto-navigator picked 'Acceso directo para ingreso de
causas y escritos' (the e-filing portal) instead of Consulta Causas; this settles which anchor
is correct instead of guessing by regex.
"""
import argparse
import time

from playwright.sync_api import sync_playwright

INJECT = """
() => {
  if (window.__navrec) return 'already';
  window.__navrec = [];
  document.addEventListener('click', (e) => {
    let a = e.target;
    while (a && a.tagName !== 'A' && a.tagName !== 'BUTTON') a = a.parentElement;
    if (!a) { window.__navrec.push({t:'(no-anchor)', tag:e.target.tagName}); return; }
    window.__navrec.push({
      t:(a.textContent||'').trim().slice(0,70),
      h:a.getAttribute('href')||'',
      oc:(a.getAttribute('onclick')||'').slice(0,120),
      id:a.id||'', cls:(a.className||'').slice(0,40)});
  }, true);
  return 'armed';
}
"""


def arm(page):
    try:
        return page.evaluate(INJECT)
    except Exception as e:
        return f"(arm failed: {str(e)[:40]})"


def drain(page):
    try:
        got = page.evaluate("()=>{const r=window.__navrec||[]; window.__navrec=[]; return r;}")
    except Exception:
        return []
    return got or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9335)
    ap.add_argument("--secs", type=float, default=600.0)
    args = ap.parse_args()

    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        ctx = b.contexts[0]
        armed, urls = set(), {}

        def refresh():
            for p in ctx.pages:
                if id(p) not in armed:
                    st = arm(p)
                    armed.add(id(p))
                    print(f"[arm] {st:10} {(p.url or '')[:70]}", flush=True)
                u = p.url or ""
                if urls.get(id(p)) != u:
                    print(f"[url] {u[:100]}", flush=True)
                    urls[id(p)] = u
                    if "oficinajudicialvirtual" in u:
                        try:
                            has = bool(p.query_selector("#fecCompetencia"))
                            print(f"      -> #fecCompetencia presente: {has}", flush=True)
                        except Exception:
                            pass

        ctx.on("page", lambda p: print(f"[new-tab] {(p.url or '')[:70]}", flush=True))
        print(f"[nav_record] escuchando puerto {args.port} · {int(args.secs)}s. "
              f"Haz el click-through ahora.", flush=True)
        deadline = time.time() + args.secs
        while time.time() < deadline:
            refresh()
            for p in list(ctx.pages):
                for ev in drain(p):
                    if ev.get("t") or ev.get("h") or ev.get("oc"):
                        print(f"[CLICK] {ev.get('t','')[:52]!r:54} "
                              f"href={ev.get('h','')[:44]} oc={ev.get('oc','')[:60]} "
                              f"id={ev.get('id','')}", flush=True)
            try:
                ctx.pages[0].wait_for_timeout(400) if ctx.pages else time.sleep(0.4)
            except Exception:
                time.sleep(0.4)
        b.close()


if __name__ == "__main__":
    main()
