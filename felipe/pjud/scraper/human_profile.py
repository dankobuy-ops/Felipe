"""HUMAN PROFILE — turn a recording into the numbers a spec can be held to.

    python human_profile.py                          # the newest recording
    python human_profile.py --file data/human/x.jsonl
    python human_profile.py --file A.jsonl --vs B.jsonl     # human vs our own run

⚠️ WHY THIS EXISTS. `human_record.py` captured eleven channels and the analysis of it was
"counts per second", which **cannot tell a human from a metronome**: a generator firing every
60 ms and a person both read as 16/s. Everything that distinguishes them is in the DISTRIBUTION
of the gaps, the shape of a move, and how long a button stays down — and all three were being
thrown away. This reads what the extended recorder now keeps.

⚠️ MEASURE OURSELVES WITH THE SAME RULER. Point this at a worker's own recording as well as at a
human's and diff them. Comparing our number against their number computed a different way is how
this project produced the burst theory, and it says so in three other places.

⚠️ THE OPTIMUM IS NOT THE MAXIMUM. A pointer emitting 40 moves/s is as anomalous as one emitting
0. Every line below is a target to MATCH, not to exceed.
"""
import argparse
import json
import math
import statistics as st
from pathlib import Path

HERE = Path(__file__).parent
HUMAN = HERE.parent / "data" / "human"


def load(path):
    """Every `input` row of a recording, plus the run's own metadata rows."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def pct(v, q):
    if not v:
        return None
    v = sorted(v)
    i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
    return v[i]


def describe(name, v, unit="ms"):
    if not v:
        return f"  {name:<26} —  (nothing recorded)"
    return (f"  {name:<26} n={len(v):<6} "
            f"p10={pct(v,.10):<7.1f} med={pct(v,.50):<7.1f} p90={pct(v,.90):<7.1f} "
            f"mean={st.mean(v):<7.1f} sd={(st.pstdev(v) if len(v)>1 else 0):<7.1f} {unit}")


def profile(rows):
    """Everything a spec can be held to, derived from one recording."""
    K = next((r["K"] for r in rows if r.get("K")), None)
    counts, ev, holds, wheels, paths = {}, [], [], [], []
    secs = 0
    for r in rows:
        if r.get("kind") != "input":
            continue
        secs += 1
        for k, v in r.items():
            if isinstance(v, int) and k in (
                    "mousemove", "mouseover", "mouseout", "wheel", "mousedown", "mouseup",
                    "keydown", "keyup", "click", "scroll", "focusin", "focusout",
                    "contextmenu", "dblclick", "select", "resize", "visibilitychange",
                    "blur", "selectionchange"):
                counts[k] = counts.get(k, 0) + v
        ev.extend(r.get("ev") or [])
        holds.extend(r.get("holds") or [])
        wheels.extend(r.get("wheels") or [])
        if r.get("path"):
            paths.append(r["path"])

    # ⚠️⚠️ WALL SECONDS, AND THE SILENT FRACTION BESIDE THEM — ALWAYS. This file used to report
    # per-ACTIVE-second rates and nothing else, which is the precise trap the handbook entry
    # written from its own output warns about. An always-on worker has almost no excluded seconds
    # and a human has more excluded than included, so the two averages describe two different
    # populations of second and the worker looks "under" while emitting 68% MORE per wall second.
    in_ts = sorted(r["t"] for r in rows if r.get("kind") == "input" and r.get("t") is not None)
    all_t = [r["t"] for r in rows if r.get("t") is not None]
    wall = (max(all_t) - min(all_t)) if len(all_t) > 1 else 0.0
    # One `input` row per second that had ANY activity, so consecutive active seconds differ by
    # ~1.0. A gap of g seconds is g-1 seconds in which nothing at all was emitted.
    sil = [round(b - a - 1.0, 2) for a, b in zip(in_ts, in_ts[1:]) if (b - a) >= 2.0]
    out = {"seconds": secs, "counts": counts, "K": K,
           "wall": wall, "silences": sil, "silent_total": sum(sil)}

    # ── inter-arrival gaps, per channel. THE thing counts cannot show. ──────────
    gaps = {}
    if K:
        by = {}
        for kind, t in ev:
            by.setdefault(K[kind] if kind < len(K) else str(kind), []).append(t)
        for k, ts in by.items():
            ts.sort()
            g = [b - a for a, b in zip(ts, ts[1:]) if 0 <= b - a < 5000]
            if g:
                gaps[k] = g
    out["gaps"] = gaps

    # ── click hold: mousedown -> mouseup. Nothing in a script decides this. ─────
    out["holds"] = [h[1] for h in holds if isinstance(h, list) and len(h) > 1]
    out["drag"] = [h[3] for h in holds if isinstance(h, list) and len(h) > 3]

    # ── wheel shape ────────────────────────────────────────────────────────────
    out["wheel_dy"] = [abs(w[2]) for w in wheels if isinstance(w, list) and len(w) > 2 and w[2]]
    out["wheel_modes"] = sorted({w[3] for w in wheels if isinstance(w, list) and len(w) > 3})

    # ── pointer geometry: speed, and how much of a move is spent slowing down ───
    # A human move is BALLISTIC then CORRECTIVE: fast out, overshoot, settle. An eased arc is
    # smooth the whole way, so its speed histogram is symmetric and its direction barely reverses.
    speeds, turns = [], []
    for p in paths:
        for (x0, y0, t0), (x1, y1, t1) in zip(p, p[1:]):
            dt = t1 - t0
            if dt <= 0 or dt > 400:
                continue
            d = math.hypot(x1 - x0, y1 - y0)
            speeds.append(d / dt * 1000.0)          # px/s
        for a, b, c in zip(p, p[1:], p[2:]):
            v1 = (b[0] - a[0], b[1] - a[1])
            v2 = (c[0] - b[0], c[1] - b[1])
            n1 = math.hypot(*v1)
            n2 = math.hypot(*v2)
            if n1 < 1 or n2 < 1:
                continue
            cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
            turns.append(math.degrees(math.acos(cos)))
    out["speed"] = speeds
    out["turn"] = turns
    return out


def report(label, p):
    print(f"\n=== {label} ===")
    wall = p.get("wall") or 0.0
    sil = p.get("silences") or []
    silent = p.get("silent_total") or 0.0
    print(f"  {p['seconds']} active second(s) of {wall:.0f} wall second(s)")
    print("\n  DUTY CYCLE — the rhythm, not the rate. Read this BEFORE the rates below.")
    if wall:
        print(f"    active          {100.0 * p['seconds'] / wall:>6.1f}%   (operator 41%)")
        print(f"    SILENT          {100.0 * silent / wall:>6.1f}%   (operator 59%)")
        print(f"    stops           {len(sil):>4}  = {len(sil) / (wall / 60.0):>5.2f}/min"
              f"   (operator 3.23/min)")
    print("   " + describe("stop length", sil, "s").strip()
          + "   (operator: median 6.1  p90 28.3  max 60.4)")
    tot = p["counts"]
    if p["seconds"] and wall:
        print("\n  RATES — per ACTIVE second AND per WALL second. Neither alone means anything.")
        print(f"    {'channel':<18} {'/active s':>10} {'/wall s':>10}")
        for k in sorted(tot, key=lambda k: -tot[k]):
            if tot[k]:
                print(f"    {k:<18} {tot[k] / p['seconds']:>10.2f} {tot[k] / wall:>10.2f}"
                      f"   ({tot[k]} total)")
    print("\n  INTER-ARRIVAL GAPS — a metronome and a hand have the same rate and different sd")
    for k in sorted(p["gaps"], key=lambda k: -len(p["gaps"][k]))[:8]:
        print(describe(k, p["gaps"][k]))
    print("\n  CLICK")
    print(describe("hold (down->up)", p["holds"]))
    print(describe("drag during click", p["drag"], "px"))
    print("\n  WHEEL")
    print(describe("|deltaY| per notch", p["wheel_dy"], "px"))
    print(f"    deltaModes seen: {p['wheel_modes'] or '—'}")
    print("\n  POINTER GEOMETRY")
    print(describe("speed", p["speed"], "px/s"))
    print(describe("turn between samples", p["turn"], "deg"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", default="", help="recording to profile (default: the newest)")
    ap.add_argument("--vs", default="", help="a second recording to diff against the first")
    a = ap.parse_args()

    f = Path(a.file) if a.file else None
    if f is None:
        cands = sorted(HUMAN.glob("*.jsonl"))
        if not cands:
            raise SystemExit(f"no recordings under {HUMAN}")
        f = cands[-1]
    rows = load(f)
    p = profile(rows)
    report(f.name, p)

    if a.vs:
        q = profile(load(a.vs))
        report(Path(a.vs).name, q)
        print(f"\n=== {f.name}  vs  {Path(a.vs).name} ===")
        print("  ⚠️ A ratio near 1.00 is the goal. Above 1 is as detectable as below.")
        for k in sorted(set(p["counts"]) | set(q["counts"])):
            ra = p["counts"].get(k, 0) / max(1, p["seconds"])
            rb = q["counts"].get(k, 0) / max(1, q["seconds"])
            if ra or rb:
                r = (rb / ra) if ra else float("inf")
                print(f"    {k:<18} {ra:>7.2f}/s  ->  {rb:>7.2f}/s   x{r:.2f}")
        for name, key in (("hold", "holds"), ("speed", "speed"), ("turn", "turn")):
            va, vb = p[key], q[key]
            if va and vb:
                print(f"    {name:<18} med {pct(va,.5):>7.1f}  ->  {pct(vb,.5):>7.1f}"
                      f"   sd {st.pstdev(va):>6.1f} -> {st.pstdev(vb):>6.1f}")


if __name__ == "__main__":
    main()
