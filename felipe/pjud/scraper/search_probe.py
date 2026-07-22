"""search_probe.py — isolate WHICH part of the script's search path trips the F5 WAF.

Context (2026-07-22): a fresh profile served the OPERATOR three manual searches, full
pagination (8 pages / 715 rows) and three causa opens with ZERO rejections, while the script
gets rejected. So the block is script-specific, not a per-session search budget and not
reCAPTCHA token reuse (search #2 provably REUSED a 38s-old token and worked). This probe
fires ONE search per run, using the REAL functions from cdp_scrape, with a single variable
changed, so the guilty step can be named.

RESULT 2026-07-22: `--mode click` — a bare Playwright page.click on Buscar, NO form changes,
identical POST params to a manual search 5 minutes earlier on the same tribunal, and a FRESH
token — was rejected instantly (250B F5 page in 0.1s, vs 109KB in 19.5s for the manual one).
So the payload is not the discriminator; HOW the input was produced is. Two candidates remain:
(a) page.click teleports the pointer — no approach path, no hover dwell, which is exactly what
F5 Shape's behavioural telemetry scores; (b) Runtime.evaluate over CDP is detectable, and the
probe read the DOM right before clicking. `--mode human` + `--bare` separate them.

Modes (run one per invocation, cheapest first — each costs exactly one search):
  --mode click      Buscar only. No form changes at all. Isolates "a scripted trusted click".
                    KNOWN-BAD as of 2026-07-22 — kept as the control.
  --mode human      Buscar via a HUMAN-SHAPED pointer: curved multi-step approach, jitter,
                    hover dwell, realistic press duration. The hypothesis fix.
  --mode clear      JS-clear the results tbody, then Buscar. Isolates fire_search's innerHTML
                    mutation (the one bit of DOM injection in the search path).
  --mode kbd        select_tribunal_kbd (arrow-key burst) + ~1s + Buscar. The PRODUCTION path.
  --mode kbd-slow   same, but --wait seconds before Buscar. Separates "arrow burst is fatal"
                    from "clicking 1s after the change is fatal".

--bare skips every pre-click DOM read, so not one Runtime.evaluate is issued before the click
(the element box is fetched over the CDP DOM domain instead). Reading after the click is safe.

Chrome fires a change event on EVERY arrow press over a closed <select>, so an N-option jump
emits N change events where a human emits one; --hops sets that distance deliberately.

Run net_probe.py alongside so the request is recorded and diffable against the manual baseline.
Verdict is printed as OK / BLOCKED (Buscar stuck disabled = the instant F5 tell) / NO-ROWS.
"""

import argparse
import math
import random
import time

from playwright.sync_api import sync_playwright

import cdp_scrape as cs

BTN = "#btnConConsultaFec"
TBL = "#dtaTableDetalleFecha"


def box_via_cdp(page, sel):
    """Element box WITHOUT Runtime.evaluate — the DOM domain only, so nothing is injected into
    the page's JS world and no isolated world is created. Returns (cx, cy) centre or None."""
    s = page.context.new_cdp_session(page)
    try:
        root = s.send("DOM.getDocument", {"depth": 1})["root"]["nodeId"]
        nid = s.send("DOM.querySelector", {"nodeId": root, "selector": sel})["nodeId"]
        if not nid:
            return None
        quad = s.send("DOM.getBoxModel", {"nodeId": nid})["model"]["content"]
        xs, ys = quad[0::2], quad[1::2]
        return (sum(xs) / 4.0, sum(ys) / 4.0)
    except Exception as e:
        print(f"    [box] {str(e)[:60]}")
        return None
    finally:
        try:
            s.detach()
        except Exception:
            pass


def human_click(page, x, y):
    """Move the pointer to (x,y) the way a hand does — an arc, not a teleport — then dwell and
    press. page.click() jumps straight to the target and fires down+up with no approach and no
    hover; F5 Shape scores exactly that. Every event here is still CDP Input (isTrusted=true),
    only the SHAPE of the motion changes."""
    sx, sy = x - random.uniform(180, 320), y + random.uniform(90, 200)   # somewhere else first
    page.mouse.move(sx, sy)
    page.wait_for_timeout(random.randint(60, 140))

    steps = random.randint(18, 28)
    bow = random.uniform(-38, 38)          # perpendicular bulge -> a curve, not a straight line
    for i in range(1, steps + 1):
        t = i / steps
        ease = t * t * (3 - 2 * t)                       # slow start, fast middle, slow finish
        arc = math.sin(math.pi * t) * bow
        page.mouse.move(sx + (x - sx) * ease + arc + random.uniform(-1.2, 1.2),
                        sy + (y - sy) * ease + random.uniform(-1.2, 1.2))
        page.wait_for_timeout(random.randint(8, 22))

    page.mouse.move(x + random.uniform(-1.5, 1.5), y + random.uniform(-1.5, 1.5))
    page.wait_for_timeout(random.randint(140, 380))      # hover dwell before committing
    page.mouse.down()
    page.wait_for_timeout(random.randint(55, 130))       # press duration
    page.mouse.up()


def state(page):
    """Read-only snapshot of the form + results."""
    def ev(sel, js, default=None):
        try:
            return page.eval_on_selector(sel, js)
        except Exception:
            return default
    return {
        "trib": ev("#fecTribunal", "e=>e.value", "?"),
        "trib_txt": ev("#fecTribunal",
                       "e=>e.options[e.selectedIndex]?e.options[e.selectedIndex].text.trim():''", ""),
        "idx": ev("#fecTribunal", "e=>e.selectedIndex", -1),
        "n_opts": ev("#fecTribunal", "e=>e.options.length", 0),
        "disabled": ev(BTN, "e=>e.disabled", None),
        "rows": ev(TBL + " tbody", "e=>e.querySelectorAll('tr').length", 0),
        "desde": ev("#fecDesde", "e=>e.value", ""),
        "hasta": ev("#fecHasta", "e=>e.value", ""),
    }


def rejected_anywhere(page):
    """True if any frame is showing the F5 'requested URL was rejected' page."""
    for fr in page.frames:
        try:
            txt = fr.evaluate("document.body?document.body.innerText.slice(0,400):''") or ""
        except Exception:
            continue
        if "requested URL was rejected" in txt or "Support ID" in txt:
            return True
    return False


def hop_target(page, hops):
    """The #fecTribunal option `hops` positions away from the current one (clamped)."""
    opts = page.eval_on_selector_all(
        "#fecTribunal option", "els=>els.map((o,i)=>({i:i,v:o.value,sel:o.selected}))")
    cur = next((o["i"] for o in opts if o["sel"]), 0)
    tgt = max(0, min(len(opts) - 1, cur + hops))
    while tgt < len(opts) and (not opts[tgt]["v"] or opts[tgt]["v"] == "0"):
        tgt += 1
    return opts[tgt]["v"], abs(tgt - cur)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--mode", required=True,
                    choices=("click", "human", "clear", "kbd", "kbd-slow"))
    ap.add_argument("--bare", action="store_true",
                    help="no DOM reads before the click (zero Runtime.evaluate) — the purest "
                         "test of whether CDP JS evaluation is what F5 is detecting")
    ap.add_argument("--hops", type=int, default=1,
                    help="how many options to arrow past (kbd modes) = how many change events")
    ap.add_argument("--wait", type=float, default=30.0,
                    help="seconds between the tribunal change and Buscar (kbd-slow)")
    args = ap.parse_args()

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        ctx = browser.contexts[0]
        if args.bare:
            # Pick the tab by URL ONLY. cs.find_ojv_page() probes with query_selector, which is
            # a Runtime evaluation in an isolated world — the very thing --bare exists to avoid.
            page = next((p for p in ctx.pages
                         if "oficinajudicialvirtual" in (p.url or "")), None)
        else:
            page = cs.find_ojv_page(ctx)
        if not page:
            raise SystemExit("[ERROR] No encuentro la pestana OJV.")

        if args.bare:
            print("[before] (--bare: no DOM reads before the click)")
        else:
            before = state(page)
            print(f"[before] trib={before['trib']} ({before['trib_txt'][:38]}) "
                  f"idx={before['idx']}/{before['n_opts']} rows={before['rows']} "
                  f"buscar_disabled={before['disabled']} fechas={before['desde']}..{before['hasta']}")
            if before["disabled"]:
                print("[ALTO] Buscar is ALREADY disabled — the session is blocked or mid-request.")
                return 1
            if rejected_anywhere(page):
                print("[ALTO] An F5 rejection page is already showing. Fresh profile needed.")
                return 1

        # Judge by the RESPONSE, not by the results table: the table keeps the previous
        # search's rows, so a rejected search can look like 100 happy rows (it did, 2026-07-22).
        seen = []

        def on_response(resp):
            if not resp.url.endswith("consultaFechaCivil.php"):
                return
            try:
                txt = resp.text()
            except Exception:
                txt = ""
            seen.append({"status": resp.status, "size": len(txt),
                         "rejected": "requested URL was rejected" in txt or "Support ID" in txt})

        page.on("response", on_response)

        t0 = time.time()
        if args.mode in ("kbd", "kbd-slow"):
            tgt, presses = hop_target(page, args.hops)
            print(f"[act] select_tribunal_kbd -> {tgt}  ({presses} arrow presses = "
                  f"{presses} trusted change events)")
            if not cs.select_tribunal_kbd(page, tgt):
                print("[ALTO] tribunal switch failed")
                return 1
            gap = args.wait if args.mode == "kbd-slow" else 1.0
            print(f"[act] waiting {gap:.1f}s before Buscar")
            time.sleep(gap)
        elif args.mode == "clear":
            print("[act] JS-clearing the results tbody (fire_search's innerHTML mutation)")
            page.evaluate("()=>{const t=document.querySelector('%s tbody');"
                          " if(t) t.innerHTML='';}" % TBL)
            time.sleep(1.0)
        else:
            print("[act] no form changes — clicking Buscar as-is")

        if args.mode == "human":
            xy = box_via_cdp(page, BTN)                  # no Runtime.evaluate
            if not xy:
                print("[ALTO] could not locate Buscar over the CDP DOM domain")
                return 1
            print(f"[act] human-shaped pointer -> Buscar at ({xy[0]:.0f},{xy[1]:.0f}) "
                  f"+ poll up to 45s")
            human_click(page, *xy)
        else:
            print("[act] click Buscar (page.click, teleport) + poll up to 45s")
            page.click(BTN, timeout=5000)
        waited = 0
        while waited < 45000 and not seen:
            page.wait_for_timeout(500)
            waited += 500

        after = state(page)
        secs = time.time() - t0
        hit = seen[0] if seen else None
        print(f"[after ] response={hit} rows_in_table={after['rows']} "
              f"buscar_disabled={after['disabled']} trib={after['trib']} ({secs:.1f}s)")

        if hit and hit["rejected"]:
            print(f"\nVERDICT: BLOCKED — F5 rejected the search in {secs:.1f}s "
                  f"({hit['size']}B). THIS STEP IS THE TRIGGER.")
            rc = 2
        elif hit and hit["size"] > 5000:
            print(f"\nVERDICT: OK — real results back ({hit['size']}B in {secs:.1f}s). "
                  f"This step is INNOCENT.")
            rc = 0
        elif hit:
            print(f"\nVERDICT: NO-ROWS — small non-reject response ({hit['size']}B): "
                  f"empty result or throttle. Not the classic block.")
            rc = 3
        else:
            print("\nVERDICT: NO-RESPONSE — the search POST never came back in 45s. "
                  "Treat as a hang/throttle, not a clean reject.")
            rc = 4
        if rejected_anywhere(page):
            print("  (+ an F5 rejection page is now rendered in a frame)")
        browser.close()
        return rc


if __name__ == "__main__":
    raise SystemExit(main())
