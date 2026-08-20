"""SCORE AN EXPERIMENT ARM THE WAY THE PROJECT IS ACTUALLY SCORED.

⚠️ CAUSAS PER HOUR, AND WHETHER IT TRIPPED. Nothing else. This file exists because for one day
the project's success metric drifted into "how closely does the worker match the recorded
operator", which can be computed offline with the site switched off -- the tell that you are
measuring a proxy. See felipe/CLAUDE.md -> "The ultimate goal".

    python expduty_score.py                          # the live arm in data/worker_h
    python expduty_score.py --dir ../data/expduty/prev-20260819-233000
    python expduty_score.py --dir A --vs B           # two arms side by side

⚠️ WALL CLOCK IS FIRST-LINE-TO-LAST-LINE PER SHARD, not the --max-minutes cap: an arm that died
at minute 9 must not be scored as if it ran the hour, or a trip reads as low throughput instead
of as a trip.
"""
import argparse
import re
from pathlib import Path

HERE = Path(__file__).parent
OPEN_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+open\s")
RESULT_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+\[\d+/\d+\]")
DOC_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+docs c2:\s+(\d+)\s+pdf")
DONE_RE = re.compile(r"DONE in ([\d.]+) min.*?opens=(\d+)\s+kept=(\d+)")
# ⚠️ The same signatures rate_watch treats as trouble. A rate without its consequences is a
# reassurance, not a measurement.
BAD_RE = re.compile(r"(BLOCKED|sin resultados|modal did not open|silent throttle|"
                    r"could not select|form is not usable|recovery \d+/|paginator stuck)")


def secs(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def score(d):
    d = Path(d)
    out = {"shards": 0, "opens": 0, "kept": 0, "results": 0, "docs": 0, "bad": 0,
           "wall": 0.0, "done": 0, "bad_lines": []}
    for f in sorted(d.glob("docs-s*.log")):
        try:
            text = f.read_bytes().replace(b"\x00", b"").decode("utf-8", "replace")
        except OSError:
            continue
        lines = text.splitlines()
        if not lines:
            continue
        out["shards"] += 1
        first = last = None
        for L in lines:
            m = OPEN_RE.match(L)
            if m:
                out["opens"] += 1
            elif RESULT_RE.match(L):
                out["results"] += 1
            else:
                m2 = DOC_RE.match(L)
                if m2:
                    out["docs"] += int(m2.group(2))
            if BAD_RE.search(L):
                out["bad"] += 1
                if len(out["bad_lines"]) < 6:
                    out["bad_lines"].append(f"{f.name}: {L.strip()[:110]}")
            m3 = re.match(r"^\[(\d{2}:\d{2}:\d{2})\]", L)
            if m3:
                t = secs(m3.group(1))
                first = t if first is None else first
                last = t
        dm = DONE_RE.search(text)
        if dm:
            out["done"] += 1
            out["kept"] += int(dm.group(3))
        # per-shard wall, summed then divided: shards overlap in time, so the ARM's wall clock is
        # the mean shard lifetime, not the sum and not the max.
        if first is not None and last is not None and last >= first:
            out["wall"] += (last - first) / 60.0
    if out["shards"]:
        out["wall"] /= out["shards"]
    return out


def show(label, s):
    print(f"\n=== {label} ===")
    if not s["shards"]:
        print("  no shard logs found")
        return
    wall = s["wall"] or 1e-9
    print(f"  {s['shards']} shard(s), mean lifetime {s['wall']:.1f} min, "
          f"{s['done']} finished cleanly")
    print(f"\n  THE BENCHMARK")
    print(f"    causas opened       {s['opens']:>6}")
    print(f"    causas/min          {s['opens'] / wall:>6.1f}   <- the score (fleet aggregate)")
    print(f"    causas/hour         {s['opens'] / wall * 60:>6.0f}")
    if s["kept"]:
        print(f"    kept (banked)       {s['kept']:>6}")
    else:
        # WARN: AN OPEN IS NOT A DELIVERED RECORD ON A SWEEP. A sweep re-opens what the bank
        # already holds -- historically only ~27% of its opens are new, against ~95% for
        # --fill. Both arms of one experiment share that discount so the COMPARISON is sound,
        # but never quote this as records/hour. `kept` fills in from the DONE line.
        print("    kept (banked)          n/a   <- no DONE line; sweep opens are ~27% new")
    print(f"\n  DID IT TRIP")
    verdict = "NO trouble events" if not s["bad"] else f"{s['bad']} TROUBLE EVENT(S)"
    print(f"    {verdict}")
    for b in s["bad_lines"]:
        print(f"      {b}")
    req = s["results"] + s["opens"] + s["docs"]
    print(f"\n  rate: {req / wall:.1f} req/min aggregate "
          f"({s['results']} results + {s['opens']} opens + {s['docs']} docs)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(HERE.parent / "data" / "worker_h"))
    ap.add_argument("--vs", default="")
    a = ap.parse_args()
    A = score(a.dir)
    show(Path(a.dir).name, A)
    if a.vs:
        B = score(a.vs)
        show(Path(a.vs).name, B)
        wa, wb = A["wall"] or 1e-9, B["wall"] or 1e-9
        ra, rb = A["opens"] / wa * 60, B["opens"] / wb * 60
        print("\n=== VERDICT ===")
        print(f"  causas/hour   {ra:.1f}  vs  {rb:.1f}   (x{rb / (ra or 1e-9):.2f})")
        print(f"  trouble       {A['bad']}  vs  {B['bad']}")
        if not A["bad"] and not B["bad"]:
            print("  ⚠️ NEITHER ARM TRIPPED — this cannot price survival, only throughput.")
            print("     Whichever delivered more causas wins outright; run nearer the wall to")
            print("     learn anything about blocks.")
        elif A["bad"] and not B["bad"]:
            print("  the SECOND arm survived where the first did not — stillness bought headroom.")
        elif B["bad"] and not A["bad"]:
            print("  the FIRST arm survived where the second did not.")
        else:
            print("  both tripped — compare causas delivered before the trip, above.")


if __name__ == "__main__":
    main()
