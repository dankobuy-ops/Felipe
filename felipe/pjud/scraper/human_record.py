"""HUMAN RECORD — watch a person do the whole procedure, and measure what they actually emit.

    python human_record.py --launch          # opens a Chrome for you to drive
    python human_record.py --port 9222       # or attach to one already open

⚠️ IT NAVIGATES NOTHING AND CLICKS NOTHING. The human drives; this only listens. It injects one
passive counter script (Runtime.evaluate, long proven innocent on this site) and reads it once a
second. The moment it started steering, it would be measuring itself.

WHY THIS AND NOT A SCREENSHOT FEED. `--live` publishes a jpeg every few seconds, which is a
slideshow: it shows you WHERE the worker is and never HOW IT MOVED. The three real defects found
this session were all movement — a wheel that scrolled from (0,0), a page that jumped between
inputs with no input device involved, keystrokes arriving in a dropdown with no pointer approach.
None of them would be visible in any number of screenshots. What separates us from a human is a
RATE and a SHAPE, and both have to be counted.

WHAT IT MEASURES, per second and in total:
  * input telemetry the page can see — mousemove, mouseover, wheel, keydown, click, scroll —
    which is the channel we keep discovering we leave empty
  * the pointer's actual path (sampled), so a human's line can be compared with our eased arc
  * every request to pjud.cl, with the GAP since the previous one to the same endpoint
  * `change` on every <select> — this is the cuaderno switch, by name and value
  * when the causa modal opens and closes

THE MEASUREMENT THIS WAS BUILT FOR (2026-08-16): how long a person dwells between opening a causa
and switching to its second cuaderno. Our worker does it in ~4 s. Every clean session ever
recorded spaced two `causaCivil.php` POSTs by 29-38 s, and the remote wall appears only when that
switch is enabled. If a human dwells for twenty seconds reading book 1, then our 4 s is not
impatience, it is a signature.
"""
import argparse
import json
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE.parent / "data" / "human"

# One passive listener set. Capture phase, so nothing the page does can hide an event from us,
# and `passive:true` on the scroll/wheel ones so we cannot possibly delay the page's own handling.
INJECT = r"""
() => {
  if (window.__hr) return 'already';
  // ⚠️ COUNTS PER SECOND CANNOT TELL A HUMAN FROM A METRONOME. A generator firing every 60 ms
  // and a person both read as "16/s"; the difference is entirely in the DISTRIBUTION of the gaps,
  // and until 2026-08-19 this recorder threw that away. `ev` keeps one [kind, t] per event so
  // every channel's inter-arrival distribution can be recovered afterwards. The Python side
  // drains every second, so nothing accumulates in the page and full rate is affordable.
  const K = ['mousemove','mouseover','mouseout','wheel','mousedown','mouseup','keydown','keyup',
             'click','scroll','focusin','focusout','contextmenu','dblclick','select','resize',
             'visibilitychange','blur','selectionchange'];
  const S = window.__hr = {
    c: {mousemove:0, mouseover:0, mouseout:0, wheel:0, mousedown:0, mouseup:0,
        keydown:0, keyup:0, click:0, scroll:0, focusin:0, focusout:0, contextmenu:0,
        dblclick:0, select:0, resize:0, visibilitychange:0, blur:0, selectionchange:0},
    K: K, path: [], keys: [], sel: [], marks: [], ev: [], holds: [], wheels: [],
    down: null, t0: Date.now()
  };
  const bump = (n) => {
    S.c[n] = (S.c[n]||0) + 1;
    const i = K.indexOf(n);
    if (i >= 0) { S.ev.push([i, Date.now() - S.t0]); if (S.ev.length > 40000) S.ev.splice(0, 10000); }
  };
  for (const n of ['mouseover','mouseout','click','focusin','focusout','contextmenu','dblclick'])
    document.addEventListener(n, () => bump(n), true);
  for (const n of ['wheel','scroll'])
    document.addEventListener(n, () => bump(n), {capture:true, passive:true});
  // ⚠️ THE HOLD IS A SIGNATURE. mousedown and mouseup were counted and their SEPARATION thrown
  // away -- yet how long a button stays down is one of the few things a synthetic click cannot
  // help but get wrong, because nothing in the code decides it. A person is 60-120 ms and varies.
  document.addEventListener('mousedown', (e) => {
    bump('mousedown');
    S.down = {t: Date.now(), id: (e.target && e.target.id) || '',
              tag: (e.target && e.target.tagName) || '', x: e.clientX, y: e.clientY};
  }, true);
  document.addEventListener('mouseup', (e) => {
    bump('mouseup');
    if (S.down) {
      S.holds.push([S.down.t - S.t0, Date.now() - S.down.t, S.down.id || S.down.tag,
                    Math.round(Math.hypot(e.clientX - S.down.x, e.clientY - S.down.y))]);
      if (S.holds.length > 4000) S.holds.splice(0, 1000);
      S.down = null;
    }
  }, true);
  // ⚠️ A WHEEL NOTCH HAS A SHAPE. We emitted a count and compared it to a human's count; the
  // delta magnitudes, their sign changes and the gaps between them were never looked at, and a
  // fixed `wheel(0, 300)` is flat where a hand is not. deltaMode matters too (0=px, 1=line).
  document.addEventListener('wheel', (e) => {
    S.wheels.push([Date.now() - S.t0, Math.round(e.deltaX), Math.round(e.deltaY), e.deltaMode]);
    if (S.wheels.length > 4000) S.wheels.splice(0, 1000);
  }, {capture:true, passive:true});
  for (const n of ['resize'])
    window.addEventListener(n, () => bump(n), true);
  document.addEventListener('visibilitychange', () => bump('visibilitychange'), true);
  document.addEventListener('selectionchange', () => bump('selectionchange'), true);
  document.addEventListener('mousemove', (e) => {
    bump('mousemove');
    // Sampled, not every event: enough to draw the line, bounded so a long session cannot grow
    // without limit. Timestamps are what matter -- the shape is in the spacing.
    // ⚠️ SAMPLE GATE LOWERED 40 ms -> 16 ms ON 2026-08-19 (one per frame, which is what the
    // browser coalesces to anyway). At 40 ms the VELOCITY PROFILE was unrecoverable, and that
    // profile is the point: a human move is ballistic then corrective -- fast out, overshoot,
    // settle -- where an eased arc is smooth all the way. Recordings made before this date are
    // coarser; do not compare their curvature against a new one without saying so.
    const p = S.path;
    if (!p.length || Date.now() - p[p.length-1][2] > 16) {
      p.push([Math.round(e.clientX), Math.round(e.clientY), Date.now()]);
      if (p.length > 12000) p.splice(0, 4000);
    }
  }, true);
  document.addEventListener('keydown', (e) => {
    bump('keydown');
    // The KEY is not recorded -- only that one arrived, and when. We are measuring rhythm, and
    // this is a real person's real session on a real account.
    S.keys.push([Date.now(), (e.target && e.target.id) || '']);
    if (S.keys.length > 2000) S.keys.splice(0, 500);
  }, true);
  document.addEventListener('keyup', () => bump('keyup'), true);
  // ★ THE CUADERNO SWITCH. Every <select> change, by id and chosen text.
  document.addEventListener('change', (e) => {
    const t = e.target;
    if (!t || t.tagName !== 'SELECT') return;
    S.sel.push([Date.now(), t.id || t.name || '?',
                (t.options[t.selectedIndex] || {}).text || '', t.value]);
  }, true);
  return 'armed';
}
"""

# Read the counters and the state of the modal in one round trip.
READ = r"""
() => {
  const S = window.__hr;
  if (!S) return null;
  const c = Object.assign({}, S.c);
  for (const k in S.c) S.c[k] = 0;              // deltas: read-and-clear
  const path  = S.path.splice(0, S.path.length);
  const keys  = S.keys.splice(0, S.keys.length);
  const sel   = S.sel.splice(0, S.sel.length);
  const ev    = S.ev.splice(0, S.ev.length);
  const holds = S.holds.splice(0, S.holds.length);
  const wheels= S.wheels.splice(0, S.wheels.length);
  const m = document.querySelector('#modalDetalleCivil');
  const vis = !!m && !!(m.offsetWidth || m.offsetHeight || m.getClientRects().length);
  let rol = '';
  if (vis) {
    const txt = (m.innerText || '');
    const g = txt.match(/[CVE]-\d+-\d{4}/);
    rol = g ? g[0] : '';
  }
  // Which cuaderno is displayed, if the modal is open. The header re-renders per book.
  let cuad = '';
  const cs = document.querySelector('#selCuaderno, select[id*=uaderno], select[name*=uaderno]');
  if (cs) cuad = (cs.options[cs.selectedIndex] || {}).text || '';
  return {c, path, keys, sel, ev, holds, wheels, K: S.K,
          modal: vis, rol, cuad, url: location.href.slice(0, 140)};
}
"""


def arm(page):
    """Inject into a page and every frame it already has. Never raises."""
    try:
        page.evaluate(INJECT)
    except Exception:
        pass


class Rec:
    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8")
        self.t0 = time.time()

    def w(self, kind, **kw):
        kw["kind"] = kind
        kw["t"] = round(time.time() - self.t0, 2)
        self.f.write(json.dumps(kw, ensure_ascii=False) + "\n")
        self.f.flush()


def main():
    ap = argparse.ArgumentParser(
        description="Watch a human drive PJUD and measure what they emit. Records only; never "
                    "navigates or clicks.")
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--launch", action="store_true",
                    help="start a Chrome to drive (same flags the worker uses), on its OWN "
                         "profile so a worker profile is never touched")
    ap.add_argument("--profile", default="",
                    help="profile dir for --launch (default: <LOCALAPPDATA>/pjud_human)")
    ap.add_argument("--minutes", type=float, default=180.0)
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rec = Rec(OUT / f"session-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    print(f"recording -> {rec.f.name}")

    with sync_playwright() as pw:
        # ⚠️ ONE sync_playwright, resolved from the instance we are already inside. worker_a says
        # it plainly: opening a second one to ask for the Chrome path is an error, and it is the
        # error that killed the first remote run on the new code. Same trap, same file away.
        if a.launch:
            import os
            import worker_a as A
            prof = a.profile or str(Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
                                    / "pjud_human")
            proc = A.launch_chrome(a.port, prof, 0, exe=A.chrome_executable(pw))
            if not proc:
                raise SystemExit(f"could not start Chrome on {a.port}")
            print(f"Chrome up on {a.port}, profile {prof}")

        b = None
        for attempt in (1, 2, 3, 4):
            try:
                b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}", timeout=45000)
                break
            except Exception as e:
                print(f"  CDP attempt {attempt}/4: {str(e)[:70]}")
                time.sleep(6)
        if b is None:
            raise SystemExit(f"no CDP on {a.port}")
        ctx = b.contexts[0]

        # ⚠️ ARM ON EVERY FUTURE DOCUMENT TOO. The human is about to navigate several times, and
        # counters injected into the page we happen to find are gone the moment they click.
        try:
            ctx.add_init_script(f"({INJECT})()")
        except Exception as e:
            print(f"  [warn] add_init_script: {str(e)[:60]}")

        seen_req = {}          # endpoint -> last time, so every request carries its own gap

        def on_resp(r):
            try:
                if "pjud.cl" not in r.url:
                    return
                rt = r.request.resource_type
                # ⚠️ THE SITE'S OWN ENDPOINTS ONLY. A single page load pulls ~25 libraries, and a
                # log where consultaFechaCivil.php scrolls past between jquery and moment.js is a
                # log nobody reads. What we are here to time is the .php calls and the xhr.
                if rt in ("image", "stylesheet", "font", "media", "script", "other"):
                    return
                if ".php" not in r.url and rt not in ("xhr", "fetch", "document"):
                    return
                ep = r.url.split("/")[-1].split("?")[0] or r.url
                now = time.time()
                gap = now - seen_req.get(ep, 0) if ep in seen_req else None
                seen_req[ep] = now
                rec.w("req", ep=ep, status=r.status, rt=rt,
                      gap=round(gap, 1) if gap is not None else None)
                g = f"  (+{gap:.1f}s since last {ep})" if gap is not None else ""
                print(f"  [req] {r.status} {ep:<28} {rt}{g}")
            except Exception:
                pass

        ctx.on("response", on_resp)

        armed = set()
        last_state = {}
        t_end = time.time() + a.minutes * 60
        print("\nDRIVE IT. I am only listening. Ctrl-C when you are done.\n")
        tick = 0
        while time.time() < t_end:
            pages = list(ctx.pages)
            for p in pages:
                if p not in armed:
                    arm(p)
                    armed.add(p)
            for p in pages:
                try:
                    st = p.evaluate(READ)
                except Exception:
                    continue
                if not st:
                    arm(p)
                    continue
                c = st["c"]
                tot = sum(c.values())
                key = st["url"][:60]
                prev = last_state.get(key, {})

                for ts, sid, text, val in st["sel"]:
                    rec.w("select", id=sid, text=text, value=val, url=st["url"])
                    print(f"  ★ SELECT {sid} -> {text!r} ({val})")

                if key not in last_state:
                    # First sight of a page is a BASELINE, not a transition. Otherwise every new
                    # tab announces "MODAL CLOSED" before the human has touched anything.
                    last_state[key] = st
                    continue
                if st["modal"] != prev.get("modal"):
                    rec.w("modal", open=st["modal"], rol=st["rol"], cuad=st["cuad"])
                    print(f"  ★ MODAL {'OPEN' if st['modal'] else 'CLOSED'} "
                          f"{st['rol']} cuaderno={st['cuad']!r}")
                elif st["modal"] and st["cuad"] != prev.get("cuad"):
                    rec.w("cuaderno", rol=st["rol"], cuad=st["cuad"])
                    print(f"  ★ CUADERNO now {st['cuad']!r} on {st['rol']}")

                if tot:
                    # ⚠️ NO SILENT TRUNCATION. This wrote `path[:60]` and dropped the rest without
                    # a word — at ~62 samples/s that is most of a second's pointer geometry gone,
                    # in the one file the whole fidelity programme is calibrated from. If a cap is
                    # ever needed again, record that it was hit.
                    rec.w("input", **c, path=st["path"], npath=len(st["path"]),
                          ev=st.get("ev", []), holds=st.get("holds", []),
                          wheels=st.get("wheels", []), K=st.get("K"),
                          nkeys=len(st["keys"]), keys=st["keys"],
                          modal=st["modal"], rol=st["rol"])
                    parts = " ".join(f"{k}={v}" for k, v in c.items() if v)
                    where = f"  [{st['rol']}]" if st["rol"] else ""
                    print(f"  {time.strftime('%H:%M:%S')} {parts}{where}")
                last_state[key] = st
            tick += 1
            if tick % 30 == 0:
                rec.w("heartbeat", pages=len(pages))
            time.sleep(1.0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped — the recording is on disk")
