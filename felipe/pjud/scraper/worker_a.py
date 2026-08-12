"""WORKER A — census + ebook. The discovery worker.

One pass over every civil tribunal in the country (Corte = "Todos") for a date window. For each
tribunal it records the census, and for each BANK causa it finds it opens the causa once and takes
everything that open can give:

    free  (already in the DOM once the modal renders — costs no extra request)
          header, litigantes, escritos, cuaderno list, cuaderno-1 historia
    1 req the EBOOK pdf

Nothing else. Not the other four PDFs, not the receptor modal, not a cuaderno switch — those are
worker B's job, because each is an extra request against the scarce budget.

WHY THIS SHAPE
    Measured 2026-08-06: the search budget and the detail budget are separate, and detail is far
    scarcer. One session ran 19 searches with no search-block, then died on its third causa open.
    So the expensive, fragile act is OPENING A CAUSA — and if we are going to pay for it, we
    should walk away with everything that open makes free, plus the one document that matters
    most. That is the whole thesis this run is testing.

    It also means the modal is where we harvest, not where we shop. Every extra click inside an
    open causa is a separate withdrawal from the budget that is already the binding constraint.

NEVER touches #corteFec. It is the only control that fires a request on change, and walking it
with arrow keys fires one per step (ten in under a second to reach Concepción) — which produced
both the desynced tribunal lists and the blocks of 2026-08-05.

PAGINATION — new here, and it matters. The 2026-08-06 census read only page 1 of each result set,
so its 207 causas are a FLOOR: 33 tribunales reported totals over 100 and 103 reported over 50.
This worker walks the paginator to the end and flags any tribunal where it could not.

Usage
    python worker_a.py --port 9337                    # full national sweep
    python worker_a.py --port 9337 --start 42         # resume at tribunal index 42
    python worker_a.py --port 9337 --max-causas 12    # bounded probe of the detail budget
"""
import os
import sys, json, time, base64, argparse, atexit, subprocess
import random
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cdp_scrape as C
import ojv
from ojv import note
from settle import Settler
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
DATA = HERE.parent / "data" / "worker_a"          # gitignored: scraped data lives in Neon
PDFS = DATA / "pdfs"

# ── pacing ───────────────────────────────────────────────────────────────────
# Operator's standing rule 2026-08-06: "waiting more is the right choice. i'd rather wait a few
# seconds more, than to get blocked." Search spacing at 60 s is the one number with evidence
# behind it — it is what let a single profile run 208 searches in an evening. The detail numbers
# are deliberately far more generous than the 20 s that preceded three-to-ten-open deaths, and
# this run is the experiment that will tell us whether spacing was ever the variable.
# ⚠️ SEARCH_GAP governs EVERY result request, pages included. A paginator click hits
# consultaFechaCivil.php and returns a result set — it is a search in all but name. Pacing it
# separately (PAGE_GAP was 20 s) meant any tribunal over 100 rows quietly fired at three times
# the rate we believed we were using: Taltal has 270 registros, so one worker alone produced 3
# requests in 46 s. With two workers paginating at once the IP saw a request every ~10 s and F5
# refused (2026-08-09, rejF=6). The single-worker sweep never showed it because pagination
# averages 1.28 pages per tribunal, so the bursts were rare and never overlapped.
# 2026-08-10, MEASURED not guessed (speed_probe.py, 51 requests across a human-warmed session
# AND a virgin profile): ramped the gap 45 -> 22 -> 10 -> 6 -> 4 s and never tripped once. At a 4 s
# gap the cycle is still 17-23 s because the SITE's own response time (12-26 s) dominates — we
# cannot go meaningfully faster than PJUD answers. Sustained ~3 req/min against the 1 req/min the
# 60 s gap allowed.
#
# The 60 s was never a real rate limit. It was compensation for input that did not look human:
# a metronome keyboard and no scrolling at all. Fix the behaviour and the budget largely
# disappears. 20 s is deliberately above the fastest CLEAN level rather than at it — margin for a
# slow day, and still 3x the old throughput.
SEARCH_GAP = 20.0      # between result requests of ANY kind — searches AND page advances
# ⚠️ KEEP CONCURRENT WORKERS OUT OF LOCKSTEP. Two workers started together pace from the same
# instant and stay synchronised for ever: observed 2026-08-10, both logging every step at the
# IDENTICAL second, right down to three failed entry attempts. To a rate limiter that is not two
# requests spread across a minute, it is two requests in the same instant, once a minute — the
# worst possible shape, and plausibly why three workers died within six minutes. Each gap gets a
# little noise so the workers drift apart instead of re-colliding, and --offset separates their
# starts in the first place.
GAP_JITTER = 0.15      # ±15% on every inter-request gap
# 2026-08-07: at 45 s the run reached 11 causa opens before a tier-2 block (~24 opens on this
# IP across the afternoon). Detail is the binding constraint and the operator's standing rule is
# "i'd rather wait a few seconds more, than to get blocked", so the gap is doubled. Searches are
# untouched: 60 s is the one number with real evidence behind it (208 searches, one evening).
# 2026-08-10, MEASURED (speed_probe.py --detail, 18 opens on a virgin profile): ramped the gap
# 90 -> 60 -> 40 -> 25 -> 15 -> 8 s. Never tripped, 18/18 ebooks, no block, no CAPTCHA. Below 15 s
# the cycle stops shrinking at ~17.5 s because that IS the work — open the modal, read it, fetch
# the document, close. Same shape as searches: our own floor, not the site's limit.
#
# 90 s gave 0.67 opens/min; the floor is 3.4. Set to 25 s (~2 opens/min, 3x the old rate) rather
# than to the floor: the ramp proves a short burst is safe, it does NOT prove endurance over
# hours, and detail is still the costliest thing we do. Earn the rest with a long run.
CAUSA_GAP = 25.0       # between causa opens
EBOOK_GAP = 4.0        # after the modal renders, before asking for the pdf
POST_CAUSA = 10.0      # after closing a causa, before anything else
# A block is a RATE verdict, so the one thing that must not happen after one is walking straight
# back in at the same pace. Multiplied by the recovery number, so repeat blocks wait ever longer.
COOL_OFF = 180.0
CLEAN_STREAK = 12      # clean causa opens that earn the recovery budget back
# ⚠️ THE SILENT THROTTLE. On 2026-08-07 the session degraded with NO rejection page, NO challenge
# iframe and NO support id — waf_check read it as THROTTLED, ojv.blocked() saw nothing, and the
# run simply kept opening causas that never opened. Four in a row, then a crash. Consecutive
# modal failures with a clean block-check ARE the tell, and nothing else reports them.
MODAL_FAIL_LIMIT = 3
SELECT_FAIL_LIMIT = 5   # consecutive un-selectable tribunales = the form is gone
# How many times a worker may throw its browser away and open another. A wedged form is cured by
# a replacement browser and by nothing else (measured 4x, 2026-08-12), but if the REPLACEMENTS
# keep wedging then the browser was never the fault — and relaunching for ever would bury that
# behind an endless restart loop, which is the same trap the supervisor's restart budget avoids.
MAX_SWAPS = 3

CIVIL = "3"
net = []
# ── pdf capture ──────────────────────────────────────────────────────────────

def classify(body):
    """'pdf' | 'apm' | 'other' — what did the document endpoint actually return?

    ⚠️ "It is over 1000 bytes" is NOT a document. That test is why three files sat on disk named
    *.pdf for a day while every one of them was really F5's <APM_DO_NOT_TOUCH> anti-bot
    interstitial: ~8-14 KB of obfuscated JavaScript, comfortably over any size threshold, with a
    perfectly ordinary 200 status. Check the magic bytes; nothing else is evidence.
    """
    if not body:
        return "other"
    if body[:4] == b"%PDF":
        return "pdf"
    head = body[:400].lstrip()
    if b"APM_DO_NOT_TOUCH" in head or b"TSPD" in body[:2000]:
        return "apm"
    return "other"


def needs_visit(st, causa_id, want_ebook):
    """Should we (re)open this causa? Not just "have we seen it" — have we got what we came for.

    A causa harvested during a --no-ebook pass, or one whose document was refused by the WAF, is
    NOT done: the metadata is banked but the ebook is the other half of the job. Retry those.
    Never retry a causa that simply HAS no ebook control, or whose endpoint served something that
    was not a pdf — those are answers, not failures, and retrying them forever would spend the
    scarcest budget we have on a question already settled.
    """
    rec = st["causas"].get(causa_id)
    if rec is None:
        return True
    if not want_ebook:
        return False
    eb = rec.get("ebook") or {}
    if eb.get("bytes"):
        return False
    return bool(eb.get("skipped") or eb.get("apm_challenge") or eb.get("failed")
                or eb.get("click_refused"))


def tidy_tabs(ctx):
    """Leave exactly the tabs we need: the OJV form page and one www.pjud.cl.

    Operator's standing instruction: close document tabs once we have the bytes. In-page fetching
    means we no longer open any, but a stray click or a leftover from an earlier run still can —
    and stale tabs are not cosmetic here. human_click drives REAL MOUSE COORDINATES, which land
    on whatever tab is actually VISIBLE, so an extra tab silently sends clicks to the wrong page.
    """
    seen_home = False
    for q in list(ctx.pages):
        u = q.url or ""
        try:
            if "/documentos/" in u:
                q.close()
            elif u.rstrip("/") == "https://www.pjud.cl":
                if seen_home:
                    q.close()
                seen_home = True
        except Exception:
            pass


FETCH_DOC_JS = r"""
async (frag) => {
  const f = [...document.querySelectorAll('#modalDetalleCivil form')]
      .find(x => (x.getAttribute('action') || '').toLowerCase().includes(frag));
  if (!f) return {err: 'no form for ' + frag};
  const inp = f.querySelector('input');
  if (!inp) return {err: 'form has no input'};
  const url = new URL(f.getAttribute('action'), location.href).href
            + '?' + encodeURIComponent(inp.name) + '=' + encodeURIComponent(inp.value);
  const t0 = performance.now();
  const r = await fetch(url, {credentials: 'include'});
  const buf = new Uint8Array(await r.arrayBuffer());
  let s = '', CH = 8192;                       // chunked: a 4 MB spread blows the call stack
  for (let i = 0; i < buf.length; i += CH)
    s += String.fromCharCode.apply(null, buf.subarray(i, i + CH));
  return {status: r.status, ct: r.headers.get('content-type'), n: buf.length,
          ms: Math.round(performance.now() - t0), b64: btoa(s)};
}
"""


FETCH_ROW_DOC_JS = r"""
async (frag) => {
  const rows = [...document.querySelectorAll('#historiaCiv table tbody tr')];
  const row = rows.find(tr => (tr.innerText || '').toLowerCase().includes(frag)
                              && tr.querySelector('form'));
  if (!row) return {err: 'no historia row matching ' + frag};
  const f = row.querySelector('form');
  const inp = f.querySelector('input');
  if (!inp) return {err: 'row form has no input'};
  const url = new URL(f.getAttribute('action'), location.href).href
            + '?' + encodeURIComponent(inp.name) + '=' + encodeURIComponent(inp.value);
  const r = await fetch(url, {credentials: 'include'});
  const buf = new Uint8Array(await r.arrayBuffer());
  let s = '', CH = 8192;
  for (let i = 0; i < buf.length; i += CH)
    s += String.fromCharCode.apply(null, buf.subarray(i, i + CH));
  return {status: r.status, ct: r.headers.get('content-type'), n: buf.length, b64: btoa(s)};
}
"""


def grab_row_doc(p, causa_id, label, desc_frag):
    """Fetch the document attached to a HISTORIA row, found by its description text.

    Same in-page fetch as grab_doc — the row's own form carries the action and the JWT, so the
    document is one request with no click and no popup. Matching on the description rather than a
    row index matters: the historia is ordered by folio and a causa with an extra trámite would
    silently hand back a different document.
    """
    return _grab(p, causa_id, label, FETCH_ROW_DOC_JS, desc_frag)


def grab_doc(p, causa_id, label, frag):
    """Fetch one document and write it verified. Returns a record — never raises.

    ⚠️ THE CLICK PATH LOOKS LIKE IT WORKS AND SILENTLY DOES NOT. Clicking a doc icon opens a
    popup, Chrome renders the pdf in its built-in viewer, and the navigation response Playwright
    hands back is the VIEWER'S HOST DOCUMENT — `<embed type="application/x-google-chrome-pdf">`.
    So response.body() returns ~14 KB of wrapper HTML, status 200, for a document that loaded
    perfectly. That one fact caused both wrong calls of 2026-08-07: three wrapper files sat on
    disk named *.pdf, and later a perfectly good scripted click was reported as a WAF block.

    So we do not click. The PAGE fetches the document itself — same origin, its own cookies, the
    same request the click would have made — and hands back the bytes. Same cost (one request),
    no popup to close, no viewer in the way, and the result is either %PDF or it is not.

    This is NOT the out-of-process APIRequestContext the handoff warns about: that fetch happens
    outside the browser with copied cookies, which is the thing that looks nothing like a user.
    This runs inside the page that is already holding the session.
    """
    return _grab(p, causa_id, label, FETCH_DOC_JS, frag)


def _grab(p, causa_id, label, js, arg):
    """Shared body of grab_doc / grab_row_doc: run the fetch, verify %PDF, write it down."""
    t0 = time.time()
    try:
        res = p.evaluate(js, arg)
    except Exception as e:
        msg = str(e)
        # ⚠️ "TypeError: Failed to fetch" is the request being REFUSED at the network layer, not a
        # bug in the page. There is no rejection frame and no challenge iframe, so blocked() sees
        # nothing and the worker keeps paying for causa opens whose documents are all being
        # denied — 2026-08-10, slot 1 ran on for two more opens that way while its sibling had
        # already taken a visible block. Flag it as a refusal so it counts toward the throttle.
        refused = "Failed to fetch" in msg or "ERR_" in msg
        note(f"      {label}: fetch {'REFUSED at network level' if refused else 'threw'} — "
             f"{msg[:70]}")
        return {"bytes": 0, "failed": True, "refused": refused}
    el = round(time.time() - t0, 1)
    if res.get("err"):
        note(f"      {label}: {res['err']}")
        return {"bytes": 0, "missing": True}
    body = base64.b64decode(res["b64"])
    if body[:4] != b"%PDF":
        kind = classify(body)
        note(f"      {label}: {res['status']} {res.get('ct')} {len(body):,} B is NOT a pdf "
             f"({kind}) after {el}s")
        if kind == "apm":
            return {"bytes": 0, "apm_challenge": True, "secs": el}
        (PDFS / f"{causa_id}__{label}.bin").write_bytes(body)
        return {"bytes": 0, "not_pdf": True, "secs": el}
    fn = PDFS / f"{causa_id}__{label}.pdf"
    fn.write_bytes(body)
    note(f"      {label}: {len(body):,} B PDF in {el}s -> {fn.name}")
    return {"bytes": len(body), "file": fn.name, "secs": el, "ct": res.get("ct")}


# ── one causa ────────────────────────────────────────────────────────────────

def proc_matches(rec, pattern):
    """Does this causa's procedimiento match what we are collecting?

    ⚠️ This can only be asked AFTER the causa is open. The results table carries Rol, Fecha,
    Caratulado and Tribunal — no procedimiento — so the list-level filter can only be "a C- rol
    with a bank among the parties". That is a real filter, but a loose one: it also matches Ley de
    Bancos, Liquidación Forzosa and Juicio de arrendamiento, which is why ~12% of what we stored
    was not what anyone asked for. The open is already spent by the time we know; what this saves
    is the document fetch and a wrong row in Neon.
    """
    if not pattern:
        return True
    got = C.norm((rec.get("header") or {}).get("procedimiento", ""))
    return re.search(pattern, got, re.I) is not None


def harvest_causa(ctx, p, trib_id, trib_name, row, want_ebook=True, only_proc=""):
    """Open the causa, take everything free, take the ebook, close. Returns the record or None
    if the modal never opened (which is NOT by itself a block — the caller checks that)."""
    causa_id = f"{trib_id}-{row['rol']}"
    note(f"    open {causa_id}  {row['car'][:52]}")
    C.human_click(p, p.locator("#dtaTableDetalleFecha tbody tr").nth(row["i"])
                  .locator("a[onclick*='detalleCausaCivil']").first, timeout=8000)
    t0 = time.time()
    opened = False
    while time.time() - t0 < 90:
        p.wait_for_timeout(400)
        try:
            if p.evaluate("(rol)=>{const m=document.querySelector('#modalDetalleCivil');"
                          "return !!m && m.innerText.indexOf(rol)>=0;}", row["rol"]):
                opened = True
                break
        except Exception:
            pass
    if not opened:
        note(f"    modal did not open after {time.time()-t0:.0f}s")
        return None
    p.wait_for_timeout(1500)                  # let the tabs inside the modal finish rendering
    C.human_scroll(p, notches=random.randint(2, 5))   # the modal is long; nobody reads it static

    # ---- free harvest: all of this is already in the DOM, none of it costs a request ----
    rec = {"causa_id": causa_id, "tribunal_id": trib_id, "tribunal": trib_name,
           "rol": row["rol"], "caratulado": row["car"], "fecha_ing": row.get("fecha", ""),
           "opened_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    for key, fn in (("header", C.parse_header), ("litigantes", C.parse_litigantes),
                    ("escritos", C.parse_escritos), ("historia_c1", C.parse_historia)):
        try:
            rec[key] = fn(p)
        except Exception as e:
            rec[key] = None
            note(f"      [warn] {key}: {str(e)[:60]}")
    try:
        rec["cuadernos"] = [c["txt"] for c in (C.cuaderno_options(p) or [])]
    except Exception:
        rec["cuadernos"] = []
    proc = (rec.get("header") or {}).get("procedimiento", "")
    note(f"      {len(rec.get('litigantes') or [])} litigantes · "
         f"{len(rec.get('historia_c1') or [])} historia c1 · "
         f"{len(rec['cuadernos'])} cuadernos · {proc[:40]}")

    if only_proc and not proc_matches(rec, only_proc):
        # Recorded, so it is never re-opened, but flagged so nothing downstream stores it and no
        # document is bought for it.
        rec["skipped_proc"] = True
        rec["ebook"] = {"bytes": 0, "skipped_proc": True}
        note(f"      procedimiento {proc[:40]!r} does not match — no document, not stored")
        C.close_modal(p, "#modalDetalleCivil")
        p.wait_for_timeout(1200)
        C.clear_stuck_modal(p)
        return rec
    if want_ebook:
        time.sleep(EBOOK_GAP)
        rec["ebook"] = grab_doc(p, causa_id, "ebook", "newebook")
    else:
        rec["ebook"] = {"bytes": 0, "skipped": True}
    # worker B's queue: what we deliberately did NOT take while we were in here
    rec["docs_pending"] = ["texto_demanda", "certificado", "ingreso_demanda_c1"] + \
                          (["mandamiento_c2"] if len(rec["cuadernos"]) > 1 else []) + \
                          ([] if rec["ebook"].get("bytes") else ["ebook"])
    C.close_modal(p, "#modalDetalleCivil")
    p.wait_for_timeout(1500)
    C.clear_stuck_modal(p)
    return rec


# ── results harvesting, with pagination ──────────────────────────────────────

def page_banks(p, page_no):
    return [dict(r, page=page_no) for r in C.page_rows(p)
            if r["has"] and r["rol"].upper().startswith("C") and C.is_bank(r["car"])]


def gap_for(base=None):
    """An inter-request gap with jitter, so parallel workers do not fire in unison."""
    base = SEARCH_GAP if base is None else base
    return base * (1.0 + random.uniform(-GAP_JITTER, GAP_JITTER))


def advance(p, page):
    """'more' | 'done' | 'stuck' — walk the paginator one step.

    Detail is harvested PAGE BY PAGE, never after paginating to the end: a row's index is an
    index into the page it was read from, so clicking page-1 indices while the last page is on
    screen opens the WRONG causas. Harvest here, then advance.

    The end signal is the site's own greyed-out Siguiente, NOT "rows seen >= total". Counting
    rows is off by the blank filler row the table always carries, and an accumulated overcount
    stops the walk one page early — a silent truncation of exactly the biggest tribunales, which
    is the failure this pagination was added to fix in the first place. `next_page` also returns
    a REASON rather than a bool so a slow paginator AJAX cannot be mistaken for the last page;
    that confusion once turned 135 causas into 91.
    """
    if C.sig_disabled(p):
        return "done"
    why = C.next_page(p)
    if why == "last":
        return "done"
    if why == "stuck":
        note(f"      [!] paginator stuck after page {page} — flagging tribunal INCOMPLETE")
        return "stuck"
    return "more"


def close_chrome(proc, profile=None):
    """Kill the Chrome WE launched, and its children.

    ⚠️ terminate() is not enough on Windows: the window goes but the renderer and crashpad
    children survive, so the port stays bound and the profile stays locked. taskkill /T takes
    the whole tree.

    ⚠️ AND DO NOT TRUST proc.poll(). Chrome routinely re-launches itself into a fresh process and
    lets the one we spawned exit at once, so poll() reports "already gone" while a complete
    browser is still running — still holding the profile directory, still LISTENING ON THE
    DEBUGGING PORT. The old early-return therefore closed nothing at all: on 2026-08-12 slots 2
    and 3 each exited cleanly on form-loss and left ten live chrome.exe processes behind.
    That is not untidiness. The supervisor decides whether a slot still has a usable browser by
    asking whether CDP answers, so an orphan tells it "browser is fine" and it restarts the
    worker onto the very session that just wedged — which is exactly what a form-loss restart is
    supposed to avoid.
    So: kill the tree we know about, THEN sweep for anything still holding our own profile dir.
    """
    try:
        if proc is not None and proc.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
            else:
                proc.terminate()
    except Exception:
        pass
    if not profile or os.name != "nt":
        return
    try:
        # The profile path goes through the ENVIRONMENT, never inlined into the command string:
        # it is a Windows path full of backslashes, and PowerShell escapes with a backtick, so
        # embedding it would break the quoting the same way it broke the supervisor on 08-11.
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" "
             "-ErrorAction SilentlyContinue | "
             "Where-Object { $_.CommandLine -like $env:PJUD_PROF } | "
             "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
            env={**os.environ, "PJUD_PROF": f"*{profile}*"},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        note(f"closed the Chrome this worker opened ({Path(profile).name})")
    except Exception:
        pass


def launch_chrome(port, profile, slot=1):
    """Start this worker's OWN Chrome and wait for its CDP port.

    ⚠️ THE BROWSER IS PART OF THE ENTRY, which is the operator's point and it is right: four
    fresh Chromes all loading pjud.cl is itself the burst, regardless of when the Python
    processes started. Gating only the worker still let four brand-new sessions appear at once.
    So Chrome is launched INSIDE the entry lock, and the next worker does not even open a window
    until the previous one is on the form.
    """
    import urllib.request
    exe = (r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if not Path(exe).exists():
        exe = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    Path(profile).mkdir(parents=True, exist_ok=True)
    note(f"launching Chrome on {port} ({Path(profile).name})")
    # The occlusion flags are BELT AND BRACES, not a fix for anything measured.
    # ⚠️ Do not let the earlier note here mislead you again: it claimed a covered window reports
    # document.visibilityState = "hidden" and therefore cannot clear F5's challenge. That was
    # tested on 2026-08-10 with two Chromes stacked at the same coordinates, and it is FALSE —
    # the fully covered window read "visible" both with the flags and without them. So occlusion
    # was never the cause of the "3 minutes and a blank site"; that was entry landing on the OJV
    # home instead of the search form, while the site was having problems.
    # The flags are kept because they cost nothing and do stop Chrome throttling a background
    # tab's timers, which the challenge script does need. Windows are TILED rather than maximised
    # so all four stay watchable.
    x, y = (slot % 2) * 780, ((slot // 2) % 2) * 470
    proc = subprocess.Popen([exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                      "--no-first-run", "--no-default-browser-check",
                      "--disable-features=CalculateNativeWinOcclusion",
                      "--disable-backgrounding-occluded-windows",
                      "--disable-renderer-backgrounding",
                      "--disable-background-timer-throttling",
                      f"--window-size=760,440", f"--window-position={x},{y}",
                      "https://www.pjud.cl/"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # ⚠️ A WORKER THAT ENDS ITS JOB TAKES ITS BROWSER WITH IT (operator, 2026-08-11). We opened
    # this window, so we own it: slot 3 finished its 70 tribunales at 16:34 and left a Chrome
    # sitting on the desktop with nothing driving it. Left alone overnight that is four dead
    # browsers holding four profiles and four debugging ports — and a listening port is exactly
    # how the supervisor decides whether a slot still has a usable browser, so an abandoned one
    # actively misleads it. atexit covers every way out: DONE, block, form-loss, or a raise.
    atexit.register(close_chrome, proc, profile)
    for _ in range(45):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read()
            note(f"Chrome up on {port}")
            # Returns the PROCESS, not True, so a caller that needs to replace this browser later
            # has the handle to close first. Still truthy, so `if not launch_chrome(...)` reads
            # exactly as it did.
            return proc
        except Exception:
            time.sleep(1)
    note(f"Chrome never opened CDP on {port}")
    close_chrome(proc, profile)      # never leave a half-started Chrome holding the profile
    return None


def enter_and_setup(ctx, net, desde, hasta, lock=None):
    """Walk in and build the search form. Returns (page, Settler, tribunal list).

    Module level and parameterised so worker B shares it verbatim. Entry, the Competencia
    cascade, the corte guard and the date read-back are exactly where a second copy would
    drift — and drift here is invisible until a run searches the wrong window and files live
    tribunales as empty, which is what happened on 2026-08-08.

    Also the recovery path. A tier-2 block leaves TSBrPFrame_cs_chlg_* frames parked on a
    session that is otherwise fine, and re-entry clears them — measured 2026-08-07, 18 s,
    0 rejection frames afterwards, same profile. NOTHING is burned by a block, so rotating
    the profile dir (which waf_check still advises) throws away a warm session for nothing.
    """
    tidy_tabs(ctx)
    # A modal left open by a crashed run blocks every keyboard select that follows, so
    # the whole sweep reports "could not select" for all 230 tribunales.
    for q in list(ctx.pages):
        try:
            if q.query_selector("#modalDetalleCivil"):
                C.clear_stuck_modal(q)
        except Exception:
            pass
    # ⚠️ ONE WORKER WALKS IN AT A TIME. Fixed offsets do not work: entry takes about three
    # minutes, so an 8 s (or even 50 s) stagger still leaves every worker inside the entry
    # sequence at once — four of them logged the identical steps within two seconds of each
    # other and none got in. Operator's call, and the right one: a condition, not a timer.
    # If the caller already holds the lock (it launched Chrome under it) do NOT take it again,
    # and do not release it either — the caller holds it until its first search comes back.
    # Recovery re-entries take their own lock and release it here, since a worker that is
    # already established is not a new arrival and has nothing to prove to the queue.
    own = lock is None
    if own:
        lock = ojv.EntryLock(DATA.parent / "entry.lock")
        lock.acquire()
    try:
        pg = ojv.walk_in(ctx)
    finally:
        if own:
            lock.release()            # released whether we got in or not — never strand the queue
    lock.touch()                      # alive and on the form: do not let the stale timer fire
    if pg is None:
        return None, None, None
    note(f"in: {pg.url[:60]}")
    del net[:]
    pg.on("response", ojv.make_tap(net))
    settler = Settler(pg)
    C.open_fecha_panel(pg)
    # Competencia is the ONLY cascade we trigger; corte stays on "Todos"
    if pg.eval_on_selector("#fecCompetencia", "e=>e.value") != CIVIL:
        note("Competencia = Civil")
        C.select_by_kbd(pg, "#fecCompetencia", CIVIL)
        ojv.click_away(pg)
        settler.wait(need="document.querySelectorAll('#fecTribunal option').length>50",
                     quiet_ms=1200, timeout=60, label="all-tribunales")
    corte = pg.eval_on_selector("#corteFec", "e=>e.value")
    if corte not in ("", "0"):
        note(f"[!] corte={corte}, expected Todos — refusing to change it (the burst)")
        raise SystemExit(2)
    for sel, val in (("#fecDesde", desde), ("#fecHasta", hasta)):
        if pg.eval_on_selector(sel, "e=>e.value") != val:
            C.type_date_kbd(pg, sel, val)
            ojv.click_away(pg)
        # Read it BACK. Typing is not proof it arrived, and a wrong window does not fail
        # loudly — it returns plausible-looking results for the wrong dates.
        got = pg.eval_on_selector(sel, "e=>e.value")
        if got != val:
            raise SystemExit(f"{sel} reads {got!r}, expected {val!r} — refusing to search")
    lst = pg.eval_on_selector_all("#fecTribunal option",
                                  "e=>e.filter(o=>o.value&&o.value!=='0')"
                                  ".map(o=>({v:o.value,t:(o.textContent||'').trim()}))")
    note(f"tribunales={len(lst)} corte=Todos dates "
         f"{pg.eval_on_selector('#fecDesde','e=>e.value')}.."
         f"{pg.eval_on_selector('#fecHasta','e=>e.value')}")
    return pg, settler, lst


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9337)
    ap.add_argument("--start", type=int, default=0, help="tribunal index to resume at")
    ap.add_argument("--end", type=int, default=0,
                    help="stop AFTER this tribunal index (0 = to the end). With --start this "
                         "carves a disjoint slice, which is how several workers share one sweep "
                         "without ever searching the same tribunal twice.")
    ap.add_argument("--only-proc", default="",
                    help="regex on procedimiento, e.g. 'obligaci.*dar'. Causas that do not match "
                         "are recorded (so they are never re-opened) but get no document and are "
                         "not written to Neon. Only knowable after the open: the results table "
                         "has no procedimiento column.")
    ap.add_argument("--causa-gap", type=float, default=0.0,
                    help="override CAUSA_GAP. Concurrent DETAIL workers must each go SLOWER: the "
                         "budget looks like ~1.4 request-equivalents/min per IP and a causa open "
                         "costs two (the open plus its document), so two workers at the "
                         "single-worker pace spend about double the ceiling.")
    ap.add_argument("--post-causa", type=float, default=0.0, help="override POST_CAUSA")
    ap.add_argument("--launch-chrome", action="store_true",
                    help="this worker starts its OWN Chrome, inside the entry lock, so no two "
                         "brand-new sessions ever appear at the same moment.")
    ap.add_argument("--chrome-profile", default="",
                    # ⚠️ %% — argparse %-expands help strings, so a literal % here makes --help
                    # itself raise "unsupported format character". It did, silently, until
                    # 2026-08-12: nobody had run --help since the flag was added.
                    help=r"profile dir for --launch-chrome (default: %%LOCALAPPDATA%%\pjud_wA<slot>)")
    ap.add_argument("--offset", type=float, default=0.0,
                    help="seconds to wait before the FIRST request. Give each concurrent worker "
                         "a different offset (e.g. 0 and 30 with a 60 s gap) so their requests "
                         "interleave instead of arriving together.")
    ap.add_argument("--slot", type=int, default=0,
                    help="worker number. Each slot gets its OWN state.json and pdfs/ under "
                         "data/worker_a<N>. Two workers sharing one state file would interleave "
                         "non-atomic writes and shred it - the file is rewritten whole after "
                         "every causa.")
    ap.add_argument("--desde", default="15/07/2026")
    ap.add_argument("--hasta", default="07/08/2026")
    ap.add_argument("--max-causas", type=int, default=0,
                    help="stop after N causa opens (0 = no limit). For probing the budget.")
    ap.add_argument("--no-detail", action="store_true", help="census only, open nothing")
    ap.add_argument("--max-recover", type=int, default=6,
                    help="how many times a block may be cleared by re-entry before giving up. "
                         "Re-entry works because a tier-2 block parks challenge frames on a "
                         "session that is otherwise healthy; nothing about the profile is burned.")
    ap.add_argument("--no-ebook", action="store_true",
                    help="open causas and take the FREE metadata, but request no document. "
                         "The causa open is the scarce act and its metadata is worth having on "
                         "its own, so a document problem never needs to idle the profile.")
    a = ap.parse_args()

    # ⚠️ Validate the window FIRST. PowerShell's Get-Date -Format "dd/MM/yyyy" returns
    # "08-08-2026" under an es-CL locale — "/" in a .NET format string means "the culture's date
    # separator", not a literal slash. That malformed date reached the form, the search went
    # nonsense, and the run recorded a real tribunal as EMPTY. Refuse it at the door.
    for label, val in (("--desde", a.desde), ("--hasta", a.hasta)):
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", val):
            raise SystemExit(f"{label}={val!r} is not dd/mm/yyyy — refusing to search with it")

    global DATA, PDFS, CAUSA_GAP, POST_CAUSA
    if a.causa_gap:
        CAUSA_GAP = a.causa_gap
    if a.post_causa:
        POST_CAUSA = a.post_causa
    if a.slot:
        DATA = HERE.parent / "data" / f"worker_a{a.slot}"
        PDFS = DATA / "pdfs"
    PDFS.mkdir(parents=True, exist_ok=True)
    STATE = DATA / "state.json"
    note(f"slot {a.slot or 0}: state -> {STATE}")
    note(f"pacing: search {SEARCH_GAP:.0f}s  causa {CAUSA_GAP:.0f}s  post {POST_CAUSA:.0f}s"
         f"  offset {a.offset:.0f}s  jitter ±{GAP_JITTER*100:.0f}%")
    st = {"meta": {}, "tribunales": {}, "causas": {}}
    if STATE.exists() and STATE.stat().st_size:
        try:
            st = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception as e:
            # A crash mid-write leaves a truncated file. Refusing to start on it would block every
            # future resume, so keep the wreck for inspection and begin a fresh state.
            bad = STATE.with_suffix(f".bad.{int(time.time())}.json")
            STATE.rename(bad)
            note(f"[!] unreadable state ({str(e)[:50]}) — moved to {bad.name}, starting fresh")
    # ⚠️ A state file belongs to ONE date window. Tribunal completion is recorded per tribunal
    # with no window attached, so resuming a 15/07 state against a 01/07 window would skip every
    # tribunal marked complete — silently reporting a finished sweep that never searched these
    # dates at all. Refuse, and say what to do about it.
    prev_w = (st["meta"].get("desde"), st["meta"].get("hasta"))
    if st.get("tribunales") and prev_w != (None, None) and prev_w != (a.desde, a.hasta):
        raise SystemExit(
            f"state.json holds the window {prev_w[0]}..{prev_w[1]}, you asked for "
            f"{a.desde}..{a.hasta}. Completion is recorded per tribunal with no window, so "
            f"resuming would skip tribunales never searched for these dates. "
            f"Use --slot N for a separate state, or move {STATE} aside first.")
    # ⚠️ RECORD THE ASSIGNED RANGE. The supervisor used to infer it from min/max of the tribunal
    # indices in state — but state accumulates across runs with different shard boundaries, so on
    # 2026-08-11 it restarted the slots as 39-120, 78-171 and 117-229: overlapping, each redoing
    # its neighbour's courts. What this slot was TOLD to sweep is a fact only this process knows.
    st["meta"].update({"desde": a.desde, "hasta": a.hasta, "port": a.port,
                       "start": a.start, "end": a.end,
                       "last_run": time.strftime("%Y-%m-%d %H:%M:%S")})

    def save():
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    tally = {"searches": 0, "pages": 0, "opens": 0, "ebooks": 0, "bytes": 0, "apm": 0}

    def tally_line(tag):
        note(f"{tag}  searches={tally['searches']} extra_pages={tally['pages']} "
             f"causa_opens={tally['opens']} ebooks={tally['ebooks']} "
             f"apm_challenged={tally['apm']} pdf_bytes={tally['bytes']:,}")

    with sync_playwright() as pw:
        # Do not even try to attach if the machine is offline: every symptom downstream would
        # be misread as the site refusing us.
        if not ojv.internet_up():
            if not ojv.wait_for_internet()[0]:
                raise SystemExit("offline at startup — nothing to do")
        # The wedge seen repeatedly since 2026-08-06: the socket listens but the handshake never
        # completes, always after heavy document traffic. Restarting Chrome on the SAME profile
        # dir fixes it — cookies and TSPD_101_DID survive, nothing is burned.
        # ⚠️ RETRY, do not exit on the first failure. Chrome needs a few seconds after a restart
        # before it will complete a handshake, and the supervisor relaunches Chrome immediately
        # before relaunching this — so a single attempt raced it and the run died on arrival
        # (2026-08-09, sweep.log left at 0 bytes with only a handshake error beside it).
        # ⚠️ HOLD THE ENTRY LOCK ACROSS THE WHOLE ARRIVAL: launching Chrome, loading pjud.cl,
        # walking in, and the first search. Four fresh browsers appearing together IS the burst,
        # so gating only the Python process — which is what the first version did — changed
        # nothing at all.
        # ⚠️ TAKEN UNCONDITIONALLY, not only under --launch-chrome. An arrival is an arrival
        # whether or not this process opened the window: the supervisor restarts a worker onto an
        # ALREADY-RUNNING Chrome, and that worker still walks in and still searches. Gating only
        # the launch left exactly that path — the one that fires unattended at 3 a.m. — ungated,
        # and released on the form instead of on a confirmed search.
        boot_lock = ojv.EntryLock(DATA.parent / "entry.lock")
        boot_lock.acquire()
        # Held so a wedged form can be answered with a REPLACEMENT browser later — see
        # fresh_browser(). A worker that did not open its own Chrome has neither, and says so
        # rather than killing a window the operator opened by hand.
        chrome_prof = None
        chrome_proc = None
        if a.launch_chrome:
            chrome_prof = a.chrome_profile or str(
                Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / f"pjud_wA{a.slot or 0}")
            chrome_proc = launch_chrome(a.port, chrome_prof, a.slot or 1)
            if not chrome_proc:
                boot_lock.release()
                raise SystemExit(f"could not start Chrome on {a.port}")

        b = None
        for attempt in (1, 2, 3, 4):
            try:
                b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}", timeout=45000)
                break
            except Exception as e:
                note(f"CDP handshake attempt {attempt}/4 failed: {str(e)[:70]}")
                if attempt < 4:
                    time.sleep(15)
        if b is None:
            raise SystemExit(f"CDP never completed a handshake on {a.port}. "
                             f"Restart Chrome on the SAME --user-data-dir and retry.")
        ctx = b.contexts[0]

        # Entry is retried too: a single failed walk-in used to end the run outright, which on a
        # slow link means a whole sweep lost to one slow page load.
        p = S = tl = None
        for attempt in (1, 2, 3):
            p, S, tl = enter_and_setup(ctx, net, a.desde, a.hasta, lock=boot_lock)
            if p is not None:
                # A form with no tribunales means we are LOOKING at the page but something is
                # covering it — a CAPTCHA frame, typically. Retrying cannot help.
                if len(tl or []) < 50:
                    for q in ctx.pages:
                        if ojv.captcha_frame(q):
                            raise SystemExit(
                                "TIER-3 IMAGE CAPTCHA on screen — a human must clear it. "
                                "Not attempting to bypass.")
                break
            note(f"entry attempt {attempt}/3 failed")
            if not ojv.internet_up() and not ojv.wait_for_internet()[0]:
                raise SystemExit("offline — stopping")
            time.sleep(20)
        # ⚠️ THE LOCK STAYS SHUT HERE. Being on the form is not the condition — a confirmed
        # search is (see EntryLock). It is released down in the sweep loop, the moment this
        # worker's first search returns a verdict. The one exception is failing to get in at
        # all: then there is nothing to confirm and holding the gate would strand the fleet.
        if p is None:
            if boot_lock:
                boot_lock.release()
            raise SystemExit("could not reach the form after 3 attempts")
        if boot_lock:
            boot_lock.touch()
            note("on the form — holding the entry lock until my first search comes back")
        if len(tl) < 50:
            raise SystemExit("not the national list — aborting")

        recoveries = 0
        clean_since_block = 0
        swaps = 0
        start_ip = ojv.public_ip()
        note(f"public IP at start: {start_ip}")

        def fresh_browser():
            """Throw this Chrome away, open another, and walk in. True if we are searching again.

            ⚠️ A WEDGED FORM IS NOT A RATE VERDICT, AND RE-ENTRY CANNOT FIX IT. Measured four
            times on 2026-08-12: slots 1, 2 and 3 each reached the point where every
            select_tribunal_kbd failed — the option list gone or the value refusing to stick —
            and in every case a REPLACEMENT browser was back on the form and searching within a
            minute, while in-session re-entry was not. Slot 1 proved the negative directly: it
            spent a full 180 s cool-off and a clean re-entry, still could not select a tribunal,
            and died anyway; relaunched onto a new Chrome it pulled the very same court (Arica,
            139 registros) on its first search.

            So the recovery ladder needed a second rung. Cooling off answers a RATE verdict;
            this answers a broken SESSION, and spending six cool-offs on the second is how a
            worker loses twenty minutes and then stops anyway.

            ⚠️ IT ARRIVES THROUGH THE ENTRY GATE, like any other new session. A replacement is a
            brand-new browser loading pjud.cl, which is precisely the burst the lock exists to
            prevent — and the lock is handed to `boot_lock` so the sweep loop releases it on the
            next CONFIRMED SEARCH, not merely on reaching the form.
            """
            nonlocal b, ctx, p, S, tl, last_search, boot_lock, chrome_proc, swaps
            if not chrome_prof:
                note("  *** the form is unusable, but this worker did not open its own Chrome "
                     "so it must not close one. Stopping for the supervisor to replace it.")
                return False
            swaps += 1
            note(f"  browser swap {swaps}: replacing this Chrome and walking in again")
            lock = ojv.EntryLock(DATA.parent / "entry.lock")
            lock.acquire()
            ok = False
            try:
                close_chrome(chrome_proc, chrome_prof)
                time.sleep(6)                      # let the profile lock and the port go
                chrome_proc = launch_chrome(a.port, chrome_prof, a.slot or 1)
                if not chrome_proc:
                    note("  *** the replacement Chrome never opened CDP")
                    return False
                lock.touch()
                for attempt in (1, 2, 3):
                    try:
                        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}",
                                                         timeout=45000)
                        break
                    except Exception as e:
                        note(f"  CDP handshake {attempt}/3 after the swap: {str(e)[:60]}")
                        time.sleep(12)
                else:
                    note("  *** the replacement Chrome never completed a CDP handshake")
                    return False
                ctx = b.contexts[0]
                lock.touch()
                p, S, tl = enter_and_setup(ctx, net, a.desde, a.hasta, lock=lock)
                ok = p is not None and len(tl or []) >= 50
                if not ok:
                    note("  *** the replacement browser did not reach the national form")
                return ok
            finally:
                if ok:
                    # Hand the gate to the sweep loop, which releases it on the next confirmed
                    # search. Releasing here would open the queue on the strength of a form,
                    # which is exactly the mistake EntryLock's docstring warns about.
                    boot_lock = lock
                    last_search = 0.0
                else:
                    lock.release()

        def recover(idx):
            """Re-enter after a block. True if we may carry on from `idx`."""
            nonlocal p, S, tl, recoveries, last_search, clean_since_block
            # ⚠️ CONNECTIVITY FIRST. An internet outage produces exactly the symptoms of a block —
            # searches that never prove fresh, causas that never open — but none of the remedies
            # apply: cooling off does nothing, and after enough of them the profile gets rotated
            # for a fault that was never the site's. Check before charging anything to the budget.
            if not ojv.internet_up():
                back, waited = ojv.wait_for_internet()
                if not back:
                    note(f"  *** offline and not coming back — stopping. resume with --start {idx}")
                    return False
                # An IP change (modem reset, switching connection) usually costs the session, so
                # re-enter — but do NOT count it as a recovery. Nothing was spent.
                # ⚠️ DID THE ADDRESS MOVE? F5 binds its session to the IP it issued it to, so an
                # old profile on a NEW address is refused on its very first search — observed
                # 2026-08-09, rejF=2 on search #1 straight after switching to a mobile connection.
                # Re-entry cannot fix that; only a fresh profile can, and the supervisor owns
                # profiles. Exit 6 so it rotates rather than burning the recovery budget on a
                # session that is already void.
                now_ip = ojv.public_ip()
                if start_ip and now_ip and now_ip != start_ip:
                    note(f"  *** IP CHANGED during the outage ({start_ip} -> {now_ip}). The F5 "
                         f"session is bound to the old address and is void.")
                    note(f"  *** exiting 6 = needs a FRESH PROFILE. resume with --start {idx}")
                    save()
                    raise SystemExit(6)
                p, S, tl = enter_and_setup(ctx, net, a.desde, a.hasta)
                if p is None:
                    note("  *** could not re-enter after the outage — stopping")
                    return False
                last_search = 0.0
                note(f"  re-entered after a {waited / 60:.1f} min outage — budget untouched")
                return True
            recoveries += 1
            clean_since_block = 0
            if recoveries > a.max_recover:
                note(f"  *** {recoveries - 1} recoveries already used — stopping. "
                     f"resume with --start {idx}")
                return False
            # Back off HARD before re-entering. The block is a rate verdict, so walking straight
            # back in at the same pace just earns another one; each successive block waits longer.
            cool = COOL_OFF * recoveries
            note(f"  recovery {recoveries}/{a.max_recover}: cooling off {cool:.0f}s, then re-entry")
            time.sleep(cool)
            p, S, tl = enter_and_setup(ctx, net, a.desde, a.hasta)
            if p is None:
                # ⚠️ SECOND RUNG BEFORE GIVING UP. Re-entry failing is not proof that a human is
                # needed — it is equally what a wedged browser looks like, and the two were
                # indistinguishable here until 2026-08-12. A tier-3 CAPTCHA is detected by
                # walk_in() and reported explicitly, so an unexplained failure earns one
                # replacement browser before the run stops.
                note("  *** re-entry failed — trying a replacement browser before giving up")
                if swaps < MAX_SWAPS and fresh_browser():
                    note(f"  recovered onto a new browser — resuming at idx {idx}")
                    return True
                note("  *** could not recover (tier-3 CAPTCHA needs a human?) — stopping. "
                     f"resume with --start {idx}")
                return False
            last_search = 0.0
            note(f"  recovered — resuming at idx {idx}")
            return True

        if a.offset:
            # The offset is a timer whose whole purpose is to keep workers apart, and we are
            # currently holding the gate that does that properly. Sleeping here would stall the
            # other three for no benefit at all, so spend it only when we are not the holder.
            if boot_lock and boot_lock.held:
                note(f"skipping the {a.offset:.0f}s offset — the entry lock already spaces us, "
                     f"and sleeping under it would stall the queue")
            else:
                note(f"offset: waiting {a.offset:.0f}s so this worker interleaves with the others")
                time.sleep(a.offset)
        last_search = 0.0
        select_fails = 0
        # ⚠️ Run-level, NOT per-tribunal. Scoped to the tribunal it never reached the
        # limit: a throttle that costs two opens per court simply moved on to the next
        # one, degrading for hours without a single detector firing (2026-08-08).
        consec_fail = 0
        idx = a.start - 1
        while True:
            idx += 1
            if idx >= len(tl) or (a.end and idx > a.end):
                break
            tgt = tl[idx]
            done = st["tribunales"].get(tgt["v"])
            if done and done.get("complete") and not done.get("undercount"):
                # A tribunal is only finished when its census is complete AND every bank causa it
                # listed has a detail record. Otherwise re-search it and pick up the stragglers —
                # this is what makes a blocked run resumable without re-doing the whole country.
                missing = [c for c in done.get("causas", [])
                           if needs_visit(st, f"{tgt['v']}-{c['rol']}", not a.no_ebook)]
                if a.no_detail or not missing:
                    continue
                note(f"  [{idx}] {tgt['v']} re-search: {len(missing)} causa(s) lack detail")
            if not C.select_tribunal_kbd(p, tgt["v"]):
                note(f"  [{idx}] {tgt['v']} could not select — skip")
                select_fails += 1
                # ⚠️ NEVER let this end in a clean DONE. On 2026-08-08 a stale modal blocked every
                # select and the run "completed" having swept nothing, reporting the previous
                # run's totals as if they were this one's. A form we cannot drive is a hard stop.
                if select_fails >= SELECT_FAIL_LIMIT:
                    note(f"  *** {select_fails} tribunales in a row could not be selected — the "
                         f"form is not usable (stale modal? collapsed panel?).")
                    save()
                    tally_line("TALLY at form-loss:")
                    # ⚠️ THIS IS THE ONE FAILURE A REPLACEMENT BROWSER RELIABLY FIXES, so try that
                    # before handing the slot back. Until 2026-08-12 this returned 5 immediately
                    # and the only cure lived in the hourly supervisor — so a worker that wedged
                    # at 01:00 sat dead until 02:00, four times over on the day this was measured.
                    # Bounded by MAX_SWAPS: if new browsers keep wedging, the fault is not the
                    # browser and relaunching for ever would just hide it.
                    if swaps < MAX_SWAPS and fresh_browser():
                        select_fails = 0
                        idx -= 1                  # retry the tribunal we could not select
                        continue
                    note(f"  *** a replacement browser did not help either — stopping. "
                         f"resume with --start {idx}")
                    return 5
                continue
            select_fails = 0
            ojv.click_away(p)
            if last_search:
                gap = gap_for() - (time.time() - last_search)
                if gap > 0:
                    time.sleep(gap)

            net.clear()
            if boot_lock and boot_lock.held:
                boot_lock.touch()     # about to search: the stale clock restarts from here
            C.human_click(p, "#btnConConsultaFec")
            last_search = time.time()
            tally["searches"] += 1
            kind, el = ojv.wait_results(p, S, net)

            hit, why = ojv.blocked(p, net)
            # ⚠️ THE GATE OPENS HERE — one confirmed search, then the next worker may start
            # (operator, 2026-08-11). Reaching a form proves nothing: on 2026-08-10 all four
            # workers reached a page and not one of them could search, so releasing on the form
            # would have opened the gate four times over on the strength of nothing.
            # Released on ANY verdict, good or bad. A worker that cannot search must not hold
            # three others behind it all night, and if the site is refusing us the queue needs to
            # find that out rather than sit still.
            if boot_lock and boot_lock.held:
                ok = kind == "results" and not hit
                note(f"first search {'CONFIRMED' if ok else 'did NOT confirm'} "
                     f"({kind}{', blocked: ' + why if hit else ''}, {el:.0f}s) "
                     f"— releasing the entry lock, next worker may come in")
                boot_lock.release()
            if hit:
                note(f"  *** BLOCKED at idx {idx} ({tgt['v']} {tgt['t'][:28]}) {why}")
                save()
                tally_line("TALLY at block:")
                if recover(idx):
                    idx -= 1          # re-enter puts us back before this tribunal
                    continue
                return 3
            if kind in ("stale", "timeout"):
                note(f"  [{idx}/{len(tl)}] {tgt['v']:>5} {tgt['t'][:34]:36} {kind.upper()} "
                     f"after {el:.1f}s — never proved fresh, NOT recording")
                consec_fail += 1
                if consec_fail >= MODAL_FAIL_LIMIT:
                    note(f"  *** {consec_fail} unproductive actions in a row — silent throttle. "
                         f"Recovering.")
                    consec_fail = 0
                    if recover(idx):
                        idx -= 1
                    else:
                        return 3
                continue

            consec_fail = 0                      # a search that proved fresh clears it too
            total = C.total_registros(p) if kind == "results" else None
            ent = {"idx": idx, "name": tgt["t"], "kind": kind, "elapsed": round(el, 1),
                   "total": total, "pages": 0, "rows_seen": 0, "complete": False,
                   "banks": 0, "causas": []}
            st["tribunales"][tgt["v"]] = ent
            if kind != "results" or total is None:
                ent["complete"] = True
                note(f"  [{idx}/{len(tl)}] {tgt['v']:>5} {tgt['t'][:34]:36} {kind:7} {el:5.1f}s "
                     f"total={total}")
                save()
                continue

            # ---- walk the result pages, harvesting detail from each BEFORE advancing ----
            page, seen, stuck, blocked_here = 1, 0, False, False
            while True:
                # Read the table the way a person does. We parse the DOM directly, so without
                # this the session produces no wheel telemetry at all while "reading" 100+ rows.
                C.human_scroll(p)
                try:
                    rows = C.page_rows(p)
                except Exception as e:
                    note(f"    [warn] could not read the results table: {str(e)[:80]}")
                    blocked_here = True
                    break
                banks = [dict(r, page=page) for r in rows if r["has"]
                         and r["rol"].upper().startswith("C") and C.is_bank(r["car"])]
                seen += sum(1 for r in rows if r["rol"].strip())   # skip the blank filler row
                ent.update(pages=page, rows_seen=seen, banks=ent["banks"] + len(banks))
                ent["causas"] += [{"rol": c["rol"], "car": c["car"], "fecha": c["fecha"],
                                   "page": page} for c in banks]
                note(f"  [{idx}/{len(tl)}] {tgt['v']:>5} {tgt['t'][:34]:36} {kind:7} {el:5.1f}s "
                     f"total={total} page={page} rows={seen} banks+{len(banks)}")
                save()

                if not a.no_detail:
                    for c in banks:
                        if not needs_visit(st, f"{tgt['v']}-{c['rol']}", not a.no_ebook):
                            continue
                        if a.max_causas and tally["opens"] >= a.max_causas:
                            note(f"  --max-causas {a.max_causas} reached — stopping cleanly")
                            save()
                            tally_line("TALLY at cap:")
                            return 0
                        time.sleep(gap_for(CAUSA_GAP))
                        tally["opens"] += 1
                        try:
                            rec = harvest_causa(ctx, p, tgt["v"], tgt["t"], c,
                                                want_ebook=not a.no_ebook,
                                                only_proc=a.only_proc)
                        except Exception as e:
                            note(f"    [warn] harvest threw: {str(e)[:90]}")
                            rec = None
                        hit, why = ojv.blocked(p, net)
                        if hit:
                            note(f"  *** BLOCKED on detail, idx {idx} causa {c['rol']} — {why}")
                            save()
                            tally_line("TALLY at block:")
                            blocked_here = True
                            break
                        # A document refused at the network layer is a refusal even though no
                        # rejection page exists. Count it, or the run keeps buying causa opens it
                        # can no longer use.
                        if rec is not None and (rec.get("ebook") or {}).get("refused"):
                            consec_fail += 1
                            note(f"      [!] document refused ({consec_fail}/"
                                 f"{MODAL_FAIL_LIMIT}) — session may be going")
                            if consec_fail >= MODAL_FAIL_LIMIT:
                                note("  *** documents being refused with no rejection page — "
                                     "treating as a block")
                                st["causas"][rec["causa_id"]] = rec
                                save()
                                blocked_here = True
                                break
                        if rec is None:
                            # Not a block by the usual tells (just checked). A stuck modal
                            # poisons every LATER open, so clear it — one hiccup used to look
                            # exactly like a burned profile for the rest of the run.
                            C.clear_stuck_modal(p)
                            consec_fail += 1
                            if consec_fail >= MODAL_FAIL_LIMIT:
                                note(f"  *** {consec_fail} causa opens in a row failed with no "
                                     f"rejection page — that is the SILENT THROTTLE. Recovering.")
                                blocked_here = True
                                break
                            continue
                        consec_fail = 0          # a real harvest clears the throttle counter
                        st["causas"][rec["causa_id"]] = rec
                        # A long clean stretch means the session genuinely recovered, so the
                        # budget must reset. Counting blocks for the LIFE of the run would strand
                        # a 250-causa sweep after six, however many hours of clean work sat
                        # between them.
                        clean_since_block += 1
                        if clean_since_block >= CLEAN_STREAK and recoveries:
                            note(f"      {clean_since_block} clean opens since the last block "
                                 f"— recovery budget reset")
                            recoveries = 0
                        if rec["ebook"].get("bytes"):
                            tally["ebooks"] += 1
                            tally["bytes"] += rec["ebook"]["bytes"]
                        elif rec["ebook"].get("apm_challenge"):
                            tally["apm"] += 1
                        save()
                        tally_line("      running:")
                        time.sleep(gap_for(POST_CAUSA))

                if blocked_here:
                    break
                # A page advance draws on the same budget as a search — see SEARCH_GAP.
                gap = gap_for() - (time.time() - last_search)
                if gap > 0:
                    time.sleep(gap)
                try:
                    why = advance(p, page)
                    last_search = time.time()
                except Exception as e:
                    # A 10-hour sweep must not die on one unexpected exception. Treat it the way
                    # we treat a block: save, re-enter, retry the tribunal.
                    note(f"    [warn] paginator threw: {str(e)[:90]} — treating as a block")
                    blocked_here = True
                    break
                if why != "more":
                    stuck = why == "stuck"
                    break
                page += 1
                tally["pages"] += 1

            if blocked_here:
                # The tribunal is half-done; leave it incomplete so the resume logic re-searches
                # it and picks up whichever causas never got their detail.
                ent["complete"] = False
                save()
                if recover(idx):
                    idx -= 1
                    continue
                return 3
            ent["complete"] = not stuck
            ent["undercount"] = total is not None and seen < total
            save()
            if stuck or ent["undercount"]:
                note(f"    [!] {tgt['t'][:40]} INCOMPLETE — {seen}/{total} rows over {page} pages")

        res = [v for v in st["tribunales"].values() if v["kind"] == "results"]
        emp = [v for v in st["tribunales"].values() if v["kind"] == "empty"]
        note(f"DONE. tribunales={len(st['tribunales'])} withResults={len(res)} empty={len(emp)} "
             f"causas_found={sum(v['banks'] for v in st['tribunales'].values())}")
        inc = [v["name"] for v in st["tribunales"].values() if not v.get("complete", True)]
        if inc:
            note(f"  INCOMPLETE (paginator stuck): {inc}")
        tally_line("TALLY final:")
        return 0


if __name__ == "__main__":
    sys.exit(main())
