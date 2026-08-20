"""MIGRATE cuaderno-2 Drive objects from the POSITIONAL key to the FOLIO key.

Before 2026-08-19 a document was stored as `{causa}/c2-{k:02d}.pdf`, where k is its POSITION in
historia_c2, while the database row it feeds is keyed on the document's FOLIO. Historia arrives
newest-first, so one new filing shifts every position and a later ingest would stamp the previous
document's URL onto the new folio's row. See ingest_worker_h.doc_obj.

    python migrate_doc_keys.py --dry     # show what would be renamed, touch nothing
    python migrate_doc_keys.py           # rename them

WARN: THIS RENAMES, IT DOES NOT RE-UPLOAD. Drive links are id-based, so every `doc_url` already
stored in Neon keeps working -- a rename changes the name and nothing else. Re-keying by
re-uploading would have meant pushing 4,281 files and orphaning the originals.

WARN: THE MAPPING IS ONLY UNAMBIGUOUS WHILE EXPOSURE IS ZERO. It is derived from the JSON on disk,
which is trustworthy precisely because no document-carrying causa has been scraped twice yet -- so
each (causa, position) still has exactly one folio. Any causa whose files disagree across scrapes
is REFUSED rather than guessed at, and reported. Run this before that stops being true.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import dbstore
import gstore
from ingest_worker_h import doc_obj

DATA = Path(__file__).parent.parent / "data" / "worker_h"


def mapping():
    """{legacy_flat_name: new_flat_name}, plus any (causa, position) that is ambiguous."""
    seen = defaultdict(set)          # (cid, k) -> {new_name}
    for f in sorted(DATA.glob("h-*.json")):
        if "state" in f.name:
            continue
        try:
            recs = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(recs, list):
            continue
        for r in recs:
            if not isinstance(r, dict):
                continue
            cid = r.get("causa_id")
            if not cid:
                continue
            for k, h in enumerate(r.get("historia_c2") or []):
                if not (h.get("_doc_file") or "").strip():
                    continue
                seen[(cid, k)].add(doc_obj(cid, h, k))
    out, bad = {}, []
    for (cid, k), names in seen.items():
        if len(names) != 1:
            bad.append((cid, k, sorted(names)))
            continue
        legacy = gstore._flatten_name(f"{cid}/c2-{k:02d}.pdf")
        new = gstore._flatten_name(next(iter(names)))
        if legacy != new:
            out[legacy] = new
    return out, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    m, bad = mapping()
    print(f"{len(m)} object(s) to re-key from the on-disk records")
    if bad:
        print(f"WARN: {len(bad)} (causa, position) pair(s) map to MORE THAN ONE folio -- refused:")
        for cid, k, names in bad[:8]:
            print(f"    {cid} position {k}: {names}")
        print("  These are the case this migration cannot decide. Resolve them by hand.")

    store = dbstore.Store()
    cache = store._load_doc_cache()          # {drive_name: link}
    print(f"{len(cache)} object(s) currently in the Documentos folder")

    # Drive ids, which the cache does not carry -- list once more for id+name.
    ids, page = {}, None
    while True:
        resp = store.drive.files().list(
            q=f"'{store.docs_folder}' in parents and trashed = false",
            fields="nextPageToken, files(id, name)", pageSize=1000, pageToken=page).execute()
        for f in resp.get("files", []):
            ids[f["name"]] = f["id"]
        page = resp.get("nextPageToken")
        if not page:
            break

    todo = [(old, new) for old, new in m.items() if old in ids]
    absent = len(m) - len(todo)
    collide = [(o, n) for o, n in todo if n in ids]
    print(f"  {len(todo)} present in Drive, {absent} recorded on disk but not in Drive")
    if collide:
        print(f"WARN: {len(collide)} target name(s) already exist -- skipped, not overwritten:")
        for o, n in collide[:5]:
            print(f"    {o} -> {n}")
    todo = [(o, n) for o, n in todo if n not in ids]

    if a.dry:
        for o, n in todo[:10]:
            print(f"    {o}  ->  {n}")
        print(f"--dry: nothing renamed ({len(todo)} would be)")
        return

    done = 0
    for old, new in todo:
        try:
            store.drive.files().update(fileId=ids[old], body={"name": new}).execute()
            done += 1
            if done % 250 == 0:
                print(f"  renamed {done}/{len(todo)}")
        except Exception as e:
            print(f"  [warn] {old}: {e}")
    print(f"renamed {done} object(s)")


if __name__ == "__main__":
    main()
