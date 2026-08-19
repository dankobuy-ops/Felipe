# Six worker H's, DETACHED, fetching the PDF behind every cuaderno-2 historia row for the
# tribunales of one Corte de Apelaciones (default: Santiago).
#
# ⚠️ WHY DETACHED. A long run started as a background task from the agent harness is KILLED after
# roughly half an hour — that is what actually happened to the census that appeared to "stall
# overnight" on 2026-08-06. Start-Process reparents each worker, and progress is judged by
# whether its LOG FILE ADVANCES, never by whether a wrapper is still attached.
#
# ⚠️ ONE MONTH PER LAUNCH, BECAUSE THE OJV REFUSES A LONGER RANGE ("El rango de fecha no puede ser
# superior a un Mes") and the refusal arrives as a sweet-alert that reads like an empty result.
# A fill run still finds its causa by SEARCHING the tribunal over a date window and clicking the
# row, so a causa outside the window can never be reached however much it owes. Santiago spans
# 19/06 to 07/08, which is therefore THREE launches, not one.
#
# ⚠️ WHAT THIS COSTS, SAID BEFORE IT COSTS IT. A metadata open is 2 requests (open + book switch).
# This is 2 + ~3.5 documents = ~5.5, measured over 23,286 banked cuaderno-2 rows: 99.8% of them
# carry a document form, at 3.5 per causa. The one law this project has measured is that the
# binding limit is the AGGREGATE REQUEST RATE PER ADDRESS — four workers at ~56 POST/min were all
# dead by minute 5; the same four at ~23/min ran the full hour and produced ten times the output.
# So SIX workers here make roughly the request rate of sixteen doing metadata. Watch it with
# rate_watch.py, and if it is too much, TAKE WORKERS OFF or raise -Speed. Never speed them up:
# top speed halves the pointer rate (6-9 events/s against 15-20) and multiplies the request rate,
# which is both less human and less productive.
#
# ⚠️ AND IT AIMS AT THE ENDPOINT WORKER A WAS REDEFINED TO AVOID. docuN.php / docuS.php is the
# document endpoint that refused 16 and 19 times on 2026-08-13, and on 2026-08-14 worker A was
# rebuilt to take metadata only precisely so it would stay clear of it. This job cannot: the
# documents ARE the job. Expect refusals to be the first thing that shows up, and read them as a
# rate verdict on the address, not as a broken worker.
#
#   Watch:   Get-Content <data>\worker_h\docs-s1.log -Wait -Tail 20
#   Rate:    python scraper\rate_watch.py
#   Stop:    Get-Content <data>\worker_h\docs.pids | ForEach-Object { Stop-Process -Id $_ }
#   Bank it: python scraper\ingest_worker_h.py      (safe at any time, including mid-run)
#
# ⚠️ THE INGEST IS ITSELF A LONG RUN NOW — DETACH IT TOO. At ~3.5 documents per causa the Drive
# upload is thousands of files, not the dozens worker A's ebook pass produced. One run was killed
# with 2,406 uploads in flight, leaving the PDFs partly in Drive and the `documentos` rows not
# written at all, because the upsert comes after the upload. Re-running is cheap and resumes:
# upload_pdfs_parallel consults the Drive cache first and skips every name already there
# (measured: "1036 already in Drive; uploading 1664 new").

param(
    [int]    $Workers  = 6,
    [string] $Desde    = "01/07/2026",
    [string] $Hasta    = "31/07/2026",
    [string] $Corte    = "C.A. de Santiago",
    # 1.0 is exactly the pace of the recorded operator. It is the FAITHFUL setting, not the slow
    # one — see the note above about what speed spends.
    [double] $Speed    = 1.0,
    [double] $Minutes  = 240,
    [int]    $BasePort = 9700,
    # ⚠️ THE SMOKE TEST GOES THROUGH THIS SCRIPT, not around it. The first attempt at one was
    # launched with a hand-built Start-Process and died instantly on `unrecognized arguments: de
    # Santiago` — PowerShell splits an -ArgumentList element on its spaces unless the quotes are
    # part of the string. Ten minutes were spent watching a log file belonging to a process that
    # had already exited. Size the smoke test to the question, and run it down the path you are
    # about to trust.
    [int]    $MaxCausas = 0,               # per worker; 0 = the whole shard
    [switch] $DryList                      # report the work-list and exit, launching nothing
)

$ErrorActionPreference = "Stop"
$scraper = Join-Path $PSScriptRoot "scraper"
$data    = Join-Path $PSScriptRoot "data\worker_h"
New-Item -ItemType Directory -Force -Path (Join-Path $data "pdfs") | Out-Null

$py = "C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

# ⚠️ REFUSE A WINDOW LONGER THAN A MONTH HERE, not six browsers later. The worker checks too, but
# by then six Chromes have arrived at the site to be told the same thing.
$d0 = [datetime]::ParseExact($Desde, "dd/MM/yyyy", $null)
$d1 = [datetime]::ParseExact($Hasta, "dd/MM/yyyy", $null)
if ($d1 -lt $d0)                    { throw "-Hasta is before -Desde" }
if (($d1 - $d0).TotalDays -gt 31)   { throw "the OJV refuses a range longer than one month: $Desde .. $Hasta is $([int]($d1-$d0).TotalDays) days. Launch one month at a time." }
if ($d1 -gt (Get-Date).Date)        { throw "-Hasta is in the future; the datepicker disables every day after today" }

# What is actually owed, asked of the database rather than assumed. A work-list of zero is not a
# success and not a block — it is either finished or a corte name that does not match.
$listed = & $py -c @"
import sys; sys.path.insert(0, r'$scraper')
import worker_h as W
iso = lambda v: '-'.join(reversed(v.split('/')))
todo, n = W.fill_targets(iso('$Desde'), iso('$Hasta'), corte='''$Corte''', mode='docs-c2')
print(f'{n} {len(todo)}')
"@
if ($LASTEXITCODE -ne 0) { throw "could not read the work-list from Neon" }
$parts = $listed.Trim().Split(" ")
Write-Host "work-list: $($parts[0]) causa(s) owe cuaderno-2 documents in '$Corte' for $Desde .. $Hasta, across $($parts[1]) tribunal(es)"
if ([int]$parts[0] -eq 0) {
    Write-Host "nothing owed for this window — either it is finished, or that corte name does not match tribunales.corte exactly."
    return
}
Write-Host ("expect roughly {0:N0} document fetches (3.5 per causa, measured)" -f ([int]$parts[0] * 3.5))
if ($DryList) { return }

# ⚠️ REFUSE TO DOUBLE-START. Two fleets on one address is the one thing measured to kill a fleet,
# and the second one would be invisible in the first one's logs.
# ⚠️ AND MATCH THE WORKER, NOT ITS INGEST. `-like "*worker_h.py*"` also matches
# `ingest_worker_h.py`, so a perfectly correct detached ingest blocked the next month's launch.
# The lookbehind refuses a preceding word character, which is what separates "worker_h.py" from
# "…_worker_h.py". It failed SAFE — refusing to launch, not launching twice — which is the right
# direction for a guard to be wrong in, but it was still wrong.
$alive = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -match '(?<!\w)worker_h\.py' })
if ($alive.Count -gt 0) {
    throw "$($alive.Count) worker_h process(es) already running (PID $($alive.ProcessId -join ', ')). Stop them first — a second fleet on this address doubles the aggregate rate, which is the one thing measured to kill a fleet."
}

$pids = @()
for ($i = 1; $i -le $Workers; $i++) {
    $port = $BasePort + $i
    # ⚠️ ONE PROFILE DIR PER PORT, and --launch derives it from the port for exactly that reason.
    # Chrome treats --user-data-dir as a singleton and the clash does NOT fail loudly: a browser
    # came up, entered, searched, and was closed under us 75 s later.
    # ⚠️ QUOTE ANY VALUE THAT CONTAINS A SPACE, INSIDE THE STRING. Start-Process joins
    # -ArgumentList with spaces and hands the result to the process, so a bare "C.A. de Santiago"
    # arrives as THREE arguments and argparse dies with `unrecognized arguments: de Santiago` —
    # instantly, into stderr, leaving an empty stdout log that looks exactly like a worker still
    # starting up. The quotes have to be part of the value.
    $args = @(
        "-u", "worker_h.py",
        "--launch", "--port", $port,
        "--fill", "--docs-c2", "--corte", "`"$Corte`"",
        "--shard", $i, "--of", $Workers,
        "--desde", $Desde, "--hasta", $Hasta,
        "--speed", $Speed,
        "--max-minutes", $Minutes,
        # The arrival gate serialises fresh browsers so six of them never land on pjud.cl in the
        # same instant. Released once the form is built — building a form is not an arrival.
        "--gate", "file", "--gate-release", "form",
        "--window", "1440x900",
        "--max-pages", "10", "--max-recover", "3", "--measure",
        "--shots", "`"$(Join-Path $data 'shots')`""
    )
    if ($MaxCausas -gt 0) { $args += @("--max-causas", $MaxCausas) }
    $log = Join-Path $data "docs-s$i.log"
    $err = Join-Path $data "docs-s$i.err"
    $proc = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $scraper `
                          -RedirectStandardOutput $log -RedirectStandardError $err `
                          -WindowStyle Hidden -PassThru
    $pids += $proc.Id
    Write-Host ("  shard {0}/{1}  port {2}  PID {3}  -> {4}" -f $i, $Workers, $port, $proc.Id, (Split-Path $log -Leaf))
    # Stagger the launches. The entry gate serialises the arrival itself, but six Chromes starting
    # in the same second contend for the machine, not for the site.
    Start-Sleep -Seconds 6
}
$pids | Out-File (Join-Path $data "docs.pids") -Encoding ascii

Write-Host ""
Write-Host "$Workers worker(s) detached, $Desde .. $Hasta, '$Corte', reading x$Speed, lifespan $Minutes min"
Write-Host "  follow : Get-Content `"$(Join-Path $data 'docs-s1.log')`" -Wait -Tail 20"
Write-Host "  rate   : $py `"$(Join-Path $scraper 'rate_watch.py')`""
Write-Host "  bank   : $py `"$(Join-Path $scraper 'ingest_worker_h.py')`""
Write-Host "  stop   : Get-Content `"$(Join-Path $data 'docs.pids')`" | ForEach-Object { Stop-Process -Id `$_ }"
