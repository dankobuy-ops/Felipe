"""STEP CONSOLE — see what a runner is about to do, and tell it whether to do it.

    python step_console.py --watch            # poll; save each frame; print what it is asking
    python step_console.py --go               # release the oldest waiting step
    python step_console.py --run              # release it AND stop asking for the rest of the run
    python step_console.py --abort            # stop the run where it stands
    python step_console.py --recent 20        # the trace so far, whatever its state
    python step_console.py --pull DIR         # every frame of the newest run, to disk
    python step_console.py --purge            # frames are ~80 KB each; clean up

The runner side is `stepgate.py`; read its header for why the channel is Neon and not a socket.

⚠️ FRAMES ARE WRITTEN TO DISK, ALWAYS. The whole failure mode this replaces was arguing about a
page nobody had seen. `--watch` saves every frame it prints, so there is a picture to open next to
the line of text, and the path is printed with it.
"""
import argparse
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
import stepgate

HERE = Path(__file__).parent
FRAMES = HERE.parent / "data" / "step_frames"


def _meta(row):
    import json
    try:
        return json.loads(row.get("meta") or "{}")
    except Exception:
        return {}


def describe(row, conn, save_to=None):
    """One waiting step, in the terms that decide the answer: where it is, what is on top."""
    m = _meta(row)
    print(f"\n  [{row['id']}] step {row['n']}  {row['tag']}   ({row.get('run_id')})")
    print(f"      url    {str(m.get('url'))[:96]}")
    print(f"      title  {str(m.get('title'))[:80]}")
    if m.get("frames"):
        print(f"      iframes {m['frames']}")
    if m.get("modals") or m.get("sheets"):
        print(f"      modals {m.get('modals')}  backdrops={m.get('sheets')}")
    if m.get("extra"):
        print(f"      extra  {str(m['extra'])[:200]}")
    txt = " / ".join(t.strip() for t in str(m.get("text", "")).splitlines() if t.strip())[:220]
    if txt:
        print(f"      text   {txt}")
    if save_to:
        p = stepgate.save_img(conn, row["id"], Path(save_to) / f"{row['id']}-{row['tag']}.jpg")
        if p:
            print(f"      frame  {p}")
    return row["id"]


def main():
    ap = argparse.ArgumentParser(
        description="Watch a stepping runner and answer it. See stepgate.py for the channel.")
    ap.add_argument("--watch", action="store_true", help="poll until a step is waiting")
    ap.add_argument("--every", type=float, default=4.0, help="poll seconds (default 4)")
    ap.add_argument("--for", dest="secs", type=float, default=0,
                    help="stop watching after N seconds (0 = until a step is waiting)")
    ap.add_argument("--go", nargs="?", const=-1, type=int, help="release one step (default: oldest waiting)")
    ap.add_argument("--run", nargs="?", const=-1, type=int, help="release and stop asking")
    ap.add_argument("--abort", nargs="?", const=-1, type=int, help="stop the run")
    ap.add_argument("--recent", type=int, default=0, help="list the last N frames posted")
    ap.add_argument("--pull", default="", help="write every frame of the newest run to this dir")
    ap.add_argument("--dir", default=str(FRAMES), help="where --watch saves frames")
    ap.add_argument("--purge", action="store_true", help="delete frames older than 24 h")
    a = ap.parse_args()

    conn = stepgate.connect()
    if conn is None:
        raise SystemExit("no database — check pjud_config.json / DATABASE_URL")

    if a.purge:
        print(f"purged {stepgate.purge(conn)} frame(s)")
        return

    if a.recent:
        for r in reversed(stepgate.recent(conn, a.recent)):
            m = _meta(r)
            print(f"  {r['id']:>6}  {str(r['asked_at'])[11:19]}  {r['phase']:<6} {r['state']:<8} "
                  f"{r['tag'][:34]:<34} {str(m.get('url', ''))[:52]}")
        return

    if a.pull:
        rows = stepgate.recent(conn, 500)
        if not rows:
            print("nothing posted yet")
            return
        run_id = rows[0]["run_id"]
        out = Path(a.pull)
        n = 0
        for r in reversed([x for x in rows if x["run_id"] == run_id]):
            if stepgate.save_img(conn, r["id"],
                                 out / f"{r['n']:03d}-{r['phase']}-{r['tag'][:40]}.jpg"):
                n += 1
        print(f"{n} frame(s) of run {run_id} -> {out}")
        return

    for flag, verdict in ((a.go, "go"), (a.run, "run"), (a.abort, "abort")):
        if flag is None:
            continue
        rid = flag
        if rid == -1:
            pend = stepgate.waiting(conn, 5)
            if not pend:
                print("nothing is waiting")
                return
            rid = pend[-1]["id"]            # oldest waiting
        n = stepgate.answer(conn, rid, verdict)
        print(f"{'sent' if n else 'NOT SENT (not waiting any more)'}: {verdict} -> step {rid}")
        return

    if a.watch:
        t0, seen = time.time(), set()
        Path(a.dir).mkdir(parents=True, exist_ok=True)
        print(f"watching for a step to answer (frames -> {a.dir})")
        while True:
            for r in reversed(stepgate.waiting(conn, 5)):
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                describe(r, conn, a.dir)
                print(f"\n  answer with:  python step_console.py --go {r['id']}"
                      f"   (or --run {r['id']} / --abort {r['id']})")
                return
            if a.secs and time.time() - t0 > a.secs:
                print(f"nothing waiting after {a.secs:.0f}s")
                return
            time.sleep(a.every)

    pend = stepgate.waiting(conn, 5)
    if not pend:
        print("nothing is waiting")
        for r in reversed(stepgate.recent(conn, 6)):
            m = _meta(r)
            print(f"  last: {r['id']:>6} {r['phase']:<6} {r['state']:<8} {r['tag'][:36]:<36} "
                  f"{str(m.get('url', ''))[:46]}")
        return
    Path(a.dir).mkdir(parents=True, exist_ok=True)
    for r in reversed(pend):
        describe(r, conn, a.dir)


if __name__ == "__main__":
    main()
