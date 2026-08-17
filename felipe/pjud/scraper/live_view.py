"""LIVE VIEW — watch what a worker is actually doing, while it is doing it.

⚠️ WHY THIS EXISTS. A cloud runner has no screen. Four sessions died at the same causa with
"modal did not open after 90s" and nobody could say what was on the page for those ninety
seconds — a spinner, a rejection interstitial, an overlay, an empty modal, or a perfectly normal
page missing one element. `--shots` answered that AFTERWARDS, out of an artifact you can only
download once the job has ended. The operator asked for the other half: "set up the runner in a
way I get to see what it's doing" — i.e. WHILE it runs, so a wrong turn can be caught in the
minute it happens instead of the hour after.

THE TRANSPORT IS NEON, because it is the only thing the runner and the operator's PC already
share. One row per worker slot, overwritten in place:

    runner ──(jpeg + log tail every few seconds)──▶ live_view table ◀──(poll)── watch_live.py

⚠️ ONE ROW PER SLOT, NOT A FRAME LOG. A history table would grow without bound on a channel
nobody reads twice, and the failure history already has an owner (`--shots`, uploaded as an
artifact). The live view is a window, not a recorder.

⚠️ IT MUST NEVER BE ABLE TO BREAK A RUN — it is a convenience bolted onto the one process we
cannot reach by hand. Every path is wrapped: a screenshot timeout, a closed page, a dead database
connection all degrade to "no picture", never to a stopped sweep. After MAX_FAILS consecutive
errors it switches itself off for good and says so once.

⚠️ IT IS ALSO A VARIABLE. Screenshotting occupies the renderer's main thread for a few tens of
milliseconds, and we are currently hunting a wall that appears at exactly 10 causa opens on a
runner and never locally. Do NOT leave it on during a one-variable test unless the arm you are
comparing against also has it on. Nothing here touches the network toward PJUD — CDP screenshots
are local — but "no requests" is not the same as "no difference".

Cost control, because both ends pay for the bytes:
  * a frame is published only if it CHANGED (md5 of the jpeg). A page sitting still through a
    25 s pacing wait costs one frame, not five.
  * the viewer sends the sequence number it already holds, and gets `same` back instead of the
    picture.
"""

import base64
import hashlib
import os
import socket
import time

HERE_SLOT = None

MAX_FAILS = 5          # consecutive errors after which the live view turns itself off for good


class Live:
    """Publishes what one worker sees. Fails open, always."""

    DDL = """CREATE TABLE IF NOT EXISTS live_view (
                 slot     TEXT PRIMARY KEY,
                 run_id   TEXT,
                 host     TEXT,
                 ip       TEXT,
                 seq      INTEGER     DEFAULT 0,
                 phase    TEXT        DEFAULT '',
                 tail     TEXT        DEFAULT '',
                 url      TEXT        DEFAULT '',
                 frame    TEXT        DEFAULT '',
                 started  TIMESTAMPTZ DEFAULT now(),
                 ts       TIMESTAMPTZ DEFAULT now())"""

    def __init__(self, slot, every=6.0, quality=45, label=""):
        self.slot = str(slot)
        self.every = float(every)
        self.quality = int(quality)
        self.label = label
        self.seq = 0
        self.last = 0.0
        self.last_hash = ""
        # An explicit caption from say(), and the log line that was current when it was set.
        # ⚠️ WITHOUT THE SECOND FIELD THE CAPTION LIVES FOR ONE TICK: tick() derives the phase
        # from the log tail, so "BLOCKED on 2-C-1251-2026" was overwritten by the next routine
        # line a couple of seconds later — i.e. the captions were invisible exactly when they
        # mattered. It now stands until the worker itself says something newer.
        self.caption = ""
        self.caption_at = ""
        self.fails = 0
        self.dead = False
        self.frames = 0
        self.conn = None
        self.ip = os.environ.get("RUNNER_IP", "")
        self.run_id = str(os.environ.get("GITHUB_RUN_ID", "local"))
        try:
            self.host = socket.gethostname()
        except Exception:
            self.host = "?"
        try:
            import psycopg2
            import dbstore
            self.conn = psycopg2.connect(**dbstore._conn_kwargs())
            self.conn.autocommit = True
            with self.conn.cursor() as c:
                c.execute(self.DDL)
                # A previous run's picture in this slot is a lie the moment we start, and the
                # viewer shows the age of what it holds — so clear it rather than leaving a stale
                # frame that looks live until you read the timestamp.
                c.execute("INSERT INTO live_view (slot, run_id, host, ip, started, ts) "
                          "VALUES (%s,%s,%s,%s, now(), now()) ON CONFLICT (slot) DO UPDATE SET "
                          "run_id=EXCLUDED.run_id, host=EXCLUDED.host, ip=EXCLUDED.ip, "
                          "seq=0, frame='', phase='', tail='', started=now(), ts=now()",
                          (self.slot, self.run_id, self.host, self.ip))
            _note(f"live view ON - slot {self.slot}, a frame every {self.every:.0f}s when the "
                  f"page changes. Watch it with:  python watch_live.py")
        except Exception as e:
            _note(f"live view unavailable ({str(e)[:70]}) - running blind, which is only a "
                  f"convenience lost")
            self.conn = None
            self.dead = True

    # ── capture ─────────────────────────────────────────────────────────────
    def tick(self, page, force=False):
        """Publish a frame if enough time has passed and the page looks different.

        Called from the pacing waits (cdp_scrape.IDLE_HOOK) and from inside the modal wait loop,
        which is exactly where the interesting failures live: the worker is either acting or
        waiting, and the waits are where a hang happens.
        """
        if self.dead or page is None:
            return
        now = time.time()
        if not force and now - self.last < self.every:
            return
        self.last = now
        try:
            # ⚠️ AN EXPLICIT, SHORT TIMEOUT. Playwright's default screenshot timeout is 30 s, and
            # a page busy enough to need 30 s is precisely the page we would be watching — so the
            # default would stall the worker for half a minute at the worst possible moment.
            png = page.screenshot(type="jpeg", quality=self.quality,
                                  full_page=False, timeout=5000)
            h = hashlib.md5(png).hexdigest()
            url = ""
            try:
                url = page.url
            except Exception:
                pass
            tail = _tail()
            last = tail.rsplit("\n", 1)[-1] if tail else ""
            if self.caption and last != self.caption_at:
                self.caption = ""
            phase = (self.caption or last)[:200]
            if h == self.last_hash and not force:
                # The picture is identical — refresh the heartbeat only, so the viewer can still
                # tell "nothing is moving" from "the worker is dead", which are different things
                # and were indistinguishable when a stale frame was all you had.
                self._exec("UPDATE live_view SET ts=now(), phase=%s, tail=%s, url=%s "
                           "WHERE slot=%s", (phase, tail, url, self.slot))
                return
            self.last_hash = h
            self.seq += 1
            self.frames += 1
            self._exec("UPDATE live_view SET seq=%s, frame=%s, phase=%s, tail=%s, url=%s, "
                       "ip=%s, ts=now() WHERE slot=%s",
                       (self.seq, base64.b64encode(png).decode("ascii"),
                        phase, tail, url, self.ip, self.slot))
            self.fails = 0
        except Exception as e:
            self.fails += 1
            if self.fails >= MAX_FAILS:
                self.dead = True
                _note(f"live view OFF after {MAX_FAILS} consecutive errors "
                      f"(last: {str(e)[:60]}) - the run is unaffected")

    def say(self, page, phase):
        """Force a frame with a caption — used at the moments worth seeing, whatever the clock
        says: a causa opening, a block, an entry, the end of a run."""
        if self.dead:
            return
        t = _tail()
        self.caption = str(phase)[:200]
        self.caption_at = t.rsplit("\n", 1)[-1] if t else ""
        self.tick(page, force=True)

    def public_ip_once(self):
        """Fill in the address the world sees, once, so the viewer can tell WHICH runner this is.
        Deliberately lazy and best-effort: it is one external request and a live view is never
        worth delaying a walk-in for."""
        if self.ip or self.dead:
            return
        try:
            import ojv
            self.ip = ojv.public_ip() or ""
        except Exception:
            self.ip = ""

    def close(self, verdict=""):
        if self.conn is None:
            return
        try:
            self._exec("UPDATE live_view SET phase=%s, ts=now() WHERE slot=%s",
                       (f"[ended] {verdict}"[:200], self.slot))
            self.conn.close()
        except Exception:
            pass

    # ── plumbing ────────────────────────────────────────────────────────────
    def _exec(self, sql, params):
        try:
            with self.conn.cursor() as c:
                c.execute(sql, params)
        except Exception:
            # One reconnect, then let the caller's failure counter do its work. A worker that
            # runs for five hours will outlive an idle Neon connection at least once.
            import psycopg2
            import dbstore
            self.conn = psycopg2.connect(**dbstore._conn_kwargs())
            self.conn.autocommit = True
            with self.conn.cursor() as c:
                c.execute(sql, params)


def _tail():
    """The worker's own last log lines. ojv.note() keeps them; nothing new is instrumented, and
    the log narration IS the phase description — 'open 10-C-1638-2026', '[42] 2do Juzgado ...' —
    so no separate phase plumbing has to be threaded through the sweep."""
    try:
        import ojv
        return "\n".join(ojv.TAIL)[-4000:]
    except Exception:
        return ""


def _note(m):
    try:
        import ojv
        ojv.note(m)
    except Exception:
        print(m, flush=True)


def read_all(conn=None, have=None):
    """Viewer side: every slot's latest state. `have` maps slot -> seq already held, and those
    frames are returned as None so a still page costs nothing to watch."""
    import psycopg2.extras
    close = False
    if conn is None:
        import psycopg2
        import dbstore
        conn = psycopg2.connect(**dbstore._conn_kwargs())
        conn.autocommit = True
        close = True
    have = have or {}
    out = []
    try:
        # ⚠️ TWO QUERIES ON PURPOSE — the metadata first, the picture only for the slots whose
        # seq actually moved. Selecting `frame` and discarding it in Python would pull ~80 KB per
        # slot per poll out of Neon for a page that is standing still, which is the exact cost
        # this whole design is built to avoid.
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute("SELECT slot, run_id, host, ip, seq, phase, tail, url, "
                      "  EXTRACT(EPOCH FROM (now()-ts))      AS age, "
                      "  EXTRACT(EPOCH FROM (now()-started)) AS uptime "
                      "FROM live_view ORDER BY slot")
            out = [dict(r) for r in c.fetchall()]
        want = [r["slot"] for r in out
                if str(have.get(str(r["slot"]), "")) != str(r["seq"])]
        frames = {}
        if want:
            with conn.cursor() as c:
                c.execute("SELECT slot, frame FROM live_view WHERE slot = ANY(%s)", (want,))
                frames = {s: f for s, f in c.fetchall()}
        for r in out:
            r["frame"] = frames.get(r["slot"]) or None
            r["age"] = round(float(r["age"] or 0), 1)
            r["uptime"] = round(float(r["uptime"] or 0), 1)
    finally:
        if close:
            conn.close()
    return out
