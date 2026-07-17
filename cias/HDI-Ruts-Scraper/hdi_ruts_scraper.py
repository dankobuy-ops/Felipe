"""HDI-Ruts-Scraper — pull client email + phone by RUT from HDI's broker cotizador
and record them in a Google Sheet.

DATA FLOW
  - RUT source:   Patentes tab, column B (rut_propietario)
  - Dedupe:       Patentes tab, column M ("HDI" flag). A row is "to do" only if its
                  flag is empty. Every checked RUT (data OR not) gets the flag set,
                  so nothing is ever re-scraped.
  - Output:       HDI tab (A=Rut, B=Correo, C=Telefono) — APPEND, email rows only.
                  Duplicate RUTs already in the HDI tab are not appended again.

WORKFLOW
  1. Open the monitored Chrome:   python cdp.py launch
  2. In that window: log in to the HDI broker portal and open the vehicle cotizador
     (Cotizadores -> Vehiculo) so the "Rut del Cliente" form is showing.
  3. Run:                         python hdi_ruts_scraper.py
     Options: --limit N (first N to-do rows)   --start ROW (skip Patentes rows above ROW)

HOW THE LOOKUP WORKS (the non-obvious bits — see README.md)
  real keystrokes (not fill()) -> click empty space to blur (not Tab, never Limpiar)
  -> read the email/celular FIELDS as ground truth. Empty after WAIT s = no data.
  Collision guard + verify-retry make it reliable; a health probe every 50 rows
  stops the run cleanly if the session expires. Safe to stop/kill and re-run.

CONFIG — edit here if the sheet layout changes (see README.md).
"""
import sys, os, re, time

# ─── CONFIG ──────────────────────────────────────────────────────────────────
SHEET_ID     = "1HDrOxgRtMngxY92MInOY6nI2bfO1mcwP_7GVvRFUM9g"
SRC_TAB      = "Patentes"     # tab holding the RUTs to look up
SRC_RUT_COL  = "B"            # column with the RUTs
SRC_FLAG_COL = "M"            # per-company "checked" flag column (HDI)
SRC_FIRST_ROW = 2             # first data row (row 1 = headers)
DEST_TAB     = "HDI"          # output tab: A=Rut, B=Correo, C=Telefono (row 1 = header)
CANARY_RUT   = "7620655-4"    # a RUT known to HAVE data — used for the health probe
GAUTH_DIR    = r"C:\Claude\felipe\scraper"        # folder with gauth.py + token.json
PORT = int(os.environ.get("CDP_PORT", "9333"))
WAIT = float(os.environ.get("LOOKUP_WAIT", "5"))   # max seconds to wait for a load
GAP  = float(os.environ.get("LOOKUP_GAP", "0.4"))  # pause between RUTs
FLAG = "x"                                          # value written to the flag column
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, GAUTH_DIR)
import gauth  # noqa: E402
try:
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright


def digits(rut):
    return re.sub(r'[^0-9kK]', '', rut or '').upper()


FIND_POINT = """() => {
  const w = window.innerWidth, h = window.innerHeight;
  const bad = new Set(['INPUT','SELECT','TEXTAREA','BUTTON','A','LABEL','OPTION']);
  const cands = [[w*0.5,28],[w*0.5,h*0.82],[w*0.62,h*0.5],[w*0.4,h*0.75],[w*0.5,h*0.6]];
  for (const [x,y] of cands) {
    const el = document.elementFromPoint(x,y);
    if (el && !bad.has(el.tagName) && !el.closest('input,select,button,a,label'))
      return {x: Math.round(x), y: Math.round(y)};
  }
  return {x: Math.round(w*0.5), y: 28};
}"""


class Looker:
    """HDI cotizador lookup: RUT -> {email, celular}."""
    def __init__(self, page):
        self.page = page
        pt = page.evaluate(FIND_POINT)          # verified empty spot to click-away on
        self.bx, self.by = pt["x"], pt["y"]

    def _fields(self):
        return self.page.evaluate("""() => ({
            e: (document.getElementById('Main_txtEmail')||{}).value || '',
            c: (document.getElementById('Main_txtCelular')||{}).value || ''
        })""")

    def _clear_out(self):
        self.page.evaluate("""() => { for (const id of ['Main_txtEmail','Main_txtCelular']){
            const e=document.getElementById(id); if(e) e.value=''; } }""")

    def _rutval(self):
        return digits(self.page.locator("#Main_txtRut").input_value())

    def lookup(self, rut):
        k = digits(rut)
        r = self.page.locator("#Main_txtRut")
        time.sleep(0.4)                          # let the previous lookup settle

        # collision guard: re-entering the same RUT won't re-fire — nudge first.
        if self._rutval() == k:
            r.click(); r.fill(""); r.press_sequentially("11111111", delay=25)
            self.page.mouse.click(self.bx, self.by)
            time.sleep(0.6)

        # verify-retry: characters can drop if the page is mid-update.
        for _ in range(3):
            self._clear_out()
            r.click(); r.fill("")
            r.press_sequentially(k, delay=55)    # real keystrokes, human pace
            time.sleep(0.15)
            if self._rutval() == k:
                break
            time.sleep(0.4)
        else:
            return {"email": "", "celular": "", "status": "typefail"}

        self.page.mouse.click(self.bx, self.by)  # click away -> fires the lookup
        end = time.time() + WAIT
        while time.time() < end:
            v = self._fields()
            if v["e"].strip() or v["c"].strip():
                return {"email": v["e"].strip(), "celular": v["c"].strip(), "status": "ok"}
            time.sleep(0.25)
        return {"email": "", "celular": "", "status": "nodata"}


def col_get(sh, rng):
    v = sh.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=rng).execute().get("values", [])
    return [(r[0] if r else "") for r in v]


def main():
    limit = start = None
    a = sys.argv[1:]
    if "--limit" in a: limit = int(a[a.index("--limit") + 1])
    if "--start" in a: start = int(a[a.index("--start") + 1])

    sh = gauth.sheets_client()
    got = sh.spreadsheets().values().batchGet(spreadsheetId=SHEET_ID, ranges=[
        f"{SRC_TAB}!{SRC_RUT_COL}{SRC_FIRST_ROW}:{SRC_RUT_COL}",
        f"{SRC_TAB}!{SRC_FLAG_COL}{SRC_FIRST_ROW}:{SRC_FLAG_COL}",
        f"{DEST_TAB}!A2:A"]).execute()["valueRanges"]
    ruts  = [(r[0] if r else "") for r in got[0].get("values", [])]
    flags = [(r[0] if r else "") for r in got[1].get("values", [])]
    flags += [""] * (len(ruts) - len(flags))
    dest_existing = {digits(r[0]) for r in got[2].get("values", []) if r}

    todo = []
    for i, rut in enumerate(ruts):
        row = i + SRC_FIRST_ROW
        if not rut.strip() or flags[i].strip():
            continue
        if start and row < start:
            continue
        todo.append((row, rut.strip()))
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} RUTs to check "
          f"(of {sum(1 for r in ruts if r.strip())} in {SRC_TAB}, "
          f"{sum(1 for f in flags if f.strip())} already flagged {SRC_FLAG_COL})")
    if not todo:
        return

    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        pages = [p for ctx in b.contexts for p in ctx.pages]
        page = next((p for p in pages if "Vehiculo1" in p.url), pages[-1])
        lk = Looker(page)
        seen, ok, miss, tf = set(), 0, 0, 0

        def mark(row):
            sh.spreadsheets().values().update(
                spreadsheetId=SHEET_ID, range=f"{SRC_TAB}!{SRC_FLAG_COL}{row}",
                valueInputOption="RAW", body={"values": [[FLAG]]}).execute()

        for n, (row, rut) in enumerate(todo, 1):
            k = digits(rut)
            if k in seen:                        # duplicate RUT within this run
                mark(row)
                print(f"[{n}/{len(todo)}] row{row} {rut:>13} -> DUP (already checked this run)")
                continue
            t = time.time()
            res = lk.lookup(rut)
            dt = round(time.time() - t, 1)
            if res["status"] == "typefail":
                tf += 1
                print(f"[{n}/{len(todo)}] row{row} {rut:>13} -> TYPEFAIL ({dt}s) [not flagged, will retry]")
                sys.stdout.flush()
                continue
            seen.add(k)
            found = bool(res["email"] or res["celular"])
            if found and k not in dest_existing:
                sh.spreadsheets().values().append(
                    spreadsheetId=SHEET_ID, range=f"{DEST_TAB}!A:C",
                    valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                    body={"values": [[rut, res["email"], res["celular"]]]}).execute()
                dest_existing.add(k)
            mark(row)                            # flag AFTER writing -> resumable
            ok += 1 if found else 0
            miss += 0 if found else 1
            tag = "OK    " if found else "NODATA"
            print(f"[{n}/{len(todo)}] row{row} {rut:>13} -> {tag} {res['email']:<32} {res['celular']} ({dt}s)")
            sys.stdout.flush()
            time.sleep(GAP)

            if n % 50 == 0:                       # session-health probe
                p = lk.lookup(CANARY_RUT)
                if not (p["email"] or p["celular"]):
                    print(f"SESSION-DEAD after {n} rows: canary RUT returned nothing. "
                          f"Stopping — re-login in the browser and re-run to resume.")
                    sys.stdout.flush()
                    break
        print(f"\ndone: {ok} with data (appended to {DEST_TAB}), {miss} no-data, {tf} typefail")
        b.close()


if __name__ == "__main__":
    main()
