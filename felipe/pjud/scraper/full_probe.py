"""FULL CAUSA PROBE — take EVERYTHING a causa has, and find the fastest pace that survives it.

Worker A takes one document per causa (the ebook) because, when it was written, detail was the
scarce resource and every extra request was a withdrawal from a budget we did not understand.
That budget turned out to be mostly self-inflicted: uniform keystrokes and no scrolling. With
those fixed a single worker sustains ~3 req/min, so the honest question is now what a COMPLETE
causa costs and how fast we can take them.

Complete means:
    header, litigantes, escritos                    free with the open
    every cuaderno (switching costs a request each)
    every historia row of every cuaderno            free once the cuaderno is loaded
    texto demanda, certificado, ebook               3 requests
    every historia row document + anexo             1 request each
    receptor / notificaciones                       1 request (opens its own modal)
    georreferencia for every row that has one       1 request each

The point is the MEASUREMENT: how many requests a full causa really costs, how long it takes, and
where it trips. Everything is counted separately so the expensive parts are visible rather than
averaged away.

    python full_probe.py --port 9342 --causas 6
    python full_probe.py --port 9342 --causas 12 --gap 20     # then ramp the gap down

⚠️ Designed to be pushed until it trips. Run it on a session you can afford to lose.
"""
import sys, time, argparse, json, base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cdp_scrape as C
import ojv
from ojv import note
from settle import Settler
import worker_a as A
from playwright.sync_api import sync_playwright

PDFS = Path(__file__).parent.parent / "data" / "full_probe"
net = []


FETCH_BY_FORM_JS = r"""
async ([action, name, value]) => {
  const url = new URL(action, location.href).href
            + '?' + encodeURIComponent(name) + '=' + encodeURIComponent(value);
  const r = await fetch(url, {credentials: 'include'});
  const buf = new Uint8Array(await r.arrayBuffer());
  let s = '', CH = 8192;
  for (let i = 0; i < buf.length; i += CH)
    s += String.fromCharCode.apply(null, buf.subarray(i, i + CH));
  return {status: r.status, ct: r.headers.get('content-type'), n: buf.length, b64: btoa(s)};
}
"""


def fetch_form(p, action, name, value, label, out_dir):
    """Fetch one document straight from the page. Returns (bytes, ok).

    Same in-page route as worker A: the page requests it with its own cookies, exactly as the
    click would have. Never judged by size — %PDF or it did not arrive.
    """
    if not (action and value):
        return 0, False
    try:
        res = p.evaluate(FETCH_BY_FORM_JS, [action, name or "dtaDoc", value])
    except Exception as e:
        note(f"        {label}: fetch threw {str(e)[:50]}")
        return 0, False
    body = base64.b64decode(res["b64"])
    if body[:4] != b"%PDF":
        return 0, False
    (out_dir / f"{label}.pdf").write_bytes(body)
    return len(body), True


def harvest_full(p, causa_id, want_geo=True, want_receptor=True, doc_gap=0.0):
    """Everything. Returns a dict of what was taken and what each part cost."""
    out_dir = PDFS / causa_id.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cost = {"docs": 0, "geo": 0, "cuaderno_switch": 0, "receptor": 0}
    got = {"bytes": 0, "docs": 0, "geo": 0, "rows": 0, "cuadernos": 0}

    rec = {"causa_id": causa_id,
           "header": C.parse_header(p),
           "litigantes": C.parse_litigantes(p),
           "escritos": C.parse_escritos(p)}
    C.human_scroll(p, notches=3)

    # --- header documents -------------------------------------------------------
    hdr = C.grab_header_docs(p)
    for hd in hdr:
        n, ok = fetch_form(p, hd["action"], hd["param"], hd["val"], hd["key"], out_dir)
        cost["docs"] += 1
        got["bytes"] += n
        got["docs"] += ok
        if doc_gap:
            time.sleep(doc_gap)

    # --- every cuaderno, every row, every attachment -----------------------------
    cuads = C.cuaderno_options(p) or [{"txt": "1 - Principal", "val": ""}]
    got["cuadernos"] = len(cuads)
    rec["cuadernos"] = []
    for ci, opt in enumerate(cuads):
        if ci:
            C.select_cuaderno(p, ci)            # a request, and the only one we cannot avoid
            cost["cuaderno_switch"] += 1
            p.wait_for_timeout(1200)
            C.human_scroll(p, notches=2)
        rows = C.parse_historia(p)
        got["rows"] += len(rows)
        cn = C._cuaderno_num(opt["txt"]) if hasattr(C, "_cuaderno_num") else str(ci + 1)
        for ri, r in enumerate(rows):
            for kind in ("doc", "anexo"):
                f = r.get(kind)
                if not (f and f.get("action") and f.get("val")):
                    continue
                lbl = f"c{cn}-{r.get('folio', ri)}-{kind}"
                n, ok = fetch_form(p, f["action"], "dtaDoc", f["val"], lbl, out_dir)
                cost["docs"] += 1
                got["bytes"] += n
                got["docs"] += ok
                if doc_gap:
                    time.sleep(doc_gap)
            if want_geo and r.get("geo"):
                g = C.resolve_geo(p, r["geo"])
                cost["geo"] += 1
                got["geo"] += bool(g)
                r["georref"] = g
        rec["cuadernos"].append({"cuaderno": opt["txt"], "historia": rows})

    # --- receptor / notificaciones ----------------------------------------------
    if want_receptor:
        rec["receptor"] = C.parse_receptor(p)
        cost["receptor"] = 1

    rec["_cost"] = cost
    rec["_got"] = got
    rec["_secs"] = round(time.time() - t0, 1)
    rec["_requests"] = cost["docs"] + cost["geo"] + cost["cuaderno_switch"] + cost["receptor"] + 1
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9342)
    ap.add_argument("--causas", type=int, default=6)
    ap.add_argument("--gap", type=float, default=30.0, help="between causas")
    ap.add_argument("--doc-gap", type=float, default=0.0, help="between documents inside a causa")
    ap.add_argument("--no-geo", action="store_true")
    ap.add_argument("--no-receptor", action="store_true")
    a = ap.parse_args()
    PDFS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        ctx = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}", timeout=60000).contexts[0]
        p = C.find_ojv_page(ctx)
        if p is None:
            raise SystemExit("no form — walk in first")
        p.bring_to_front()
        p.on("response", ojv.make_tap(net))
        S = Settler(p)
        C.open_fecha_panel(p)

        banks = C.page_bank_causas(p)
        if not banks:
            raise SystemExit("no bank causas on the current results page — run a search first")
        note(f"{len(banks)} causas on this page | gap {a.gap:.0f}s, doc-gap {a.doc_gap:.1f}s, "
             f"geo={not a.no_geo} receptor={not a.no_receptor}")

        rows, last = [], 0.0
        for i, c in enumerate(banks[:a.causas], 1):
            if last:
                g = a.gap - (time.time() - last)
                if g > 0:
                    time.sleep(g)
            t0 = time.time()
            ok = C.human_click(p, p.locator("#dtaTableDetalleFecha tbody tr").nth(c["i"])
                               .locator("a[onclick*='detalleCausaCivil']").first, timeout=8000)
            opened = False
            while time.time() - t0 < 60:
                p.wait_for_timeout(400)
                try:
                    if p.evaluate("(r)=>{const m=document.querySelector('#modalDetalleCivil');"
                                  "return !!m && m.innerText.indexOf(r)>=0;}", c["rol"]):
                        opened = True
                        break
                except Exception:
                    pass
            if not opened:
                note(f"  [{i}] {c['rol']}: modal did not open")
                C.clear_stuck_modal(p)
                continue
            p.wait_for_timeout(900)
            rec = harvest_full(p, c["rol"], not a.no_geo, not a.no_receptor, a.doc_gap)
            C.close_modal(p, "#modalDetalleCivil")
            p.wait_for_timeout(800)
            C.clear_stuck_modal(p)
            last = time.time()
            cyc = time.time() - t0
            blocked, why = ojv.blocked(p, net)
            cap = ojv.captcha_frame(p)
            g, ct = rec["_got"], rec["_cost"]
            note(f"  [{i}] {c['rol']:14} {cyc:5.1f}s  {rec['_requests']:>2} req "
                 f"(docs {ct['docs']} geo {ct['geo']} cuad {ct['cuaderno_switch']}) -> "
                 f"{g['docs']} pdfs {g['bytes']/1e6:.1f}MB, {g['rows']} rows, {g['geo']} geo, "
                 f"{len(rec.get('receptor') or [])} receptor"
                 + (f"  *** {why or 'CAPTCHA'}" if (blocked or cap) else ""))
            rows.append({"rol": c["rol"], "cycle": round(cyc, 1), **rec["_cost"],
                         "requests": rec["_requests"], "pdfs": g["docs"],
                         "bytes": g["bytes"], "rows": g["rows"], "geo": g["geo"],
                         "receptor": len(rec.get("receptor") or []),
                         "blocked": blocked, "captcha": cap})
            if blocked or cap:
                note("  *** STOPPING")
                break

        if rows:
            n = len(rows)
            note("")
            note(f"{n} full causas | avg {sum(r['cycle'] for r in rows)/n:.1f}s, "
                 f"{sum(r['requests'] for r in rows)/n:.1f} requests, "
                 f"{sum(r['pdfs'] for r in rows)/n:.1f} pdfs, "
                 f"{sum(r['bytes'] for r in rows)/n/1e6:.1f} MB each")
            note(f"  request rate: {60*sum(r['requests'] for r in rows)/sum(r['cycle'] for r in rows):.2f}/min")
            note(f"  blocked: {sum(1 for r in rows if r['blocked'] or r['captcha'])}")
        Path(PDFS / "full_probe.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
        note(f"wrote {PDFS / 'full_probe.json'}")


if __name__ == "__main__":
    sys.exit(main())
