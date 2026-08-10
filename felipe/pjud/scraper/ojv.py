"""Shared OJV machinery: walk in, run a search, prove the results are fresh, spot a block.

Extracted from census.py 2026-08-07 so every worker uses ONE copy. Duplication is not a style
issue here — it is the documented failure mode: `waf_check` and `cdp_scrape` each carried their
own English-only rejection matcher, so when the site started answering in Spanish BOTH went blind
at once and a sweep ran for an hour reporting health while every search was being refused. One
copy, fixed once.

Callers tune the timing knobs by assigning to the module attributes (they are read at call time):

    import ojv
    ojv.EMPTY_MIN_S = 30.0
"""
import time, re, socket, random
import cdp_scrape as C
import unattended_worker as uw

# ── timing (operator's rule 2026-08-06: err on the side of waiting) ───────────
# The request RATE is unaffected by these: the inter-search gap is measured from the search
# click, so detecting an empty faster only shortens idle time, never spacing. What waiting longer
# actually buys is protection against the silent failure that matters — calling a slow-but-live
# tribunal "empty" and recording a court as having no causas when it has some. Nothing downstream
# would ever flag that. Live tribunales settled in 5.5-16.9 s on 2026-08-06, so a 25 s floor sits
# comfortably clear of the observed range.
EMPTY_MIN_S = 25.0      # never call a search empty before this many seconds
EMPTY_QUIET = 10000     # ms of DOM silence required
HARD_CAP = 75.0         # give up... unless the site's own spinner says it is still working
# How long the site's loading sheet may sit there with NOTHING in flight before we call it
# orphaned and remove it. Short: a real request that is still running keeps S.inflight non-zero,
# so this timer only ever counts an overlay that has been abandoned.
STUCK_OVERLAY_S = 25.0

SHAPE_RE = re.compile(r"/[0-9a-f]{24,40}(\?|$)")


def note(m):
    s = time.strftime("%H:%M:%S")
    try:
        print(f"[{s}] {m}", flush=True)
    except UnicodeEncodeError:
        # A single un-encodable character in a log line once killed an entire sweep.
        print(f"[{s}] {m.encode('ascii', 'replace').decode('ascii')}", flush=True)


# ── network tap ──────────────────────────────────────────────────────────────

def make_tap(net):
    """Response handler appending {u, n, rej} to `net`. Bilingual rejection detection —
    the site answers Spanish ("Su numero de soporte es") to this browser, and matching only the
    English text is what blinded every detector on 2026-08-05."""
    def on_resp(r):
        try:
            if "pjud.cl" not in r.url or r.request.resource_type in (
                    "image", "stylesheet", "font", "media"):
                return
        except Exception:
            return
        n, rej = None, False
        try:
            body = r.body()
            n = len(body)
            low = body.lower()
            rej = (b"numero de soporte" in low or b"n\xc3\xbamero de soporte" in low
                   or b"requested url was rejected" in low or b"support id" in low)
        except Exception:
            pass
        net.append({"u": r.url.split("/")[-1].split("?")[0], "n": n, "rej": rej})
    return on_resp


# ── connectivity ─────────────────────────────────────────────────────────────

def internet_up(timeout=4.0):
    """Is there general internet, independent of pjud.cl?

    ⚠️ Deliberately NOT a request to pjud.cl. The whole point is to tell an OUTAGE apart from a
    BLOCK, and asking the site that might be refusing us cannot distinguish those. These are
    neutral third parties: if none of them answer, the machine is offline.

    Checked with raw sockets rather than the browser, because the browser may itself be wedged —
    and because a page that fails to load offline looks exactly like a page the WAF is refusing.
    """
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53), ("www.google.com", 443)):
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return True
        except OSError:
            continue
    return False


def wait_for_internet(max_wait=14400, poll=20.0):
    """Block until connectivity returns. (came_back, seconds_waited).

    An outage must NEVER be charged to the block budget: it is not a rate verdict, no cool-off
    helps it, and rotating the profile over it would throw away a warm session for a problem that
    has nothing to do with the site. Callers use the elapsed time to decide whether the session
    is likely still alive on the other side.

    max_wait defaults to four hours — long enough to ride out a modem reset, an ISP blip or a
    switch between connections, and short enough that a machine left offline overnight stops
    rather than sits in a loop forever.
    """
    t0 = time.time()
    if internet_up():
        return True, 0.0
    note("*** NO INTERNET — pausing. This is NOT a block: no cool-off, no recovery spent.")
    while time.time() - t0 < max_wait:
        time.sleep(poll)
        if internet_up():
            el = time.time() - t0
            note(f"*** internet is back after {el / 60:.1f} min — resuming")
            return True, el
    note(f"*** still offline after {max_wait / 60:.0f} min — stopping")
    return False, time.time() - t0


def public_ip(timeout=6.0):
    """Our WAN address, or None. Neutral third parties only — never pjud.cl."""
    import urllib.request
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                ip = r.read().decode("utf-8", "replace").strip()
            if ip and len(ip) < 46:
                return ip
        except Exception:
            continue
    return None


def rej_frames(p):
    """How many frames currently show an F5 rejection. The rejection lives in an IFRAME with no
    modal classes, so a selector sweep of the main document misses it entirely (operator caught
    this: "the blocking pop up is still opened. check it")."""
    n = 0
    for fr in p.frames:
        try:
            t = fr.evaluate("()=>document.body?document.body.innerText:''") or ""
        except Exception:
            continue
        low = t.lower()
        # ⚠️ Match the ENGLISH forms too. The tier-3 CAPTCHA frame says "Your support ID is",
        # which neither "soporte" nor "requested url was rejected" catches — so on 2026-08-10 two
        # workers sat behind a full-page CAPTCHA while every detector reported health. Third time
        # this same shape has bitten: one wording, one language, one frame we were not reading.
        if ("soporte" in low or "requested url was rejected" in low
                or "support id" in low or "code is in the image" in low):
            n += 1
    return n


def captcha_frame(p):
    """True if a tier-3 image CAPTCHA is on screen, in ANY frame.

    ⚠️ It is served INSIDE A CHILD FRAME — 183 characters of it — so reading the main document's
    innerText, which is what walk_in used to do, sees nothing at all. This must be its own check
    rather than folded into blocked(): a CAPTCHA is not a rate verdict. Cooling off will not clear
    it, re-entry will not clear it, and rotating the profile only earns a fresh one. It needs a
    human, and the only correct response is to stop and say so.
    """
    for fr in p.frames:
        try:
            t = fr.evaluate("()=>document.body?document.body.innerText:''") or ""
        except Exception:
            continue
        if "code is in the image" in t.lower():
            return True
    return False


def hard_rejections(net):
    """Rejection RESPONSES, not merely small ones.

    The first version of this asked `size < 1000`, which stopped a perfectly healthy sweep — 63 KB
    of results, 59 registros, zero rejection frames — because one legitimate 0-byte response
    counted as a kill. Require the rejection TEXT and a body in the size band F5 actually uses.
    """
    return [r for r in net if r["rej"] and r["n"] is not None and 100 < r["n"] < 1000]


def blocked(p, net):
    """(is_blocked, reason). Checks structure and network, never a single heuristic."""
    rf = rej_frames(p)
    hard = hard_rejections(net)
    if rf or hard:
        return True, f"rejF={rf} hardRej={len(hard)}"
    try:
        if p.query_selector("iframe[id*='TSBrPFrame'], iframe[id*='cs_chlg']"):
            return True, "challenge iframe present"
    except Exception:
        pass
    # ⚠️ THE FOURTH TELL, and the one that cost two days. Buscar left `disabled` while the page is
    # NOT busy means the form will never fire another search: every click lands on a dead button,
    # no request goes out, and wait_results returns STALE for ever. There is no rejection page and
    # no challenge iframe, so every other check here says "healthy" — which is precisely how a
    # spent session ran all night producing nothing (2026-08-08/09). HANDOFF_CDP has called this
    # the instant block tell since July; we simply never asked.
    # Sampled twice: during a legitimate search the button is disabled AND page_busy is true, so
    # the guard is "disabled while idle", confirmed over a short dwell to avoid catching the
    # instant between the click and the spinner appearing.
    try:
        def dead():
            return bool(p.eval_on_selector("#btnConConsultaFec", "e=>!!e && e.disabled")) \
                and not C.page_busy(p)
        if dead():
            time.sleep(2.0)
            if dead():
                return True, "Buscar stuck disabled while idle (spent session)"
    except Exception:
        pass
    return False, ""


# ── pointer hygiene ──────────────────────────────────────────────────────────

def click_away(p):
    """Move the pointer to dead space and press nothing.

    Operator, 2026-08-06: "when the tribunals list got stuck on me, it loaded fine only after
    clicking on the background of the site... don't dismiss the blur theory yet. even if it's a
    fairytale, i'd rather 'waste' a few clicks, imitating what a human would do." Unproven, cheap,
    kept. press=False deliberately: a real CLICK on the background once dismissed things we
    needed, so this is a hover-and-settle, not a click.
    """
    try:
        pt = p.evaluate("""()=>{
          const bad = e => !e || ['A','BUTTON','INPUT','SELECT','TEXTAREA','LABEL','IMG','IFRAME','OPTION']
                                  .includes(e.tagName)
                          || e.getAttribute('onclick')
                          || e.closest('a,button,input,select,textarea,label,[onclick],.modal');
          for (let y=140; y<innerHeight-90; y+=35)
            for (let x=30; x<innerWidth-30; x+=55) {
              const el=document.elementFromPoint(x,y);
              if (el && !bad(el)) return {x:x,y:y};
            }
          return null; }""")
        if pt:
            C._human_pointer(p, pt["x"], pt["y"], press=False)
            p.wait_for_timeout(250)
    except Exception:
        pass


# ── entry ────────────────────────────────────────────────────────────────────

def find_form(ctx):
    """The page holding the search form, tolerating navigation.

    query_selector THROWS "Execution context was destroyed" while a page is navigating — which is
    exactly when we poll for the form after the entry click. Unguarded, that killed a whole run at
    the moment the click SUCCEEDED.
    """
    for q in list(ctx.pages):
        try:
            if q.query_selector("#fecCompetencia"):
                return q
        except Exception:
            pass
    return None


OJV_HOST = "oficinajudicialvirtual.pjud.cl"


def _reach_ojv(ctx, start, wait=60.0):
    """Click through from www.pjud.cl to the OJV, FOCUSING the tab it opens.

    ⚠️ THE TAB MUST BE BROUGHT TO THE FRONT. F5's challenge script checks
    document.visibilityState — we found that check by hand in the APM payload — so a tab opened
    in the BACKGROUND never runs it. The page then stays blank and its URL never even resolves,
    which the old helper read as "no OJV tab appeared". Three attempts in a row failed that way
    on a freshly changed IP (2026-08-09), and the whole worker exited, while a direct navigation
    with the tab focused cleared the same challenge in six seconds.

    So: click, take whatever tab appears, focus it, THEN wait for the entry button.
    """
    cands = start.eval_on_selector_all(
        "a", "els=>els.map(a=>({t:(a.textContent||'').trim().slice(0,60),"
             " h:a.getAttribute('href')||''}))")
    hits = [c for c in cands if OJV_HOST in (c["h"] or "").lower()]
    if not hits:
        note(f"    no <a href*='{OJV_HOST}'> on {start.url[:50]}")
        return None
    hits.sort(key=lambda c: 0 if "/home" in c["h"].lower() else 1)
    best = hits[0]
    note(f"    click -> {best['t'][:44]!r}")
    before = set(ctx.pages)
    C.human_click(start, start.locator(f"a[href='{best['h']}']").first)

    deadline = time.time() + wait
    focused = set()
    while time.time() < deadline:
        for q in [x for x in ctx.pages if x not in before]:
            if q not in focused:            # focus every new tab once, blank ones included:
                try:                        # a blank tab is precisely the un-run challenge
                    q.bring_to_front()
                    focused.add(q)
                except Exception:
                    pass
            try:
                if OJV_HOST in (q.url or "") and q.query_selector(
                        "[onclick*='accesoConsultaCausas'], [onclick*='accesoInvitado'], "
                        "#no-disponible"):
                    return q
            except Exception:
                pass
        start.wait_for_timeout(700)
    # Last resort: some builds navigate the SAME tab instead of opening one.
    try:
        if OJV_HOST in (start.url or ""):
            return start
    except Exception:
        pass
    return None


def walk_in(ctx):
    """www.pjud.cl -> OJV /home/ -> dismiss AVISO -> Consulta causas -> form. Fully scripted.

    Returns the form page, or None. None with a TIER-3 note means a human must clear an image
    CAPTCHA; None otherwise means the entry did not take and the run should stop rather than
    hammer the gate.
    """
    p = find_form(ctx)
    if p:
        return p
    # ★ Close stale OJV tabs FIRST. Each failed walk-in used to leave another /home/ behind, and
    # human_click drives REAL MOUSE COORDINATES — which land on whatever tab is actually visible.
    # With two /home/ tabs open, retries clicked those coordinates on the WRONG tab, so three
    # "attempts" could fail without the button ever being touched (operator: "you have 2 homes
    # opened. what's wrong"). That also undermines the "gate 1 refuses us" reading: the clicks may
    # simply never have arrived.
    for q in list(ctx.pages):
        if "oficinajudicialvirtual" in (q.url or ""):
            try:
                q.close()
            except Exception:
                pass
    time.sleep(1.5)
    start = next((q for q in ctx.pages if "pjud.cl" in (q.url or "")), None) or ctx.new_page()
    try:
        start.goto("https://www.pjud.cl/", wait_until="domcontentloaded")
    except Exception:
        pass
    start.bring_to_front()
    start.wait_for_timeout(4000)
    page = None
    for attempt in (1, 2, 3):
        page = _reach_ojv(ctx, start, wait=60.0)
        if page is not None:
            break
        note(f"could not reach the OJV (attempt {attempt}/3)")
        if not internet_up():
            if not wait_for_internet()[0]:
                return None
        time.sleep(8)
        try:
            start.goto("https://www.pjud.cl/", wait_until="domcontentloaded")
            start.wait_for_timeout(4000)
        except Exception:
            pass
    if page is None:
        # FALLBACK: go straight there. The click-through from www.pjud.cl is preferred because it
        # is what a person does, but on 2026-08-09 it stopped producing a usable tab on a changed
        # IP — three attempts, every one blank — while a direct navigation in a focused tab
        # cleared F5's challenge in six seconds. Typing a public URL is ordinary browsing; a
        # preference for the prettier path is not worth losing the run over.
        note("click-through failed 3x — navigating to the OJV directly")
        try:
            page = next((q for q in ctx.pages if OJV_HOST in (q.url or "")), None) or ctx.new_page()
            page.bring_to_front()
            page.goto(f"https://{OJV_HOST}/home/", wait_until="domcontentloaded", timeout=60000)
            for _ in range(20):                   # the challenge needs the tab VISIBLE to run
                page.wait_for_timeout(3000)
                if page.query_selector("[onclick*='accesoConsultaCausas'], "
                                       "[onclick*='accesoInvitado'], #no-disponible"):
                    note("  direct navigation reached the OJV")
                    break
            else:
                note("could not reach the OJV directly either")
                return None
        except Exception as e:
            note(f"direct navigation failed: {str(e)[:70]}")
            return None
    page.bring_to_front()
    page.wait_for_timeout(4000)
    try:
        body = page.evaluate("()=>document.body?document.body.innerText.slice(0,300):''") or ""
    except Exception:
        body = ""
    if "code is in the image" in body.lower() or captcha_frame(page):
        note("*** TIER-3 IMAGE CAPTCHA — needs the operator. Not attempting to bypass. ***")
        return None
    _dismiss_aviso(page)
    # GATE 1 IS FLAKY, NOT REFUSING. Every fresh profile on 2026-08-06 failed its first entry
    # click and succeeded on a retry seconds later with nothing changed. Treating one timeout as a
    # verdict produced several wrong "needs a human / reCAPTCHA refused" conclusions.
    for attempt in range(1, 4):
        sel = next((s for s in ("[onclick*='accesoConsultaCausas']",
                                "[onclick*='accesoInvitado']") if page.query_selector(s)), None)
        if sel is None:
            # Do NOT give up: /home/ may simply not have finished rendering. Breaking here once
            # reported "no guest-entry button" for a button that appeared moments later.
            note(f"  guest-entry button not present yet (attempt {attempt}/3) — waiting")
            page.wait_for_timeout(8000)
            continue
        # ★ THE BUG THAT FAKED EVERY "GATE-1 REFUSED": /home/ has TWO accesoConsultaCausas
        # buttons. Playwright locators are strict, so passing the SELECTOR to human_click makes
        # bounding_box() throw ("resolved to 2 elements"); human_click catches it, falls through
        # to .click() which throws identically, and returns False. No click is ever delivered —
        # and the caller reports a gate-1 refusal for a click that never happened. Pick ONE
        # element, and one that actually hit-tests.
        page.bring_to_front()          # real mouse coords hit the VISIBLE tab, not this object
        page.wait_for_timeout(800)
        C.human_scroll(page, notches=2)   # a person looks around /home/ before clicking
        # ⚠️ ...and then scrolls BACK to what they want to click. Without this the scroll I added
        # on 2026-08-10 pushed the entry button below the fold, elementFromPoint returned null for
        # a point outside the viewport, and the coverage test read that as "covered" — refusing to
        # click a button that was merely off-screen. A hit-test is only meaningful on something
        # actually in view.
        try:
            page.eval_on_selector(sel, "e=>e.scrollIntoView({block:'center'})")
            page.wait_for_timeout(random.uniform(250, 600))
        except Exception:
            pass
        cov = page.evaluate("""(s)=>{
          return [...document.querySelectorAll(s)]
            .map((e,i)=>({e:e,r:e.getBoundingClientRect(),i:i}))
            .filter(o=>o.r.width>0&&o.r.height>0)
            .map(o=>{const t=document.elementFromPoint(o.r.x+o.r.width/2,o.r.y+o.r.height/2);
                     return {i:o.i, hit: !!t && (t===o.e||o.e.contains(t))};});
        }""", sel)
        pick = next((c["i"] for c in cov if c["hit"]), None)
        if pick is None:
            note(f"  entry button covered ({cov}) — not clicking")
            page.wait_for_timeout(5000)
            continue
        note(f"human_click guest entry {sel} nth({pick}) (attempt {attempt}/3)")
        ok = C.human_click(page, page.locator(sel).nth(pick), timeout=8000)
        note(f"  click delivered: {ok}")
        for _ in range(90):                      # 45 s per attempt
            page.wait_for_timeout(500)
            fp = find_form(ctx)
            if fp:
                note(f"  entered on attempt {attempt}")
                return fp
        _dismiss_aviso(page)   # it "comes and goes" — it can appear BETWEEN attempts
        note(f"  no form after attempt {attempt}; pausing before retry")
        page.wait_for_timeout(20000)
    return find_form(ctx)


def _dismiss_aviso(page):
    """The #no-disponible AVISO. Operator: "it comes and goes. dont conclude just because you
    dont see it now" — so always check, never assume. This overlay covering the entry button is
    what the whole "warm-up ritual" folklore turned out to be."""
    try:
        vis = ("()=>{const m=document.getElementById('no-disponible');"
               "return !!m && getComputedStyle(m).display!=='none';}")
        if not page.evaluate(vis):
            return
        note("dismissing #no-disponible AVISO")
        C.human_click(page, page.locator("#no-disponible button[data-dismiss='modal']").first,
                      timeout=6000)
        for _ in range(40):
            page.wait_for_timeout(300)
            if not page.evaluate(vis):
                return
    except Exception:
        pass


# ── search ───────────────────────────────────────────────────────────────────

def results_sig(p):
    """Fingerprint of what the results area currently shows. Advisory only — see wait_results."""
    try:
        return p.evaluate("""()=>{
          const t=document.querySelector('.loadTotalFec');
          const tot=t?t.innerText.replace(/\\s+/g,' ').trim():'';
          const rows=[...document.querySelectorAll('#dtaTableDetalleFecha tbody tr')];
          const head=rows.slice(0,3)
              .map(r=>r.innerText.replace(/\\s+/g,' ').trim().slice(0,70)).join('|');
          return tot+'##'+rows.length+'##'+head;
        }""") or ""
    except Exception:
        return ""


def wait_results(p, S, net):
    """('results'|'empty'|'stale'|'timeout', elapsed_s) — freshness is PROVEN, not assumed.

    ⚠️ Two earlier versions of this were wrong in ways nothing downstream could catch:

    1. "Does .loadTotalFec contain 'Total de registros'?" is TRUE from the PREVIOUS search — the
       site leaves old results on screen while the new one runs. It returned at 0.0 s every time
       and recorded each tribunal with the PREVIOUS tribunal's totals: 35 entries, zero empties,
       phantom "ex" courts credited with bank causas.
    2. The DOM-fingerprint fix could not tell empty->empty apart: an empty search clears the
       table, so two empties in a row leave it identical and "changed" never becomes true. That
       burned the full hard cap and would have dropped the second of every consecutive-empty pair
       — silent gaps in exactly the phantom-heavy regions where empties cluster.

    So the ground truth is the NETWORK: a consultaFechaCivil.php response arriving after the
    click proves the search ran. `net` must be cleared immediately before the click.
    """
    t0 = time.time()
    S.arm_observer()
    busy_since = None
    while True:
        el = time.time() - t0
        got_resp = [r for r in net if "consultaFechaCivil" in r["u"] and r["n"] is not None]
        busy = C.page_busy(p)
        # ⚠️ A STUCK overlay is not a busy page. page_busy now counts the site's
        # .jquery-loading-modal sheet (it must — while that is up every click is refused), but a
        # sheet that never goes away then pins page_busy True and we burn the whole 3x hard cap,
        # 225 s per tribunal, before calling a perfectly good court STALE. That is what happened
        # overnight on 2026-08-09: six recoveries spent on nothing but this. If the overlay is up
        # while NOTHING is in flight, it is orphaned — clear it and carry on.
        if busy and S.inflight == 0:
            busy_since = busy_since or time.time()
            if time.time() - busy_since > STUCK_OVERLAY_S:
                C.clear_stuck_modal(p)                 # the .jquery-loading-modal sheet
                got = C.clear_stuck_spinner(p)         # and the site's own #loadPre* spinner
                if got:
                    note(f"      [fix] cleared abandoned spinner {got} after "
                         f"{STUCK_OVERLAY_S:.0f}s idle")
                busy_since = None
                busy = C.page_busy(p)
        else:
            busy_since = None
        idle = (not busy) and S.inflight == 0 and S.dom_quiet_ms() >= EMPTY_QUIET
        if got_resp and idle and el >= 2.0:
            if "total de registros" in results_sig(p).lower():
                return "results", el
            if el >= EMPTY_MIN_S:              # operator's rule: never rush an "empty"
                return "empty", el
        if el >= HARD_CAP:
            # ★ Do NOT give up while the SITE says it is still working. 2026-08-06: two
            # consecutive STALEs looked like a block, but the probe showed zero rejection frames,
            # Buscar disabled-because-searching, and page_busy TRUE — a request genuinely in
            # flight. The site had simply slowed from 11-35 s to over 75 s, and we were throwing
            # away valid slow searches (including Los Angeles, 11 causas).
            if busy and el < HARD_CAP * 3:
                p.wait_for_timeout(500)
                continue
            return ("stale" if not got_resp else "timeout"), el
        p.wait_for_timeout(250)
