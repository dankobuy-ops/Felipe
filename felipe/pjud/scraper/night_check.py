"""NIGHT_CHECK — decide whether a queued test MEASURED anything, and say so in the job summary.

⚠️ THE RULE THIS EXISTS FOR: green/red must be decided on whether the measurement was WRITTEN,
never on whether the process exited 0. Two `pjud-velocidad` runs on 2026-08-12 reported themselves
as successful measurements while both had crashed inside setup, because the step ended with
`|| echo "a refusal is the measurement"`. A probe whose failures look like results launders a bug
into a number somebody later plans against.

⚠️ AND IT MUST DISTINGUISH "nothing wrong" FROM "I could not tell". A check that cannot run says
so loudly and exits non-zero; it never returns a reassuring zero by default.

Stages:
    before      snapshot the row counts to /tmp/night_<label>.json
    after       diff against the snapshot; --require-docs N fails if documentos grew by less
    after-c     the worker C invariant: an unchanged causa must cost ZERO document fetches
    probe       read a worker A state.json and report what the session actually reached
    report      the morning table

ASCII ONLY in everything printed. A `⚠️` in a help string once crashed the whole run on Windows
cp1252, and this file is read on both.
"""
import sys, json, argparse, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import dbstore

SNAP = pathlib.Path("/tmp")
COUNTS = {
    "causas": "SELECT count(*) FROM causas",
    "causas_full": "SELECT count(*) FROM causas WHERE fill_status='full'",
    "cuadernos": "SELECT count(*) FROM cuadernos",
    "cuadernos_geo": "SELECT count(*) FROM cuadernos WHERE georref <> ''",
    "documentos": "SELECT count(*) FROM documentos",
    "anexos": "SELECT count(*) FROM anexos",
    "escritos": "SELECT count(*) FROM escritos",
    "litigantes": "SELECT count(*) FROM litigantes",
}


def counts():
    c = dbstore.Store().conn.cursor()
    out = {}
    for k, q in COUNTS.items():
        c.execute(q)
        out[k] = c.fetchone()[0]
    return out


def emit(lines):
    text = "\n".join(lines)
    print(text)
    import os
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True,
                    choices=("before", "after", "after-c", "probe", "report"))
    ap.add_argument("--label", default="test")
    ap.add_argument("--slot", type=int, default=1)
    ap.add_argument("--require-docs", type=int, default=0,
                    help="fail unless documentos grew by at least this many")
    ap.add_argument("--require-full", type=int, default=0,
                    help="fail unless this many causas reached fill_status='full'. This is the "
                         "real success criterion for a worker B run: 'some documents were "
                         "written' can be true of a run that was refused on causa two.")
    a = ap.parse_args()
    snap = SNAP / f"night_{a.label}.json"

    if a.stage == "before":
        n = counts()
        snap.write_text(json.dumps(n), encoding="utf-8")
        emit([f"### {a.label} - antes", "",
              "| tabla | filas |", "|---|---:|"] +
             [f"| {k} | {v:,} |" for k, v in n.items()])
        return 0

    if a.stage == "probe":
        # A worker A session's own verdict. `finished`/`reason`/`blocks` are written by finish()
        # on EVERY exit path precisely so something outside the process can read them.
        f = pathlib.Path(f"../data/worker_a{a.slot}/state.json")
        if not f.exists():
            emit([f"### {a.label}", "",
                  "**NO STATE FILE** - the worker never got far enough to write one. "
                  "That is ignorance, not a clean result."])
            return 1
        st = json.loads(f.read_text(encoding="utf-8"))
        m = st.get("meta", {})
        t = st.get("tribunales", {})
        opens = len(st.get("causas", {}))
        emit([f"### {a.label}", "",
              f"- opens: **{opens}**",
              f"- reason: **{m.get('reason','?')}** | finished: {m.get('finished','?')} | "
              f"blocks: {m.get('blocks','?')} | stopped_at_idx: {m.get('stopped_at_idx','?')}",
              f"- tribunales barridos: {len(t)}",
              "",
              "Contra el set bloqueado (74-85 opens, 68-70 min, murieron en Antofagasta idx 16-18)."])
        return 0

    if a.stage == "report":
        n = counts()
        emit(["### Estado final de Neon", "",
              "| tabla | filas |", "|---|---:|"] +
             [f"| {k} | {v:,} |" for k, v in n.items()])
        return 0

    # after / after-c
    if not snap.exists():
        emit([f"### {a.label}", "", "**COULD NOT CHECK** - no `before` snapshot. "
              "Reporting nothing rather than reporting success."])
        return 1
    before = json.loads(snap.read_text(encoding="utf-8"))
    now = counts()
    delta = {k: now[k] - before.get(k, 0) for k in now}
    emit([f"### {a.label} - despues", "",
          "| tabla | antes | despues | delta |", "|---|---:|---:|---:|"] +
         [f"| {k} | {before.get(k,0):,} | {now[k]:,} | {delta[k]:+,} |" for k in now])

    rc = 0
    if a.require_docs and delta["documentos"] < a.require_docs:
        emit(["", f"**FALLO: documentos crecio {delta['documentos']}, se esperaba al menos "
                  f"{a.require_docs}.** El worker abrio causas pero no guardo ningun documento - "
                  f"que es exactamente el estado en que estaba todo antes de esta noche "
                  f"(documentos=0 con 45.701 filas de cuadernos). No sirve seguir a b_real."])
        rc = 1

    if a.require_full and delta["causas_full"] < a.require_full:
        emit(["", f"**FALLO: solo {delta['causas_full']} causa(s) llegaron a 'full', se pedian "
                  f"{a.require_full}.** El worker se detuvo antes de terminar su lista - "
                  f"bloqueo, o el ritmo no aguanta. Los documentos que si alcanzo a guardar estan "
                  f"en Neon igual: B escribe por causa, no al final."])
        rc = 1

    if a.stage == "after-c":
        f = pathlib.Path("../data/worker_c/last_run.json")
        if not f.exists():
            emit(["", "**NO SE PUDO VERIFICAR**: worker C no dejo last_run.json."])
            return 1
        r = json.loads(f.read_text(encoding="utf-8"))
        emit(["", f"- causas re-chequeadas: **{r['checked']}** | con cambios: **{r['moved']}** | "
                  f"filas nuevas: {r['new_rows']} | fallidas: {r['failed']}",
              f"- documentos re-comprados sobre filas ya conocidas: **{r['refetched_on_known_rows']}**"])
        # THE invariant. Worker C's entire value is that a finished causa costs one open and no
        # fetches. If the row ids drift, KNOWN_DOCS matches nothing, every skip list is empty, and
        # C quietly becomes worker B at worker B's price while still reporting success.
        if r["refetched_on_known_rows"] > 0:
            emit(["", f"**FALLO: worker C volvio a comprar {r['refetched_on_known_rows']} "
                      f"documento(s) de filas que ya teniamos**, minutos despues de que worker B "
                      f"las guardara. O el tribunal los publico justo ahora (improbable), o los "
                      f"ids de fila ya no calzan con Neon y C esta re-comprando la causa entera. "
                      f"Sin esto, C no vale su presupuesto de sesion."])
            rc = 1
        elif r["checked"] and not r["moved"]:
            emit(["", "**OK: cada causa costo una apertura y CERO descargas.** "
                      "Eso es exactamente para lo que existe worker C."])
    return rc


if __name__ == "__main__":
    sys.exit(main())
