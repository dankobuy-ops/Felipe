"""SUPERSEDED 2026-08-07 by worker_a.py. Kept as a thin shim so old commands keep working.

`worker_a.py --no-detail` IS this census, plus two fixes this file never had:

  * pagination — this version read only page 1 of each result set, so its per-tribunal counts are
    a FLOOR. 33 tribunales reported totals over 100; every causa past page 1 was invisible to it.
  * one copy of the entry/search/block machinery, now in ojv.py. Three separate copies of the
    rejection matcher are how every detector went blind at once when the site switched to Spanish.

Nothing here is deleted for history's sake: git has it. Use worker_a.py.
"""
import sys, os
from pathlib import Path

HERE = Path(__file__).parent
args = sys.argv[1:]
fwd = ["--no-detail"]
if args:                       # old signature was: census.py PORT [START_AT]
    fwd += ["--port", args[0]]
if len(args) > 1:
    fwd += ["--start", args[1]]

print(f"[census.py] superseded — running: worker_a.py {' '.join(fwd)}", flush=True)
os.execv(sys.executable, [sys.executable, "-u", str(HERE / "worker_a.py")] + fwd)
