"""Remove the causas the new header-ETAPA gate rejects, and everything hanging off them.

⚠️ THE VERDICT COMES FROM run.etapa_rejected(), THE SAME FUNCTION THE SCRAPER GATES ON. A parallel
SQL predicate would be a second implementation of the rule, and second implementations drift --
this repo has paid for that with duplicated block detectors and a hand-rolled ingest mapping. If
the gate changes, this changes with it, for free.

⚠️ --apply WRITES A BACKUP FIRST. Deletion is the one thing here that cannot be undone by running
the scraper again: the causas are cheap to rediscover, but the historia, litigantes and document
URLs attached to them are not. The backup is a plain JSON file; keep it until the next full sweep
has proven the filter behaves.

    python clean_etapas.py                 # dry run: counts and a sample, touches nothing
    python clean_etapas.py --apply         # back up, then delete
"""
import sys, json, argparse, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dbstore
import run

# causa_id is the parent key on these; cuaderno-keyed tables are reached through cuadernos.
CHILD_BY_CAUSA = ("litigantes", "escritos", "cuadernos", "notificaciones_receptor")
CHILD_BY_CUADERNO = ("documentos", "anexos")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--backup-dir", default=str(Path(__file__).parent.parent / "data"))
    a = ap.parse_args()

    store = dbstore.Store()
    cur = store.conn.cursor()
    cur.execute("SELECT causa_id, COALESCE(etapa,'') FROM causas")
    rows = cur.fetchall()
    doomed = [cid for cid, et in rows if run.etapa_rejected(et)]
    by_etapa = {}
    for cid, et in rows:
        if run.etapa_rejected(et):
            by_etapa[et] = by_etapa.get(et, 0) + 1

    print(f"causas total          {len(rows):,}")
    print(f"rejected by the gate  {len(doomed):,}  ({100*len(doomed)/max(1,len(rows)):.1f}%)")
    for et, n in sorted(by_etapa.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>6}  {et}")
    if not doomed:
        print("nothing to do.")
        return 0

    # What hangs off them, so the number deleted is never a surprise.
    counts = {}
    for tab in CHILD_BY_CAUSA:
        cur.execute(f"SELECT count(*) FROM {tab} WHERE causa_id = ANY(%s)", (doomed,))
        counts[tab] = cur.fetchone()[0]
    for tab in CHILD_BY_CUADERNO:
        cur.execute(f"SELECT count(*) FROM {tab} WHERE cuaderno_id IN "
                    f"(SELECT id FROM cuadernos WHERE causa_id = ANY(%s))", (doomed,))
        counts[tab] = cur.fetchone()[0]
    print("\nchild rows that go with them:")
    for tab, n in counts.items():
        print(f"    {n:>6}  {tab}")

    if not a.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply to delete.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(a.backup_dir) / f"deleted_etapas_{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    dump = {"when": stamp, "rule": list(run.ETAPA_SKIP), "causa_ids": doomed, "tables": {}}
    cur.execute("SELECT row_to_json(c) FROM causas c WHERE causa_id = ANY(%s)", (doomed,))
    dump["tables"]["causas"] = [r[0] for r in cur.fetchall()]
    for tab in CHILD_BY_CAUSA:
        cur.execute(f"SELECT row_to_json(t) FROM {tab} t WHERE causa_id = ANY(%s)", (doomed,))
        dump["tables"][tab] = [r[0] for r in cur.fetchall()]
    for tab in CHILD_BY_CUADERNO:
        cur.execute(f"SELECT row_to_json(t) FROM {tab} t WHERE cuaderno_id IN "
                    f"(SELECT id FROM cuadernos WHERE causa_id = ANY(%s))", (doomed,))
        dump["tables"][tab] = [r[0] for r in cur.fetchall()]
    out.write_text(json.dumps(dump, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nbackup written: {out}  ({out.stat().st_size:,} bytes)")

    # Children first: documentos/anexos hang off cuadernos, so cuadernos must go last of those.
    deleted = {}
    for tab in CHILD_BY_CUADERNO:
        cur.execute(f"DELETE FROM {tab} WHERE cuaderno_id IN "
                    f"(SELECT id FROM cuadernos WHERE causa_id = ANY(%s))", (doomed,))
        deleted[tab] = cur.rowcount
    for tab in CHILD_BY_CAUSA:
        cur.execute(f"DELETE FROM {tab} WHERE causa_id = ANY(%s)", (doomed,))
        deleted[tab] = cur.rowcount
    cur.execute("DELETE FROM causas WHERE causa_id = ANY(%s)", (doomed,))
    deleted["causas"] = cur.rowcount

    print("deleted:")
    for tab, n in deleted.items():
        print(f"    {n:>6}  {tab}")
    cur.execute("SELECT count(*) FROM causas")
    print(f"\ncausas remaining: {cur.fetchone()[0]:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
