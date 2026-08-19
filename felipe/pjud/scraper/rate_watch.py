"""What request rate are the local workers ACTUALLY producing, right now?

Written 2026-08-12, because the theoretical rate is not the real one and acting on the
theoretical one is how you both over- and under-throttle.

⚠️ N workers do NOT produce N x (1/SEARCH_GAP) requests per minute, in either direction:

  it goes UP when causas are already banked. A seeded/backfilled pass skips the causa opens
  that used to dominate each cycle, so a worker stops spending 35 s per causa and becomes almost
  pure census. Slot 1 produced 66 result requests in TEN HOURS on 2026-08-11 (~0.1/min); the
  same worker on a seeded pass fires one every 20-40 s. Same code, same gaps, ~15x the rate.

  it goes DOWN as workers are added (operator, 2026-08-12). They share one connection and one
  machine, so each extra worker slows every other one: the site's own response time already
  dominates the cycle (12-26 s measured), and contention stretches it further. The gap is a
  FLOOR on the interval, never a promise of it.

Both effects are invisible in the config and visible only in the logs, so measure there. A
"result request" is a search OR a page advance -- a paginator click hits consultaFechaCivil.php
and returns a result set, so it draws on the same budget (HANDOFF_WORKERS.md, SEARCH_GAP).
A causa open costs its open plus its document, so it is counted as two.

    python rate_watch.py                # last 15 min, per slot and total
    python rate_watch.py --mins 60      # a longer baseline
    python rate_watch.py --watch 60     # re-measure every 60 s until stopped
"""
import argparse
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

# One line per result request: page 1 is the search, every later page is an advance.
RESULT_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+\[\d+/\d+\]")
OPEN_RE   = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+open\s")
EBOOK_RE  = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+ebook:.*\bPDF\b")
# ⚠️ ONE LINE, N REQUESTS. worker H's --docs-c2 reports a whole causa's documents in a single
# line ("docs c2: 4 pdf (308 KB)"), so this one is SUMMED, not counted. Counting the line would
# have under-reported the rate by a factor of 3.5 — and under-reporting is the direction that
# gets a fleet killed, because it reads as headroom.
DOC_RE    = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+docs c2:\s+(\d+)\s+pdf")
# The things that mean it is going wrong, so a rate is never read without its consequences.
BAD_RE    = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\].*(BLOCKED|modal did not open|silent throttle|"
                       r"could not select|form is not usable|recovery \d+/|paginator stuck)")


def slots():
    """(label, logfile) for every worker whose log exists — A's slots AND H's shards.

    ⚠️ IT ONLY EVER LOOKED AT worker_a. Six worker H's were pulling documents at full tilt on
    2026-08-19 and this reported `0.00/min` and `[ok] within the range this IP has sustained
    cleanly` — a rate tool that cannot see the fleet is worse than no rate tool, because it
    answers the question with a reassurance. And `Iniciar_Docs_Santiago.ps1` tells the operator to
    use it. Same failure as worker A's screenshots never being wired: grep for every producer
    before trusting a consumer.
    """
    out = [(d.name[-2:], d / "sweep.log")
           for d in sorted(DATA.glob("worker_a*")) if (d / "sweep.log").exists()]
    h = DATA / "worker_h"
    out += [("h" + f.stem.split("-s")[-1], f) for f in sorted(h.glob("docs-s*.log"))]
    out += [("h" + f.stem.split("p")[-1], f) for f in sorted(h.glob("h-*-p*.log"))]
    return out


def scan(path, since):
    """Count events written after `since` (a datetime today). Logs carry HH:MM:SS only.

    ⚠️ THE LOGS HAVE NO DATE, so a finished slot poisons the measurement. worker_a stopped at
    18:51 YESTERDAY; read as today that is later than a 14:12 cut-off, so its whole tail counted
    as current traffic and inflated the first reading from 1.5 to 2.6 result requests/min --
    which is the difference between "within what this IP has sustained" and "in the band where
    three workers died". Two guards: skip a file nothing has written to inside the window, and
    drop any line stamped in the future.
    """
    counts = {"result": 0, "open": 0, "ebook": 0, "doc": 0, "bad": 0}
    last = None
    try:
        if datetime.fromtimestamp(path.stat().st_mtime) < since:
            return counts, last                 # nothing written in this window: a dead slot
        # NUL bytes appear when a log was truncated rather than rotated -- strip, do not choke.
        text = path.read_bytes().replace(b"\x00", b"").decode("utf-8", "replace")
    except OSError:
        return counts, last
    today, now = since.date(), datetime.now()
    for line in text.splitlines():
        for key, rx in (("result", RESULT_RE), ("open", OPEN_RE), ("ebook", EBOOK_RE),
                        ("doc", DOC_RE), ("bad", BAD_RE)):
            m = rx.match(line)
            if not m:
                continue
            t = datetime.combine(today, datetime.strptime(m.group(1), "%H:%M:%S").time())
            if since <= t <= now:
                # ⚠️ `doc` carries its own count in the line; every other pattern is one request.
                counts[key] += int(m.group(2)) if key == "doc" else 1
                if key != "bad":
                    last = max(last, t) if last else t
            break
    return counts, last


def report(mins):
    since = datetime.now() - timedelta(minutes=mins)
    print(f"\n=== request rate over the last {mins} min "
          f"(since {since:%H:%M:%S}, now {datetime.now():%H:%M:%S}) ===")
    print(f"{'slot':<6}{'results':>9}{'opens':>7}{'ebooks':>8}{'docs':>7}{'req-equiv':>11}"
          f"{'req/min':>9}{'trouble':>9}  last")
    tot = {"result": 0, "open": 0, "ebook": 0, "doc": 0, "bad": 0}
    for label, path in slots():
        c, last = scan(path, since)
        if not any(c.values()):
            continue
        for k in tot:
            tot[k] += c[k]
        req = c["result"] + c["open"] + c["ebook"] + c["doc"]
        print(f"{label:<6}{c['result']:>9}{c['open']:>7}{c['ebook']:>8}{c['doc']:>7}{req:>11}"
              f"{req / mins:>9.2f}{c['bad']:>9}  {last:%H:%M:%S}" if last else "")
    req = tot["result"] + tot["open"] + tot["ebook"] + tot["doc"]
    print("-" * 76)
    print(f"{'ALL':<6}{tot['result']:>9}{tot['open']:>7}{tot['ebook']:>8}{tot['doc']:>7}{req:>11}"
          f"{req / mins:>9.2f}{tot['bad']:>9}")
    print(f"\n  result requests alone: {tot['result'] / mins:.2f}/min")
    # ⚠️ SPLIT THE MODAL AXIS FROM THE DOCUMENT AXIS. They are different endpoints and the only
    # measured ceilings belong to causaCivil.php (2026-08-17: ~56 POST/min killed four workers in
    # five minutes, ~23/min ran the hour). Whether docuN/docuS draws on the same budget is
    # UNKNOWN, so reporting one merged number would silently compare a document rate against a
    # modal-rate ceiling -- and that comparison has no evidence behind it either way.
    if tot["doc"]:
        print(f"  causaCivil.php axis:   {(tot['result'] + tot['open']) / mins:.2f}/min "
              f"(the axis the measured ceilings belong to)")
        print(f"  document axis:         {tot['doc'] / mins:.2f}/min "
              f"(docuN/docuS -- no measured ceiling exists; this run is the measurement)")
    # The only numbers we have to compare against, and they are DATED -- see HANDOFF_WORKERS §10,
    # measured before the scroll/keyboard-jitter fixes, so treat them as a flag, not a verdict.
    # ⚠️ ASCII ONLY BELOW THIS LINE. The Windows console here is cp1252 and a single un-encodable
    # character raises UnicodeEncodeError mid-print -- which is why ojv.note() carries its own
    # guard, and this script crashed on its very first run after printing the whole table.
    # ⚠️ READ THE RATE OVER 15 MIN, NOT 3. A worker re-entering fires its walk-in and first
    # searches in a burst, so a short window reports 2.6/min while the sustained figure is 1.8 --
    # and acting on the short one throttles a fleet that is perfectly healthy.
    #
    # ⚠️ AND JUDGE BY THE TROUBLE COLUMN, NOT THE RATE. The old ceiling (2 workers ~1.5/min;
    # 3 workers ~2.2/min died in 6 min, HANDOFF_WORKERS section 10) was measured BEFORE the
    # scroll and keyboard-jitter fixes, when the input stream still looked robotic -- the handoff
    # says as much. Measured against it 2026-08-12: FOUR workers held 2.6/min over 5 min and
    # 1.8/min over 15 with ZERO trouble events, and one session sustained ~3/min in speed_probe
    # on 08-10. So a number in the old "danger band" is not by itself a reason to slow down.
    # What actually preceded every failure today was trouble events, never the rate.
    r = tot["result"] / mins
    if r > 4.0:
        print("  [!] above anything this IP has been measured sustaining, on any config.")
    elif r > 2.6:
        print("  [.] above the highest CLEAN reading so far (4 workers, 2.6/min, 0 trouble,")
        print("      2026-08-12). Not a verdict -- judge it by the trouble column.")
    else:
        print("  [ok] within the range this IP has sustained cleanly.")
    if tot["bad"]:
        print(f"  [!] {tot['bad']} trouble event(s) in this window -- "
              f"a rate is only safe if this is 0.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mins", type=float, default=15)
    ap.add_argument("--watch", type=float, default=0, help="re-measure every N seconds")
    a = ap.parse_args()
    while True:
        report(a.mins)
        if not a.watch:
            return
        time.sleep(a.watch)


if __name__ == "__main__":
    main()
