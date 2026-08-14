"""ENTRY PROBE — what doors does THIS machine get offered?

One question, cheaply: does www.pjud.cl serve this IP the same OJV links it serves a residential
browser, and where does each one land? Two page loads. NO SEARCH, no causa, no document — so it
costs the site almost nothing and cannot spend a session's allowance.

⚠️ WHY THIS EXISTS. On 2026-08-14 the site changed its entry route: www.pjud.cl went from offering
"Plataforma para el ingreso de causas y escritos" (-> /home/, guest-entry gate) to a single anchor
"Sección que permite la revisión de causas" (-> straight to indexN.php, no gate). The worker was
fixed to follow it, which made RESIDENTIAL entry work in 16 s after nine failed clicks.

Then two runners in a row, an hour apart on a quiet range and different IPs, entered perfectly by
that route and could not complete a SINGLE search: rejF=1, spinner abandoned, 0 causa opens. Every
remote run that DID search today had gone through /home/ first.

So the question is whether a datacenter IP is still offered /home/ at all. If it is, prefer it
remotely and keep the direct route locally. If it is not, the gate route is gone and we cannot get
it back -- we do not type deep URLs. Guessing between those two costs a session each time; this
costs two page loads.

    python entry_probe.py --port 9222
"""
import sys, json, time, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright

OJV = "oficinajudicialvirtual.pjud.cl"

ANCHORS = r"""() => [...document.querySelectorAll('a')]
   .map(a => ({txt: (a.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 70),
               title: (a.getAttribute('title') || '').slice(0, 70),
               href: (a.getAttribute('href') || '').slice(0, 110)}))
   .filter(x => /oficinajudicialvirtual/i.test(x.href))"""

WHERE = r"""() => ({
   url: location.href,
   form: !!document.querySelector('#fecCompetencia'),
   buscar: !!document.querySelector('#btnConConsultaFec'),
   gate: document.querySelectorAll(
        "[onclick*='accesoConsultaCausas'],[onclick*='accesoInvitado']").length,
   aviso: !!document.querySelector('#no-disponible'),
   homeLinks: [...document.querySelectorAll('a')]
        .map(a => a.getAttribute('href') || '')
        .filter(h => /oficinajudicialvirtual/i.test(h)).slice(0, 12)
})"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    a = ap.parse_args()
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}", timeout=60000)
        ctx = b.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.pjud.cl/", wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        anchors = page.evaluate(ANCHORS)
        out["www_anchors"] = anchors
        print("=== OJV anchors offered on www.pjud.cl ===")
        for x in anchors:
            print(f"  txt={x['txt'][:44]!r} title={x['title'][:40]!r}")
            print(f"      -> {x['href']}")
        out["has_home_link"] = any("/home" in (x["href"] or "").lower() for x in anchors)
        out["has_direct_link"] = any("consultaunificada" in (x["href"] or "").lower()
                                     for x in anchors)
        print(f"\n  /home offered?  {out['has_home_link']}")
        print(f"  direct offered? {out['has_direct_link']}")

        # Follow whichever the worker would take, and say exactly where it lands.
        if anchors:
            pick = next((x for x in anchors
                         if "consultaunificada" in (x["href"] or "").lower()), anchors[0])
            print(f"\n=== following {pick['href'][:80]} ===")
            before = set(ctx.pages)
            try:
                page.locator(f"a[href='{pick['href']}']").first.click(timeout=8000)
            except Exception as e:
                print("  click failed:", str(e)[:70])
            landed = page
            for _ in range(30):
                time.sleep(1)
                new = [q for q in ctx.pages if OJV in (q.url or "")]
                if new:
                    landed = new[-1]
                    break
            landed.bring_to_front()
            time.sleep(4)
            where = landed.evaluate(WHERE)
            out["landed"] = where
            print(json.dumps(where, ensure_ascii=False, indent=1))
            # And from THERE, is /home reachable by a link? (We never type a URL.)
            out["home_reachable_from_landing"] = any(
                "/home" in h.lower() for h in where.get("homeLinks", []))
            print(f"\n  /home linked from the landing page? "
                  f"{out['home_reachable_from_landing']}")
    print("\nJSON " + json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
