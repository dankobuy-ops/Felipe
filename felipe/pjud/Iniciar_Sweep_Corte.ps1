# Sweep ONE Corte de Apelaciones over ONE window with N detached worker A's — DISCOVERY, so that
# a doc pass has something to open.
#
# ⚠️ WHY THIS EXISTS SEPARATELY FROM Iniciar_Docs_Santiago.ps1. `--fill --docs-c2` re-opens causas
# the DATABASE already holds; it cannot discover. Pointed at a window nothing was ever swept for,
# it reports `nothing-searched` and looks exactly like a refusal (measured 2026-08-18). The corpus
# stops at 07/08/2026 because that is where sweeping stopped — so bringing a month "up to today"
# is TWO passes: this one to find the causas, then the doc pass to fetch their PDFs.
#
# ⚠️ THAT IS TWO OPENS PER NEW CAUSA, and a causa open is the scarcest thing this project spends.
# It is the price of worker A being metadata-only by design (redefined 2026-08-14 precisely to
# stay clear of the document endpoint). Worth it for a short catch-up window; not worth it as a
# standing pattern — if whole-corte catch-ups become routine, the answer is a sweep that takes
# documents in the same open, not this run twice.
#
# ⚠️ NEVER RUN THIS WHILE A DOC FLEET IS UP. The binding limit is the AGGREGATE REQUEST RATE PER
# ADDRESS, and two fleets is the one configuration measured to kill both. The guard below refuses.
#
#   Watch:  Get-Content <data>\worker_a1\sweep.log -Wait -Tail 20
#   Rate:   python scraper\rate_watch.py
#   Bank:   python scraper\ingest_worker_a.py --slot 1   (per slot)

param(
    [string] $Corte    = "C.A. de Santiago",
    [string] $Desde    = "01/08/2026",
    [string] $Hasta    = (Get-Date -Format "dd\/MM\/yyyy"),   # escaped: es-CL renders "/" as "-"
    [int]    $Workers  = 4,
    [double] $Minutes  = 180,
    [int]    $BasePort = 9800,
    # ⚠️ MATCH THE FILTER THE CORPUS WAS BUILT WITH. worker_a.py's own default is EMPTY (store
    # every procedimiento), while Iniciar_Worker_A.ps1 and ingest_worker_a both use
    # 'obligaci.*dar' — so a sweep launched without this would quietly widen the corpus's
    # definition for one window only, and nothing downstream would flag the inconsistency.
    [string] $OnlyProc = "obligaci.*dar",
    [switch] $DryList
)

$ErrorActionPreference = "Stop"
$scraper = Join-Path $PSScriptRoot "scraper"
$py = "C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

$d0 = [datetime]::ParseExact($Desde, "dd/MM/yyyy", $null)
$d1 = [datetime]::ParseExact($Hasta, "dd/MM/yyyy", $null)
if ($d1 -lt $d0)                  { throw "-Hasta is before -Desde" }
if (($d1 - $d0).TotalDays -gt 31) { throw "the OJV refuses a range longer than one month: $Desde .. $Hasta is $([int]($d1-$d0).TotalDays) days." }
if ($d1 -gt (Get-Date).Date)      { throw "-Hasta is in the future; the datepicker disables every day after today" }

# How many courts this corte has, and what is already banked for the window — so "it found
# nothing" can be told apart from "there was nothing to find".
$info = & $py -c @"
import sys; sys.path.insert(0, r'$scraper')
import psycopg2, dbstore
iso = lambda v: '-'.join(reversed(v.split('/')))
cn = psycopg2.connect(**dbstore._conn_kwargs())
k = cn.cursor()
k.execute("select count(*) from tribunales where corte = %s", ('''$Corte''',))
courts = k.fetchone()[0]
k.execute("""select count(*) from causas c join tribunales t on t.id = c.tribunal_id
             where t.corte = %s and c.f_ingreso between %s and %s""",
          ('''$Corte''', iso('$Desde'), iso('$Hasta')))
have = k.fetchone()[0]
print(f'{courts} {have}')
"@
if ($LASTEXITCODE -ne 0) { throw "could not read the corte from Neon" }
$p = $info.Trim().Split(" ")
Write-Host "'$Corte': $($p[0]) tribunales; Neon already holds $($p[1]) causa(s) for $Desde .. $Hasta"
# ⚠️ NO BACKTICKS IN A DOUBLE-QUOTED POWERSHELL STRING. Backtick is the escape character, so a
# markdown-style `select ...` swallows the following letter and derails the parse for the rest of
# the file — the reported error lands 40 lines later, on a statement that is perfectly fine.
if ([int]$p[0] -eq 0) { throw 'no tribunal carries that corte -- check: select distinct corte from tribunales' }
if ($DryList) { return }

# ⚠️ ONE FLEET AT A TIME, ON EITHER WORKER. Match the worker, not its ingest: -like '*worker_a.py*'
# would also match 'ingest_worker_a.py', which is how the doc launcher once refused to start
# because a perfectly correct detached ingest was running.
$alive = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -match '(?<!\w)worker_[ah]\.py' })
if ($alive.Count -gt 0) {
    throw "$($alive.Count) worker process(es) already running (PID $($alive.ProcessId -join ', ')). Two fleets on one address is the one configuration measured to kill both — stop them first."
}

# ⚠️ --start/--end index the FILTERED list once --corte is given, so the slices are over this
# corte's courts, not the country's. Disjoint by construction.
$n = [int]$p[0]
$per = [math]::Ceiling($n / $Workers)
for ($i = 1; $i -le $Workers; $i++) {
    $start = ($i - 1) * $per
    if ($start -ge $n) { Write-Host "  shard $i has no courts — $n courts over $Workers workers"; continue }
    $end = [math]::Min($start + $per - 1, $n - 1)
    $port = $BasePort + $i
    $data = Join-Path $PSScriptRoot "data\worker_a$i"
    New-Item -ItemType Directory -Force -Path $data | Out-Null
    # ⚠️ Quote every value containing a space INSIDE the string: Start-Process joins -ArgumentList
    # with spaces, so a bare corte name arrives as three arguments and argparse dies into stderr.
    $args = @(
        "-u", "worker_a.py",
        "--launch-chrome", "--port", $port,
        "--corte", "`"$Corte`"",
        "--start", $start, "--end", $end,
        "--desde", $Desde, "--hasta", $Hasta,
        "--slot", $i,
        "--only-proc", "`"$OnlyProc`"",
        "--max-minutes", $Minutes,
        "--shots", "`"$(Join-Path $data 'shots')`""
    )
    $log = Join-Path $data "sweep.log"
    $proc = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $scraper `
                          -RedirectStandardOutput $log -RedirectStandardError (Join-Path $data "sweep.err") `
                          -WindowStyle Hidden -PassThru
    $proc.Id | Out-File (Join-Path $data "sweep.pid") -Encoding ascii
    Write-Host ("  shard {0}/{1}  courts {2}-{3}  port {4}  PID {5}" -f $i, $Workers, $start, $end, $port, $proc.Id)
    Start-Sleep -Seconds 8
}
Write-Host ""
Write-Host "sweeping '$Corte', $Desde .. $Hasta. When it finishes: ingest, THEN run the doc pass."
