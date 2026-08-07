"""Give the live Neon tables real DATE / TIMESTAMPTZ / INTEGER columns.

Everything was created TEXT by dbstore._ddl(), so '22/07/2026' sorted next to '01/03/2019' as
strings and no date arithmetic was possible. This migrates in place, after proving every value
converts.

PROFILED FIRST, 2026-08-07 (this is why the conversions below are safe):

    causas.f_ingreso                4,061 / 4,061  dd/mm/yyyy
    causas.updated_at               4,061 / 4,061  ISO-8601 with Z
    cuadernos.fecha_tramite        77,255 / 77,255 dd/mm/yyyy
    cuadernos.fecha_diligencia     23,526 dd/mm/yyyy + 53,729 blank
    cuadernos.foja                 76,903 integers + 352 blank, nothing else
    escritos.fecha_ingreso            191 / 191    dd/mm/yyyy
    litigantes/ruts.updated_at              all    ISO-8601 with Z
    notificaciones_receptor.fecha  21,399 / 21,399 dd/mm/yyyy

DD/MM CONFIRMED, NOT ASSUMED: the max first component is 31 in all three date columns, so it
cannot be a month. Getting this backwards would silently corrupt 100k+ rows into plausible wrong
dates — the kind of damage nothing downstream would ever flag.

DELIBERATELY LEFT AS TEXT:

    cuadernos.folio, documentos.folio, anexos.folio
        4,166 and 82 values look like '[11E]' — a folio with an escrito marker. These are
        identifiers, not quantities. Casting to integer would have to drop the bracketed rows
        or the marker, and either way loses data that is currently correct.
    ruts.rut, bancos.rut, bancos.dv
        Identifiers, not numbers. A RUT's check digit can be 'K', and leading zeros matter.
        Arithmetic on a RUT is never meaningful, so numeric buys nothing and costs formatting.

Every table is copied to <table>_bak_<stamp> before it is touched. Run with --apply to execute;
without it you get the plan and the backup check only.
"""
import sys, argparse, time
import psycopg2
import dbstore

# (table, column, target type). The USING clause is derived from the type.
PLAN = [
    ("causas", "f_ingreso", "date"),
    ("causas", "updated_at", "timestamptz"),
    ("cuadernos", "fecha_tramite", "date"),
    ("cuadernos", "fecha_diligencia", "date"),
    ("cuadernos", "foja", "integer"),
    ("escritos", "fecha_ingreso", "date"),
    ("litigantes", "updated_at", "timestamptz"),
    ("ruts", "updated_at", "timestamptz"),
    ("notificaciones_receptor", "fecha", "date"),
    ("anexos", "fecha", "date"),                 # empty today; convert now so it never drifts
    ("sweep_progress", "updated_at", "timestamptz"),
]


def using(col, kind):
    """The conversion expression. Blank -> NULL in every case: '' is a perfectly ordinary value
    in a TEXT column and a hard error in every other type, so it must become NULL, not stay ''."""
    q = f'NULLIF(btrim("{col}"), \'\')'
    if kind == "integer":
        return f"{q}::integer"
    return f"{q}::{kind}"        # DateStyle=DMY makes dd/mm/yyyy unambiguous; ISO stays ISO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="execute (default: dry run)")
    a = ap.parse_args()

    stamp = time.strftime("%Y%m%d")
    conn = psycopg2.connect(**dbstore._conn_kwargs())
    conn.autocommit = False
    cur = conn.cursor()
    # dd/mm/yyyy is ambiguous to Postgres unless the session says which comes first.
    cur.execute("SET DateStyle = 'ISO, DMY'")

    cur.execute("""SELECT table_name, column_name, data_type FROM information_schema.columns
                   WHERE table_schema='public'""")
    live = {(t, c): d for t, c, d in cur.fetchall()}

    todo = []
    for t, c, kind in PLAN:
        cur_type = live.get((t, c))
        if cur_type is None:
            print(f"  SKIP {t}.{c} — no such column")
        elif cur_type == "text":
            todo.append((t, c, kind))
            print(f"  PLAN {t}.{c:18} text -> {kind}")
        else:
            print(f"  DONE {t}.{c:18} already {cur_type}")
    if not todo:
        print("nothing to do")
        return 0
    if not a.apply:
        print("\ndry run — re-run with --apply")
        return 0

    # ---- verify EVERY value converts before altering anything -------------------
    print("\nverifying conversions...")
    for t, c, kind in todo:
        try:
            cur.execute(f'SELECT count(*) FROM "{t}" WHERE {using(c, kind)} IS NULL '
                        f'AND NULLIF(btrim("{c}"), \'\') IS NOT NULL')
            bad = cur.fetchone()[0]
        except Exception as e:
            conn.rollback()
            print(f"  *** {t}.{c} WOULD FAIL: {str(e)[:120]}")
            return 2
        print(f"  ok   {t}.{c:18} unconvertible non-blank values: {bad}")
        if bad:
            conn.rollback()
            print("  refusing to migrate a column that would lose values")
            return 2

    # ---- backup, then alter -----------------------------------------------------
    tables = sorted({t for t, _, _ in todo})
    for t in tables:
        bak = f"{t}_bak_{stamp}"
        cur.execute(f'DROP TABLE IF EXISTS "{bak}"')
        cur.execute(f'CREATE TABLE "{bak}" AS SELECT * FROM "{t}"')
        cur.execute(f'SELECT count(*) FROM "{bak}"')
        print(f"  backup {bak}: {cur.fetchone()[0]:,} rows")

    for t, c, kind in todo:
        cur.execute(f'ALTER TABLE "{t}" ALTER COLUMN "{c}" TYPE {kind} USING {using(c, kind)}')
        print(f"  altered {t}.{c} -> {kind}")

    conn.commit()
    print("\ncommitted. spot check:")
    for t, c, kind in todo[:6]:
        cur.execute(f'SELECT min("{c}"), max("{c}") FROM "{t}"')
        lo, hi = cur.fetchone()
        print(f"  {t}.{c:18} min={lo} max={hi}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
