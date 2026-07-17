# HDI-Ruts-Scraper

Pulls client **email + phone by RUT** from HDI's broker cotizador
(`venta.hdi.cl/amsa/cotizador-web` → *Cotizadores → Vehículo*) and records them in
a Google Sheet. Resumable and safe to stop/restart.

## Data flow
| Step | Where |
|---|---|
| **RUT source** | `Patentes` tab, column **B** (`rut_propietario`) |
| **Dedupe / "already done"** | `Patentes` tab, column **M** ("HDI" flag). A row is *to-do* only if its flag is empty. Every checked RUT (with data **or** not) gets the flag set — so nothing is ever re-scraped. |
| **Output** | `HDI` tab (**A**=Rut, **B**=Correo, **C**=Teléfono) — **appended**, email rows only. A RUT already in the HDI tab is not appended twice. |

So each run only processes Patentes RUTs whose **M** flag is blank (i.e. newly added).

## Files
| File | What it is |
|---|---|
| `hdi_ruts_scraper.py` | The scraper. Config block at top. |
| `cdp.py` | Launches / drives the monitored Chrome (`launch`, `pages`, `shot`, `js`). |

## Requirements
Runs on the **`felipe/scraper`** venv (`playwright`/`patchright`,
`google-api-python-client`) and reuses its Google login (`gauth.py` + `token.json`,
account **danko.buy@gmail.com**). Chrome must be installed.

## How to run
```powershell
$py = "C:\Claude\felipe\scraper\.venv\Scripts\python.exe"
cd  "C:\Claude\cias\HDI-Ruts-Scraper"

# 1) Open the monitored Chrome
& $py cdp.py launch

# 2) In THAT window: log in to the HDI broker portal, then open
#    Cotizadores -> Vehiculo so the "Rut del Cliente" form is showing.

# 3) Run — processes every un-flagged Patentes RUT, resumes automatically
& $py hdi_ruts_scraper.py
& $py hdi_ruts_scraper.py --limit 10     # only first 10 to-do rows (test)
& $py hdi_ruts_scraper.py --start 800    # skip Patentes rows above 800
```
Each result is written immediately (flag set only *after* a successful lookup), so
you can **stop or kill it any time** and re-run — flagged rows are skipped.

## Configuring the layout  ← edit after you change the sheet
`CONFIG` block at the top of `hdi_ruts_scraper.py`:
```python
SHEET_ID      = "1HDrOxg…UM9g"
SRC_TAB       = "Patentes"    # tab holding the RUTs
SRC_RUT_COL   = "B"           # column with the RUTs
SRC_FLAG_COL  = "M"           # per-company "checked" flag column (HDI)
SRC_FIRST_ROW = 2             # first data row
DEST_TAB      = "HDI"         # output tab: A=Rut, B=Correo, C=Telefono
CANARY_RUT    = "7620655-4"   # a RUT known to HAVE data (session health probe)
```
> If you clear a RUT's **M** flag, that RUT will be re-checked. To force a full
> re-scrape, clear all of column M (keep the header).

## How the lookup works (hard-won details)
- Types the RUT with **real keystrokes**, not `fill()` — `fill()` doesn't fire the
  site's lookup.
- Blurs by **clicking empty space**, never Tab and never the **Limpiar** button
  (Limpiar reloads dropdowns that jam the ASP.NET queue → 20–60 s lookups).
- Reads the **email/celular fields** as ground truth (CDP network sniffing is
  unreliable). Empty after ~5 s ⇒ no contact on file.
- **Collision guard** (same RUT won't re-fire) + **verify-retry** (retypes dropped
  characters) + **health probe** every 50 rows (stops on session expiry).

## Tuning (env vars, optional)
`CDP_PORT` (9333), `LOOKUP_WAIT` (5 s), `LOOKUP_GAP` (0.4 s), `CDP_PROFILE`, `CDP_CHROME`.

---
_Sibling scraper for the Renta company (same engine, `Patentes!N` flag → `Renta`
tab) lives in `../Renta-Ruts-Scraper` once its portal lookup is built._
