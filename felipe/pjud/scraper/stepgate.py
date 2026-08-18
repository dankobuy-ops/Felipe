"""STEP GATE — a runner that stops before every action and waits to be told to go.

    runner:    st = stepgate.Stepper("32096555236-s1"); st.ask(page, "guest-entry")
    operator:  python step_console.py --watch

⚠️ WHY THIS EXISTS. On 2026-08-18 both August runners died the same way: `click delivered: True`,
then forty-five silent seconds, then an F5 rejection page. The log could not say whether the block
arrived one second after the click or forty, because nothing looked at the page in between. A
failure screenshot tells you where a run ENDED and nothing about how it got there, and the
interesting frame is never the last one.

⚠️ THE CONTROL CHANNEL IS NEON, and it has to be. A GitHub runner has no inbound network, no
screen, and no shell we can reach; its artifacts do not upload until the job is over. The one
thing it already talks to mid-run is the database — `PgEntryLock` proved that channel works from a
datacenter — so the runner PUBLISHES the frame it is looking at and POLLS for a verdict. Same
mechanism, opposite direction.

⚠️ AND IT KEEPS MOVING WHILE IT WAITS. A browser frozen stone dead for five minutes — no pointer,
no idle motion, nothing — is a longer, louder empty telemetry channel than anything this project
has fixed so far. `idle` is called between polls precisely so a paused session looks like a person
reading, which is what it is. Do not replace it with time.sleep().

⚠️ FAILS OPEN ON A DEAD DATABASE, like every other gate here. A diagnostic that can strand a run
over an unrelated Neon hiccup is worse than no diagnostic.

Verdicts: `go` (this one action), `run` (stop asking, finish the run unattended), `abort` (stop).
There is deliberately no `skip`: a context manager cannot decline to run its own body without
tricks, and a half-performed action is a worse thing to reason about than a stopped run.
"""
import json
import os
import time

TABLE = "step_gate"
DDL = f"""CREATE TABLE IF NOT EXISTS {TABLE} (
             id BIGSERIAL PRIMARY KEY,
             run_id TEXT NOT NULL,
             n INTEGER NOT NULL,
             tag TEXT,
             phase TEXT,
             state TEXT,
             img TEXT,
             meta TEXT,
             asked_at TIMESTAMPTZ DEFAULT now(),
             answered_at TIMESTAMPTZ)"""


class Aborted(Exception):
    """The operator said stop. Not an error — a decision."""


def connect():
    """An autocommit connection with the table in place, or None. Never raises."""
    try:
        import psycopg2

        import dbstore
        conn = psycopg2.connect(**dbstore._conn_kwargs())
        conn.autocommit = True
        with conn.cursor() as c:
            c.execute(DDL)
            c.execute(f"CREATE INDEX IF NOT EXISTS {TABLE}_wait "
                      f"ON {TABLE} (state, asked_at DESC)")
        return conn
    except Exception:
        return None


def _state(page):
    """The page's own account of itself — the same fields the trace records."""
    try:
        return page.evaluate(
            "()=>({url:location.href, title:document.title,"
            " sx:Math.round(scrollX), sy:Math.round(scrollY),"
            " vw:innerWidth, vh:innerHeight,"
            " text:(document.body?document.body.innerText:'').slice(0,400),"
            " frames:[...document.querySelectorAll('iframe')].map(f=>f.id||f.name||''),"
            " modals:[...document.querySelectorAll('.modal.show,.modal.in')].map(m=>m.id),"
            " sheets:document.querySelectorAll('.modal-backdrop,.jquery-loading-modal').length})")
    except Exception as e:
        return {"url": "?", "error": str(e)[:80]}


def _jpeg_b64(page, quality=50):
    import base64
    try:
        return base64.b64encode(
            page.screenshot(full_page=False, timeout=6000, type="jpeg",
                            quality=quality)).decode("ascii")
    except Exception:
        return ""


class Stepper:
    """Runner side. `ask` blocks until the operator answers; `report` just posts a frame."""

    def __init__(self, run_id=None, timeout=900.0, on_timeout="abort", idle=None):
        self.run_id = str(run_id or os.environ.get("GITHUB_RUN_ID") or f"local-{os.getpid()}")
        self.timeout = float(timeout)
        # ⚠️ THE DEFAULT ON SILENCE IS TO STOP. "Wait for our instruction" means a runner nobody
        # is watching should not quietly carry on for 45 minutes on its own; a stopped run costs
        # two minutes of runner time, an unwatched one costs the whole point of the exercise.
        self.on_timeout = on_timeout if on_timeout in ("go", "abort") else "abort"
        self.idle = idle                # callable(page, secs) — a hand on the page while paused
        self.n = 0
        self.released = False                # operator said `run`: stop asking
        self.conn = connect()
        if self.conn is None:
            print("      [step] no control channel (db unreachable) — running unattended")

    # ── runner side ────────────────────────────────────────────────────────────────────────
    def _post(self, page, tag, phase, state, extra=None):
        if self.conn is None:
            return None
        st = _state(page)
        if extra:
            st["extra"] = extra
        try:
            with self.conn.cursor() as c:
                c.execute(f"INSERT INTO {TABLE} (run_id, n, tag, phase, state, img, meta) "
                          f"VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                          (self.run_id, self.n, tag, phase, state,
                           _jpeg_b64(page), json.dumps(st, ensure_ascii=False)))
                return c.fetchone()[0]
        except Exception as e:
            print(f"      [warn] step post: {str(e)[:60]}")
            return None

    def report(self, page, tag, extra=None):
        """Post what an action DID. No waiting — the operator sees it before the next question."""
        if self.conn is None or self.released:
            return
        self._post(page, tag, "after", "done", extra)

    def ask(self, page, tag, extra=None):
        """Post the frame we are about to act on, then wait for a verdict. Returns True to go."""
        if self.conn is None or self.released:
            return True
        self.n += 1
        rid = self._post(page, tag, "before", "waiting", extra)
        if rid is None:
            return True
        print(f"      [step {self.n}] waiting for instruction: {tag}")
        t0 = time.time()
        while time.time() - t0 < self.timeout:
            # ⚠️ Idle FIRST, then poll — so the very first thing a paused session does is move
            # like a person, not sit still waiting for a database round-trip.
            if self.idle:
                try:
                    self.idle(page, 2.0)
                except Exception:
                    time.sleep(2.0)
            else:
                time.sleep(2.0)
            try:
                with self.conn.cursor() as c:
                    c.execute(f"SELECT state FROM {TABLE} WHERE id=%s", (rid,))
                    row = c.fetchone()
            except Exception:
                continue
            v = (row[0] if row else "waiting") or "waiting"
            if v == "waiting":
                continue
            print(f"      [step {self.n}] -> {v}  ({time.time() - t0:.0f}s)")
            if v == "abort":
                raise Aborted(f"operator aborted at step {self.n} ({tag})")
            if v == "run":
                self.released = True
            return True
        print(f"      [step {self.n}] no instruction in {self.timeout:.0f}s "
              f"-> {self.on_timeout}")
        try:
            with self.conn.cursor() as c:
                c.execute(f"UPDATE {TABLE} SET state=%s, answered_at=now() WHERE id=%s",
                          (self.on_timeout + "-timeout", rid))
        except Exception:
            pass
        if self.on_timeout == "abort":
            raise Aborted(f"no instruction for step {self.n} ({tag}) in {self.timeout:.0f}s")
        return True

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass


# ── operator side ──────────────────────────────────────────────────────────────────────────
def waiting(conn, limit=5):
    """Rows a runner is currently blocked on, newest first."""
    with conn.cursor() as c:
        c.execute(f"SELECT id, run_id, n, tag, meta, asked_at FROM {TABLE} "
                  f"WHERE state='waiting' ORDER BY asked_at DESC LIMIT %s", (limit,))
        return [dict(zip(("id", "run_id", "n", "tag", "meta", "asked_at"), r))
                for r in c.fetchall()]


def recent(conn, limit=20, run_id=None):
    """The last frames posted, whatever their state — the trace as it happens."""
    q = (f"SELECT id, run_id, n, tag, phase, state, meta, asked_at FROM {TABLE} "
         f"{'WHERE run_id=%s ' if run_id else ''}ORDER BY id DESC LIMIT %s")
    with conn.cursor() as c:
        c.execute(q, ((run_id, limit) if run_id else (limit,)))
        return [dict(zip(("id", "run_id", "n", "tag", "phase", "state", "meta", "asked_at"), r))
                for r in c.fetchall()]


def answer(conn, rid, verdict):
    """Release one waiting step. `verdict` in go | run | abort."""
    if verdict not in ("go", "run", "abort"):
        raise ValueError(f"verdict must be go|run|abort, not {verdict!r}")
    with conn.cursor() as c:
        c.execute(f"UPDATE {TABLE} SET state=%s, answered_at=now() "
                  f"WHERE id=%s AND state='waiting'", (verdict, rid))
        return c.rowcount


def save_img(conn, rid, path):
    """Write a posted frame to disk so it can actually be looked at. Returns the path or None."""
    import base64
    from pathlib import Path
    with conn.cursor() as c:
        c.execute(f"SELECT img FROM {TABLE} WHERE id=%s", (rid,))
        row = c.fetchone()
    if not row or not row[0]:
        return None
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(base64.b64decode(row[0]))
    return str(p)


def purge(conn, keep_run=None, older_than_hours=24):
    """Frames are ~80 KB each; do not let a diagnostic table become the biggest one we own."""
    with conn.cursor() as c:
        if keep_run:
            c.execute(f"DELETE FROM {TABLE} WHERE run_id <> %s", (keep_run,))
        else:
            c.execute(f"DELETE FROM {TABLE} "
                      f"WHERE asked_at < now() - make_interval(hours => %s)", (older_than_hours,))
        return c.rowcount
