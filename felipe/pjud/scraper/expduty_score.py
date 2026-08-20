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
import sys
from pathlib import Path

HERE = Path(__file__).parent
OPEN_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+open\s")
RESULT_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+\[\d+/\d+\]")
DOC_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+docs c2:\s+(\d+)\s+pdf")
DONE_RE = re.compile(r"DONE in ([\d.]+) min.*?opens=(\d+)\s+kept=(\d+)")
# ⚠️ The same signatures rate_watch treats as trouble. A rate without its consequences is a
# reassurance, not a measurement.
# WARN: THE LOG CARRIES BOTH HALVES OF THE KEY. "open 277-C-9940-2026" is tribunal 277 and
# rol C-9940-2026. A rol is unique only WITHIN a tribunal -- matching on it alone returned MORE
# hits than there were causas (861 against 495) and a NEGATIVE new count, which is how the
# mistake surfaced. Always join on the pair.
OPENKEY_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s+open\s+(\d+)-(\S+)")
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
        if first is not None and last is not None:
            span = last - first
            # WARN: THE LOGS CARRY HH:MM:SS WITH NO DATE, so a run that crosses midnight
            # ends EARLIER than it started and its span goes negative. The old guard
            # (last >= first) silently contributed ZERO wall for every such shard, and a
            # four-shard arm that all crossed midnight scored 242000000000 causas/min --
            # absurd enough to catch, which is the only reason it was caught. rate_watch
            # carries the same warning for the same reason; this file did not.
            if span < 0:
                span += 24 * 3600
            out["wall"] += span / 60.0
    if out["shards"]:
        out["wall"] /= out["shards"]
    return out


def new_records(d):
    """How many of this arm's opens are NOT already in Neon -- the actual benchmark.

    WARN: RUN THIS BEFORE THE INGEST, NOT AFTER. It asks what Neon does not yet hold, so
    once the arm has been ingested its own records ARE held and it scores near zero. Arm 1
    read 335 new before ingest and 23 after -- same run, same logs, 4% "useful". The number
    is a snapshot of the bank at the moment you ask, not a property of the run.

    WARN: `kept` IS NOT `banked`, AND `opens` IS NOT `records`. worker_h counts an open as
    kept when it passed the etapa/procedimiento gate; nothing there knows whether the bank
    already holds it. On 2026-08-20 an 8-worker arm opened 1,008 causas -- 1.7x a 4-worker
    arm -- and delivered FIVE RECORDS FEWER, because it re-swept a window the earlier arm had
    just harvested. Scoring on opens would have concluded "add workers" and been exactly wrong.
    """
    keys = set()
    for f in sorted(Path(d).glob("docs-s*.log")):
        try:
            text = f.read_bytes().replace(bytes([0]), b"").decode("utf-8", "replace")
        except OSError:
            continue
        for L in text.splitlines():
            m = OPENKEY_RE.match(L)
            if m:
                keys.add((m.group(1), m.group(2)))
    if not keys:
        return None
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import psycopg2, dbstore
        cn = psycopg2.connect(**dbstore._conn_kwargs())
        k = cn.cursor()
        k.execute("select count(*) from causas c join unnest(%s::text[], %s::text[]) "
                  "as w(tid, rol) on w.rol = c.rol and w.tid = c.tribunal_id::text",
                  ([x[0] for x in keys], [x[1] for x in keys]))
        held = k.fetchone()[0]
        cn.close()
    except Exception as e:
        print("  (could not reach Neon: " + str(e)[:70] + ")")
        return None
    return {"opened": len(keys), "held": held, "new": len(keys) - held}


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
        print(f"    kept (passed gate)  {s['kept']:>6}")
        # WARN: `kept` IS NOT `banked`. worker_h counts an open as kept when it passed the
        # etapa/procedimiento gate -- nothing there knows whether the bank already holds it.
        # Deduplication happens at ingest, so a fleet can report 94% kept and still deliver few
        # NEW records on a re-swept window. Quote this as work done, never as records delivered.
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
    nr = s.get("_new")
    if nr:
        print("")
        print("  DELIVERED (counted in Neon, not in the run's own tally)")
        print(f"    distinct opened     {nr['opened']:>6}")
        print(f"    already banked      {nr['held']:>6}")
        print(f"    NEW records         {nr['new']:>6}   = {nr['new'] / wall:.1f}/min"
              f"   ({100.0 * nr['new'] / max(1, nr['opened']):.0f}% of opens useful)")
    req = s["results"] + s["opens"] + s["docs"]
    print(f"\n  rate: {req / wall:.1f} req/min aggregate "
          f"({s['results']} results + {s['opens']} opens + {s['docs']} docs)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(HERE.parent / "data" / "worker_h"))
    ap.add_argument("--vs", default="")
    ap.add_argument("--new", action="store_true",
                    help="count how many opens are NEW to Neon -- the actual "
                         "benchmark. Opens and kept both overstate delivery on a "
                         "re-swept window.")
    a = ap.parse_args()
    A = score(a.dir)
    if a.new:
        A["_new"] = new_records(a.dir)
    show(Path(a.dir).name, A)
    if a.vs:
        B = score(a.vs)
        if a.new:
            B["_new"] = new_records(a.vs)
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
