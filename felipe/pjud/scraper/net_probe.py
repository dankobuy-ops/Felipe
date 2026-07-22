"""Read-only NETWORK recorder for the OJV page. Attaches over CDP and logs every request
the page makes (method, url, POST body, key form params) plus the response status/size and
whether F5 rejected it. Injects NOTHING — it only listens.

Why: on 2026-07-21 a fresh profile served the OPERATOR a working manual search and then
rejected the SCRIPT's very first search. Same session, same form, different outcome — so
the difference is in the request the script produces, not the device reputation. This tool
captures both requests so they can be diffed field by field.

How to use (one experiment = one fresh profile):
  1. Operator: fresh profile, CAPTCHA, reach Consulta Causas.
  2. Start:  python net_probe.py --label manual
  3. Operator: establish the form BY HAND and click Buscar. Confirm results appear.
  4. Stop it (Ctrl+C), then start:  python net_probe.py --label script
  5. Run the scraper (or just its search) and let it get rejected.
  6. Diff the two JSONL files — the params that differ are the answer.

Output: <scratchpad or --out dir>/netprobe_<label>_<epoch>.jsonl (one JSON per request).
"""

import argparse
import json
import time
from pathlib import Path
from urllib.parse import parse_qsl

from playwright.sync_api import sync_playwright

# Params whose full value is noise (or huge); log a fingerprint instead of the value.
FINGERPRINT = {"g-recaptcha-response-fecha", "g-recaptcha-response-rit",
               "g-recaptcha-response-nombre", "g-recaptcha-response-jur",
               "g-recaptcha-response"}


def find_ojv_page(ctx):
    for p in ctx.pages:
        if "pjud" in (p.url or ""):
            return p
    return None


def summarize_post(body):
    """Form params as {name: value}, with recaptcha tokens reduced to len+head+tail so two
    requests can be compared for token REUSE without dumping 1.3KB of token per line."""
    if not body:
        return {}
    out = {}
    try:
        pairs = parse_qsl(body, keep_blank_values=True)
    except Exception:
        return {"_raw": body[:300]}
    for k, v in pairs:
        if k in FINGERPRINT:
            out[k] = f"<len={len(v)} {v[:12]}…{v[-8:]}>" if v else "<EMPTY>"
        else:
            out[k] = v[:200]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--label", default="run", help="manual | script | anything")
    ap.add_argument("--seconds", type=int, default=600, help="how long to listen")
    ap.add_argument("--out", default="", help="output dir (default: alongside this script)")
    args = ap.parse_args()

    outdir = Path(args.out) if args.out else Path(__file__).resolve().parent
    outfile = outdir / f"netprobe_{args.label}_{int(time.time())}.jsonl"
    fh = outfile.open("w", encoding="utf-8")
    n = [0]

    def record(kind, **kw):
        n[0] += 1
        rec = {"i": n[0], "t": round(time.time(), 3), "kind": kind, **kw}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        return rec

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        ctx = browser.contexts[0]
        print(f"[probe:{args.label}] -> {outfile}")

        def on_request(req):
            if "pjud.cl" not in req.url:
                return
            if req.resource_type in ("image", "stylesheet", "font", "media"):
                return
            body = None
            try:
                body = req.post_data
            except Exception:
                pass
            # ALL headers (cookie reduced to a length — this file is gitignored but a 4KB
            # session cookie in a log is still a bad habit). We need the full set because the
            # open question is how a browser-issued request differs from an out-of-page
            # context.request.get(): referer, sec-fetch-*, accept, ua-* are exactly the tell.
            hdrs = {}
            for k, v in req.headers.items():
                kl = k.lower()
                hdrs[kl] = f"<len={len(v)}>" if kl in ("cookie", "authorization") else v[:300]
            rec = record("request", method=req.method, url=req.url,
                         rtype=req.resource_type, params=summarize_post(body),
                         headers=hdrs)
            if req.method == "POST":
                print(f"  #{rec['i']} POST {req.url.split('/')[-1]}  "
                      f"{ {k: v for k, v in rec['params'].items() if k.startswith('fec') or k.startswith('corte')} }")

        def on_response(resp):
            if "pjud.cl" not in resp.url or resp.request.resource_type in (
                    "image", "stylesheet", "font", "media"):
                return
            rejected, size = None, None
            try:
                txt = resp.text()
                size = len(txt)
                rejected = "requested URL was rejected" in txt or "Support ID" in txt
            except Exception:
                pass
            rec = record("response", url=resp.url, status=resp.status,
                         size=size, rejected=rejected)
            if rejected:
                print(f"  #{rec['i']} !! REJECTED {resp.url.split('/')[-1]} "
                      f"(status {resp.status})")
            elif resp.request.method == "POST":
                print(f"  #{rec['i']} <- {resp.status} {size}B {resp.url.split('/')[-1]}")

        # Attach to EVERY tab, present and future. OJV opens Consulta Causas in a new tab and
        # discards the old one, so pinning to a single page makes the recorder die exactly when
        # the interesting traffic starts (it did, 2026-07-22 — 0 events captured).
        attached = set()

        def attach(pg):
            if pg in attached:
                return
            attached.add(pg)
            pg.on("request", on_request)
            pg.on("response", on_response)
            try:
                print(f"[probe:{args.label}] +tab {(pg.url or '')[:78]}")
            except Exception:
                pass

        for pg in ctx.pages:
            attach(pg)
        ctx.on("page", attach)

        deadline = time.time() + args.seconds
        try:
            while time.time() < deadline:
                for pg in ctx.pages:     # pick up tabs opened before the event landed
                    attach(pg)
                # The wait MUST go through Playwright: a bare time.sleep() blocks the sync
                # greenlet and no request/response events are ever dispatched (0 events
                # captured, 2026-07-22). Pump via any live tab so one closing tab is harmless.
                for pg in list(ctx.pages):
                    try:
                        pg.wait_for_timeout(500)
                        break
                    except Exception:
                        continue
                else:
                    time.sleep(0.5)      # no tabs at all right now
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"[probe:{args.label}] loop ended: {str(e)[:80]}")
        finally:
            fh.close()
            print(f"\n[probe:{args.label}] {n[0]} events -> {outfile}")


if __name__ == "__main__":
    main()
