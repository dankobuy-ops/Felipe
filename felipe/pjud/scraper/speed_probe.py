"""SPEED PROBE — find the fastest sustainable pace for ONE worker, and prove where it trips.

Every pacing number we use was tuned when our sessions produced NO human telemetry: uniform
keystrokes, no scrolling at all. The gaps were pure dead air, so "wait longer" was the only lever
we had. Now that input has human cadence and the page actually gets scrolled, a large part of each
cycle is filled with activity rather than silence — and the honest question becomes what the
minimum viable CYCLE TIME is, not how long we idle between requests.

    python speed_probe.py --port 9352            # ramp searches down from 45 s
    python speed_probe.py --port 9352 --detail   # ramp causa opens instead

Ramps the gap down a level at a time, N requests per level, and stops at the first refusal. It
reports, per level: the target gap, the ACTUAL cycle time, and how much of that cycle was spent
in human-looking activity versus idle waiting. That split is the point — if a session survives a
short gap because the time is filled with scrolling and typing rather than silence, then "faster"
and "more human" are not in tension and the pacing constants are far too conservative.

⚠️ This test is DESIGNED to end in a block. Run it on a session you are willing to lose, never on
one doing production work.
"""
import sys, time, argparse, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cdp_scrape as C
import ojv
from ojv import note
from settle import Settler
from playwright.sync_api import sync_playwright

net = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9352)
    ap.add_argument("--levels", default="45,35,28,22,17,13,10,8,6",
                    help="gap seconds to try, in order")
    ap.add_argument("--per-level", type=int, default=4, help="requests at each level")
    ap.add_argument("--detail", action="store_true", help="ramp causa OPENS instead of searches")
    ap.add_argument("--desde", default="15/07/2026")
    ap.add_argument("--hasta", default="09/08/2026")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    levels = [float(x) for x in a.levels.split(",")]

    with sync_playwright() as pw:
        ctx = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}", timeout=60000).contexts[0]
        p = C.find_ojv_page(ctx)
        if p is None:
            raise SystemExit("no form — walk in first")
        p.bring_to_front()
        p.on("response", ojv.make_tap(net))
        S = Settler(p)
        C.open_fecha_panel(p)
        if p.eval_on_selector("#fecCompetencia", "e=>e.value") != "3":
            C.select_by_kbd(p, "#fecCompetencia", "3")
            ojv.click_away(p)
            S.wait(need="document.querySelectorAll('#fecTribunal option').length>50",
                   quiet_ms=1200, timeout=60, label="tribunales")
        # ⚠️ SET THE DATES. Without them the site answers every Buscar with a validation modal
        # ("Por favor ingrese una Fecha de Inicio"), whose backdrop then covers the button — so
        # human_click reports "objetivo tapado" and every subsequent search comes back stale.
        # On a session where dates were already filled this probe looked fine; on a fresh profile
        # it produced a whole ramp of meaningless failures that looked like a rate limit.
        for sel, val in (("#fecDesde", a.desde), ("#fecHasta", a.hasta)):
            if p.eval_on_selector(sel, "e=>e.value") != val:
                C.type_date_kbd(p, sel, val)
                ojv.click_away(p)
            got = p.eval_on_selector(sel, "e=>e.value")
            if got != val:
                raise SystemExit(f"{sel} reads {got!r}, expected {val!r} — refusing to probe")
        note(f"dates set: {a.desde}..{a.hasta}")

        tl = p.eval_on_selector_all(
            "#fecTribunal option",
            "e=>e.filter(o=>o.value&&o.value!=='0').map(o=>({v:o.value,t:(o.textContent||'').trim()}))")
        note(f"{len(tl)} tribunales | ramping {'CAUSA OPENS' if a.detail else 'SEARCHES'}: {levels}")

        rows, ti, stop = [], 0, None
        for gap in levels:
            note(f"--- level: gap {gap:.0f}s ---")
            for k in range(a.per_level):
                cycle0 = time.time()
                tgt = tl[ti % len(tl)]
                ti += 1

                # --- the human-activity portion of the cycle (keystrokes, scroll, pointer) ---
                act0 = time.time()
                ok = C.select_tribunal_kbd(p, tgt["v"])
                ojv.click_away(p)
                C.human_scroll(p, notches=2)
                act = time.time() - act0
                if not ok:
                    note("    could not select — skipping")
                    continue

                # --- idle top-up so the CYCLE (not the gap) lands on target ---
                idle0 = time.time()
                spent = time.time() - cycle0
                if spent < gap:
                    time.sleep(gap - spent)
                idle = time.time() - idle0

                net.clear()
                C.human_click(p, "#btnConConsultaFec")
                kind, el = ojv.wait_results(p, S, net)
                blocked, why = ojv.blocked(p, net)
                cap = ojv.captcha_frame(p)
                cycle = time.time() - cycle0
                rows.append({"gap": gap, "cycle": round(cycle, 1), "active": round(act, 1),
                             "idle": round(idle, 1), "wait": round(el, 1), "kind": kind,
                             "blocked": blocked, "captcha": cap})
                note(f"    #{len(rows):>2} gap={gap:>4.0f}s cycle={cycle:>5.1f}s "
                     f"(active {act:>4.1f}s idle {idle:>4.1f}s wait {el:>4.1f}s) "
                     f"{kind:8} rpm={60/cycle:.2f}"
                     + (f"  *** {why or 'CAPTCHA'}" if (blocked or cap) else ""))
                if blocked or cap:
                    stop = gap
                    break
            if stop:
                break

        note("")
        if stop:
            note(f"TRIPPED at gap {stop:.0f}s after {len(rows)} requests")
            safe = [r for r in rows if r["gap"] > stop]
            if safe:
                fastest = min(r["gap"] for r in safe)
                cyc = [r["cycle"] for r in safe if r["gap"] == fastest]
                note(f"FASTEST CLEAN level: gap {fastest:.0f}s, "
                     f"cycle {sum(cyc)/len(cyc):.1f}s = {60*len(cyc)/sum(cyc):.2f} req/min")
        else:
            note(f"never tripped across {len(rows)} requests down to gap {levels[-1]:.0f}s")
        act_tot = sum(r["active"] for r in rows)
        idle_tot = sum(r["idle"] for r in rows)
        note(f"time split overall: {act_tot:.0f}s human activity vs {idle_tot:.0f}s idle "
             f"({100*act_tot/max(act_tot+idle_tot, 1):.0f}% active)")
        out = a.out or str(Path(__file__).parent.parent / "data" / "speed_probe.json")
        Path(out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
        note(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
