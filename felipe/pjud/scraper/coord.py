"""Distributed-worker coordination over Neon (the shared brain).

Multiple PCs each run a background worker (see run.py --worker). They coordinate
purely through these Neon tables — no always-on master server:

  worker_status  — each worker's live heartbeat (host, ip, corte, state, progress).
  corte_claims   — atomic work assignment: a worker grabs a whole corte so two PCs
                   never scrape the same causas (Postgres FOR UPDATE SKIP LOCKED).
  captcha_queue  — a worker posts its CAPTCHA image; the master (you) posts the answer.
  alerts         — a worker escalates an issue (blocked / error / needs-navigation).
  commands       — the master drives a worker (establish / pause / resume / stop /
                   take-control) — i.e. "navigation to the scraping zone, controlled
                   from the master".

The master console (an AppSheet view on these tables, or a small local dashboard)
reads/writes them so every human touch — establish, CAPTCHA, take-over — is central.
"""

import socket

import psycopg2
import psycopg2.extras

import dbstore

WORKER_STATES = ("idle", "establishing", "waiting_captcha", "scraping",
                 "blocked", "error", "paused", "done")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS worker_status (
    worker_id  TEXT PRIMARY KEY,
    host       TEXT,
    ip         TEXT,
    corte      TEXT,
    state      TEXT DEFAULT 'idle',
    done_count INT  DEFAULT 0,
    message    TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS corte_claims (
    corte      TEXT PRIMARY KEY,
    corte_name TEXT DEFAULT '',
    pending    INT  DEFAULT 0,
    status     TEXT DEFAULT 'available',   -- available | claimed | done
    worker_id  TEXT,
    claimed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS captcha_queue (
    id         BIGSERIAL PRIMARY KEY,
    worker_id  TEXT,
    image      TEXT,                       -- data: URL / base64 PNG of the CAPTCHA
    status     TEXT DEFAULT 'pending',     -- pending | solved | expired
    solution   TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS alerts (
    id         BIGSERIAL PRIMARY KEY,
    worker_id  TEXT,
    kind       TEXT,                        -- blocked | error | needs_navigation | info
    message    TEXT DEFAULT '',
    status     TEXT DEFAULT 'open',         -- open | ack | resolved
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS commands (
    id         BIGSERIAL PRIMARY KEY,
    worker_id  TEXT,
    command    TEXT,                        -- establish | pause | resume | stop | take_control
    args       TEXT DEFAULT '',
    status     TEXT DEFAULT 'pending',      -- pending | done
    created_at TIMESTAMPTZ DEFAULT now()
);
"""


def default_worker_id():
    return socket.gethostname()


class Coord:
    """Live handle to the coordination tables. Autocommit — every call is atomic."""

    def __init__(self, conn=None):
        self.conn = conn or psycopg2.connect(**dbstore._conn_kwargs())
        self.conn.autocommit = True

    def _reconnect(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self.conn = psycopg2.connect(**dbstore._conn_kwargs())
        self.conn.autocommit = True

    def _exec(self, sql, params=(), fetch=None):
        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    cur.execute(sql, params)
                    if fetch == "one":
                        return cur.fetchone()
                    if fetch == "all":
                        return cur.fetchall()
                    return None
            except psycopg2.OperationalError:
                if attempt == 1:
                    self._reconnect()
                    continue
                raise

    def ensure_schema(self):
        self._exec(_SCHEMA)

    # ── work assignment (atomic corte claim) ─────────────────────────────────
    def seed_cortes(self, pending_by_corte, names=None):
        """(Re)seed corte_claims from {corte_value: pending_count}. Refreshes the
        pending count on still-available cortes; leaves claimed/done ones alone."""
        names = names or {}
        for cv, cnt in pending_by_corte.items():
            self._exec(
                "INSERT INTO corte_claims (corte, corte_name, pending, status) "
                "VALUES (%s,%s,%s,'available') "
                "ON CONFLICT (corte) DO UPDATE SET pending=EXCLUDED.pending, "
                "corte_name=EXCLUDED.corte_name, updated_at=now() "
                "WHERE corte_claims.status='available'",
                (str(cv), names.get(cv, ""), int(cnt)))

    def claim_corte(self, worker_id):
        """Atomically grab the highest-pending available corte. Returns its value or
        None. FOR UPDATE SKIP LOCKED → two workers never grab the same corte."""
        row = self._exec(
            "UPDATE corte_claims SET status='claimed', worker_id=%s, "
            "claimed_at=now(), updated_at=now() WHERE corte = ("
            "  SELECT corte FROM corte_claims WHERE status='available' "
            "  ORDER BY pending DESC LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING corte",
            (worker_id,), fetch="one")
        return row[0] if row else None

    def finish_corte(self, corte, status="done"):
        self._exec("UPDATE corte_claims SET status=%s, updated_at=now() WHERE corte=%s",
                   (status, str(corte)))

    def release_corte(self, corte):
        """Put a corte back (e.g. worker blocked mid-corte) so another can take it."""
        self._exec("UPDATE corte_claims SET status='available', worker_id=NULL, "
                   "updated_at=now() WHERE corte=%s", (str(corte),))

    # ── heartbeat ────────────────────────────────────────────────────────────
    def heartbeat(self, worker_id, host="", ip="", corte="", state="idle",
                  done_count=0, message=""):
        self._exec(
            "INSERT INTO worker_status (worker_id,host,ip,corte,state,done_count,"
            "message,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,now()) "
            "ON CONFLICT (worker_id) DO UPDATE SET host=EXCLUDED.host, ip=EXCLUDED.ip, "
            "corte=EXCLUDED.corte, state=EXCLUDED.state, done_count=EXCLUDED.done_count, "
            "message=EXCLUDED.message, updated_at=now()",
            (worker_id, host, ip, corte, state, int(done_count), message))

    # ── captcha relay ────────────────────────────────────────────────────────
    def post_captcha(self, worker_id, image):
        row = self._exec("INSERT INTO captcha_queue (worker_id,image) VALUES (%s,%s) "
                         "RETURNING id", (worker_id, image), fetch="one")
        return row[0] if row else None

    def get_captcha_solution(self, captcha_id):
        """Returns the solution string once the master solves it, else None."""
        row = self._exec("SELECT solution FROM captcha_queue WHERE id=%s AND "
                         "status='solved'", (captcha_id,), fetch="one")
        return row[0] if row else None

    def expire_captcha(self, captcha_id):
        self._exec("UPDATE captcha_queue SET status='expired', updated_at=now() "
                   "WHERE id=%s AND status='pending'", (captcha_id,))

    # ── alerts ───────────────────────────────────────────────────────────────
    def post_alert(self, worker_id, kind, message=""):
        self._exec("INSERT INTO alerts (worker_id,kind,message) VALUES (%s,%s,%s)",
                   (worker_id, kind, message))

    # ── commands (master → worker) ───────────────────────────────────────────
    def next_command(self, worker_id):
        """The worker's oldest pending command, or None. (id, command, args)."""
        return self._exec("SELECT id,command,args FROM commands WHERE worker_id=%s AND "
                          "status='pending' ORDER BY id LIMIT 1", (worker_id,),
                          fetch="one")

    def ack_command(self, cmd_id):
        self._exec("UPDATE commands SET status='done' WHERE id=%s", (cmd_id,))

    # ── master-side reads/writes (console) ───────────────────────────────────
    def workers(self):
        return self._exec("SELECT worker_id,host,ip,corte,state,done_count,message,"
                          "updated_at FROM worker_status ORDER BY worker_id",
                          fetch="all") or []

    def pending_captchas(self):
        return self._exec("SELECT id,worker_id,image,created_at FROM captcha_queue "
                          "WHERE status='pending' ORDER BY id", fetch="all") or []

    def solve_captcha(self, captcha_id, solution):
        self._exec("UPDATE captcha_queue SET solution=%s, status='solved', "
                   "updated_at=now() WHERE id=%s", (solution, captcha_id))

    def open_alerts(self):
        return self._exec("SELECT id,worker_id,kind,message,created_at FROM alerts "
                          "WHERE status='open' ORDER BY id", fetch="all") or []

    def send_command(self, worker_id, command, args=""):
        self._exec("INSERT INTO commands (worker_id,command,args) VALUES (%s,%s,%s)",
                   (worker_id, command, args))
