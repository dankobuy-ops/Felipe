"""REMOTE PROBE — can a GitHub runner reach the OJV at all, and where exactly does it stop?

The old workflow failed 17 jobs a day for ~13 days with one line — "could not establish the date
search form" — and the note left behind concluded a headless runner is stopped by reCAPTCHA v3 at
gate 1 and that no code change could help. Most of that diagnosis has since been disproved
locally:

  * Gate 1 was never a reCAPTCHA refusal. It was the #no-disponible AVISO covering the button,
    plus a strict-mode bug that meant the click was never delivered at all. Scripted entry now
    succeeds on a VIRGIN profile in about 20 seconds.
  * "The form never appears" is exactly what a blank OJV tab looks like, and F5's challenge script
    checks document.visibilityState — a tab that is never visible never runs it. On a HEADLESS
    runner nothing is ever visible, which would produce that precise error indefinitely. This
    probe therefore runs Chrome HEADED under Xvfb.

What is still genuinely unknown is the IP. Every measurement we have was taken from a residential
Chilean address; a runner is an Azure datacenter range, and that is independent of every bug we
fixed. This probe exists to answer that one question cheaply, so report the GATE reached rather
than a pass/fail:

    ip           the runner's public address, so we know what F5 actually saw
    pjud_home    www.pjud.cl reachable
    ojv_home     the OJV landing rendered (challenge cleared)
    entry        got into indexN.php
    form         the search form is usable (tribunal list populated)
    search       one search returned results

Any of those can fail, and each failure means something different. One search maximum: this is a
diagnostic, not a scrape.
"""
import sys, os, json, time, subprocess, socket
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
PORT = int(os.environ.get("PROBE_PORT", "9222"))
OUT = {"gate": "none", "ip": None, "steps": {}, "notes": []}


def note(m):
    print(f"[probe] {m}", flush=True)
    OUT["notes"].append(m)


def public_ip():
    import urllib.request
    for u in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(u, timeout=10) as r:
                return r.read().decode().strip()
        except Exception:
            continue
    return None


def wait_cdp(port, secs=40):
    import urllib.request
    for _ in range(secs):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read()
            return True
        except Exception:
            time.sleep(1)
    return False


def main():
    OUT["ip"] = public_ip()
    note(f"runner public IP: {OUT['ip']}")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        exe = pw.chromium.executable_path
        prof = Path.home() / "pjud_probe_profile"
        prof.mkdir(exist_ok=True)
        # HEADED, under whatever DISPLAY the workflow set up. Headless is both a strong
        # fingerprint and — more importantly — never "visible", which is the condition F5's
        # challenge script tests before it will run.
        # ⚠️ --no-sandbox is required on a CI runner: Chrome cannot set up its sandbox in that
        # container and dies instantly without it, which reads as "never opened its CDP port".
        # --disable-dev-shm-usage for the same class of reason: /dev/shm is tiny there and Chrome
        # crashes under it. And keep stderr — throwing it away is why the first run told us
        # nothing at all about WHY it did not start.
        err_log = Path("chrome_stderr.log")
        proc = subprocess.Popen(
            [exe, f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}",
             "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
             "--no-first-run", "--no-default-browser-check", "--window-size=1440,900",
             "https://www.pjud.cl/"],
            stdout=subprocess.DEVNULL, stderr=err_log.open("wb"),
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":99")})
        try:
            if not wait_cdp(PORT):
                note("chrome never opened its CDP port")
                try:
                    tail = err_log.read_text(errors="replace")[-1200:]
                    note(f"chrome stderr tail: {tail}")
                except Exception:
                    note("(no chrome stderr captured)")
                note(f"DISPLAY={os.environ.get('DISPLAY')!r}  exit={proc.poll()}")
                return finish(2)
            note("chrome up, attaching over CDP (same path as local)")

            import cdp_scrape as C
            import ojv
            b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=60000)
            ctx = b.contexts[0]
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.bring_to_front()

            # --- www.pjud.cl -----------------------------------------------------------
            try:
                pg.goto("https://www.pjud.cl/", wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(3000)
                links = pg.eval_on_selector_all(
                    "a", "els=>els.filter(a=>(a.getAttribute('href')||'')"
                         ".includes('oficinajudicialvirtual')).length")
                OUT["steps"]["pjud_home"] = {"ok": True, "ojv_links": links,
                                             "title": pg.title()[:60]}
                OUT["gate"] = "pjud_home"
                note(f"www.pjud.cl OK — {links} OJV links, title {pg.title()[:40]!r}")
            except Exception as e:
                OUT["steps"]["pjud_home"] = {"ok": False, "err": str(e)[:120]}
                note(f"www.pjud.cl FAILED: {str(e)[:90]}")
                return finish(3)

            # --- the OJV, and whatever it puts in front of us ---------------------------
            p = ojv.walk_in(ctx)
            cap = any(ojv.captcha_frame(q) for q in ctx.pages)
            rej = sum(ojv.rej_frames(q) for q in ctx.pages)
            OUT["steps"]["ojv"] = {"entered": p is not None, "captcha": cap, "rej_frames": rej}
            if cap:
                note("*** TIER-3 IMAGE CAPTCHA — a human gate. This is the answer: a runner IP "
                     "is challenged where a residential one is not.")
                OUT["gate"] = "captcha"
                return finish(0)
            if p is None:
                note(f"could not enter (captcha={cap} rejection_frames={rej})")
                OUT["gate"] = "ojv_blocked"
                return finish(0)
            OUT["gate"] = "entry"
            note(f"ENTERED: {p.url[:60]}")

            # --- can we drive the form? ------------------------------------------------
            from settle import Settler
            net = []
            p.on("response", ojv.make_tap(net))
            S = Settler(p)
            C.open_fecha_panel(p)
            if p.eval_on_selector("#fecCompetencia", "e=>e.value") != "3":
                C.select_by_kbd(p, "#fecCompetencia", "3")
                ojv.click_away(p)
                S.wait(need="document.querySelectorAll('#fecTribunal option').length>50",
                       quiet_ms=1200, timeout=60, label="tribunales")
            n = p.eval_on_selector_all("#fecTribunal option", "e=>e.length")
            OUT["steps"]["form"] = {"tribunales": n}
            note(f"form: {n} tribunales")
            if n < 50:
                OUT["gate"] = "form_empty"
                return finish(0)
            OUT["gate"] = "form"

            # --- exactly ONE search ----------------------------------------------------
            for sel, val in (("#fecDesde", "01/07/2026"), ("#fecHasta", "14/07/2026")):
                C.type_date_kbd(p, sel, val)
                ojv.click_away(p)
            tl = p.eval_on_selector_all(
                "#fecTribunal option",
                "e=>e.filter(o=>o.value&&o.value!=='0').map(o=>o.value)")
            C.select_tribunal_kbd(p, tl[0])
            ojv.click_away(p)
            C.human_scroll(p, notches=2)
            net.clear()
            C.human_click(p, "#btnConConsultaFec")
            kind, el = ojv.wait_results(p, S, net)
            blocked, why = ojv.blocked(p, net)
            OUT["steps"]["search"] = {"kind": kind, "secs": round(el, 1),
                                      "total": C.total_registros(p),
                                      "blocked": blocked, "why": why}
            note(f"search -> {kind} in {el:.0f}s total={C.total_registros(p)} blocked={blocked} {why}")
            OUT["gate"] = "search_ok" if kind == "results" and not blocked else "search_blocked"
            return finish(0)
        finally:
            try:
                proc.terminate()
            except Exception:
                pass


def finish(code):
    note(f"GATE REACHED: {OUT['gate']}")
    Path("remote_probe_result.json").write_text(json.dumps(OUT, indent=1), encoding="utf-8")
    print("::group::probe result")
    print(json.dumps(OUT, indent=1))
    print("::endgroup::")
    return code


if __name__ == "__main__":
    sys.exit(main())
