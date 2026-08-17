"""WATCH LIVE — look at what the workers are doing, from here, while they do it.

    python watch_live.py                 # opens http://127.0.0.1:8899 in your browser
    python watch_live.py --port 9100
    python watch_live.py --once          # one text snapshot, no server (for a log or a check)

Every worker started with --live publishes a jpeg of its screen plus its own log tail into Neon
(see live_view.py). This is the other end: it polls that table and paints one card per worker.
It works exactly the same whether the worker is a Chrome on this desk or a GitHub runner in a
datacenter — which is the point, because the runner is the one nobody can look at.

⚠️ IT SENDS THE SEQUENCE NUMBER IT ALREADY HOLDS, so a page that is standing still costs a few
hundred bytes a poll instead of an 80 KB picture. A worker idling through a 25 s pacing wait
publishes one frame; the viewer downloads it once.

⚠️ LOCALHOST ONLY, deliberately. The frames are of a logged-in session on a live site and the
database credentials are in this process. Binding to 0.0.0.0 would put both on the LAN.
"""

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
import live_view

PAGE = """<!doctype html><meta charset="utf-8"><title>PJUD — workers en vivo</title>
<style>
 :root{color-scheme:dark}
 body{margin:0;background:#11131a;color:#dfe3ee;font:13px/1.45 ui-monospace,Consolas,monospace}
 header{padding:8px 14px;background:#171a24;border-bottom:1px solid #262a38;
        display:flex;gap:14px;align-items:baseline}
 h1{font-size:14px;margin:0;font-weight:600;letter-spacing:.02em}
 #conn{font-size:11px;color:#7d859c}
 .grid{display:grid;gap:14px;padding:14px;
       grid-template-columns:repeat(auto-fit,minmax(460px,1fr))}
 .card{background:#171a24;border:1px solid #262a38;border-radius:8px;overflow:hidden}
 .hd{padding:7px 11px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;
     border-bottom:1px solid #262a38}
 .slot{font-weight:700;color:#8ab4ff}
 .meta{font-size:11px;color:#7d859c}
 .age{margin-left:auto;font-size:11px;padding:1px 7px;border-radius:9px}
 .ok{background:#14351f;color:#7ee2a8}.warn{background:#3a3113;color:#e8c86a}
 .bad{background:#3d1a1a;color:#ff9a9a}
 .phase{padding:6px 11px;background:#1d2130;color:#cfe0ff;font-size:12px;
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 img{display:block;width:100%;background:#000}
 .noimg{padding:34px 11px;text-align:center;color:#5c6479}
 pre{margin:0;padding:8px 11px;max-height:190px;overflow:auto;font-size:11px;
     color:#9aa3ba;border-top:1px solid #262a38;white-space:pre-wrap}
 .empty{padding:40px;text-align:center;color:#7d859c}
</style>
<header><h1>PJUD — workers en vivo</h1><span id="conn" class="meta"></span></header>
<div class="grid" id="g"></div>
<div class="empty" id="e">esperando a que un worker publique…<br>
  <span style="font-size:11px">arráncalo con <code>--live</code></span></div>
<script>
const seen = {};          // slot -> seq we already hold, so a still page costs nothing
const imgs = {};
function ageCls(a){ return a < 25 ? 'ok' : a < 90 ? 'warn' : 'bad'; }
function hhmm(s){ const m=Math.floor(s/60); return m<60? m+'m' : Math.floor(m/60)+'h'+(m%60)+'m'; }
async function poll(){
  try{
    const have = Object.entries(seen).map(([k,v])=>k+':'+v).join(',');
    const r = await fetch('/api?have='+encodeURIComponent(have));
    const rows = await r.json();
    document.getElementById('conn').textContent =
      rows.length + ' worker(s) · ' + new Date().toLocaleTimeString();
    document.getElementById('e').style.display = rows.length ? 'none' : '';
    for (const w of rows){
      let c = document.getElementById('c'+w.slot);
      if (!c){
        c = document.createElement('div'); c.className='card'; c.id='c'+w.slot;
        c.innerHTML = '<div class="hd"><span class="slot"></span><span class="meta"></span>'
                    + '<span class="age"></span></div><div class="phase"></div>'
                    + '<img><div class="noimg" style="display:none">sin imagen todavía</div>'
                    + '<pre></pre>';
        document.getElementById('g').appendChild(c);
        imgs[w.slot] = c.querySelector('img');
      }
      c.querySelector('.slot').textContent = 'slot ' + w.slot;
      c.querySelector('.hd .meta').textContent =
        [w.host, w.ip, w.run_id!=='local' ? 'run '+w.run_id : '', hhmm(w.uptime)]
        .filter(Boolean).join(' · ');
      const age = c.querySelector('.age');
      age.textContent = w.age.toFixed(0)+'s'; age.className = 'age '+ageCls(w.age);
      c.querySelector('.phase').textContent = w.phase || '';
      c.querySelector('pre').textContent = w.tail || '';
      if (w.frame){
        seen[w.slot] = w.seq;
        imgs[w.slot].src = 'data:image/jpeg;base64,' + w.frame;
        imgs[w.slot].style.display=''; c.querySelector('.noimg').style.display='none';
      } else if (!seen[w.slot]){
        imgs[w.slot].style.display='none'; c.querySelector('.noimg').style.display='';
      }
    }
  }catch(e){
    document.getElementById('conn').textContent = 'sin conexión al visor — ' + e;
  }
}
poll(); setInterval(poll, 2000);
</script>"""


class Handler(BaseHTTPRequestHandler):
    lock = threading.Lock()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api":
            q = parse_qs(u.query)
            have = {}
            for part in (q.get("have", [""])[0] or "").split(","):
                if ":" in part:
                    k, _, v = part.partition(":")
                    have[k] = v
            try:
                # ⚠️ ONE QUERY AT A TIME. Browsers open several connections and this handler is
                # threaded, so without the lock two polls share one psycopg2 connection and
                # Postgres answers with "another command is already in progress".
                with self.lock:
                    rows = self.server.fetch(have)
                body = json.dumps(rows).encode("utf-8")
            except Exception as e:
                body = json.dumps({"error": str(e)[:200]}).encode("utf-8")
            self._send(body, "application/json")
            return
        self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")

    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass          # a poll every two seconds would drown the console it is running in


def once():
    """One text snapshot. For a terminal, a log, or a quick 'is it alive' without a browser."""
    for w in live_view.read_all():
        print(f"── slot {w['slot']}  {w['host']} {w['ip']} run={w['run_id']}  "
              f"up {w['uptime']/60:.0f}m  last frame {w['age']:.0f}s ago  seq={w['seq']}")
        print(f"   {w['phase']}")
        print(f"   {w['url'][:110]}")
        for line in (w["tail"] or "").splitlines()[-8:]:
            print(f"   | {line}")


def main():
    # ⚠️ NOT description=__doc__. argparse prints it to the console, the module docstring carries
    # the project's usual arrows and warning signs, and a Windows cp1252 console cannot encode
    # them — so --help died with a UnicodeEncodeError while the tool itself was fine. Same trap
    # the argument help strings are already ASCII-only for.
    ap = argparse.ArgumentParser(
        description="Watch PJUD workers live. Each worker started with --live publishes a jpeg "
                    "of its screen plus its log tail to Neon; this serves them on localhost.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--once", action="store_true", help="print one snapshot and exit")
    ap.add_argument("--no-open", action="store_true", help="do not open a browser")
    a = ap.parse_args()
    if a.once:
        once()
        return
    import psycopg2
    import dbstore

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)

    def connect():
        c = psycopg2.connect(**dbstore._conn_kwargs())
        c.autocommit = True
        return c

    def fetch(have):
        # ⚠️ RECONNECT, DO NOT DIE. A viewer left open across a lunch break outlives an idle Neon
        # connection, and a dashboard that goes permanently blank because of that is worse than
        # no dashboard: it looks like the workers stopped.
        try:
            return live_view.read_all(srv.conn, have)
        except Exception:
            srv.conn = connect()
            return live_view.read_all(srv.conn, have)

    srv.conn = connect()
    srv.fetch = fetch
    url = f"http://127.0.0.1:{a.port}"
    print(f"watching -> {url}   (ctrl-c to stop)")
    if not a.no_open:
        threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)),
                         daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
