# EXPERIMENTO FLEET — HOW MANY WORKERS CAN THIS ADDRESS CARRY? (GOAL 2)
#
# Launch N worker H sweeps at a fixed --speed, disjoint court ranges, one address. The score is
# aggregate new records/min without tripping (felipe/CLAUDE.md -> "The ultimate goal").
#
# WARN: FLEET SIZE IS THE RATE CONTROL NOW, WHICH IS WHY THIS SCRIPT EXISTS. --speed only zeroes
# READING time, and the engine has grown motor work no speed setting removes: on 2026-08-19 four
# workers at --speed 0 produced 26 req/min against the 56 the same flag produced on 08-17, and ran
# 25 min with zero trouble. --speed now spans about 13% of the rate; worker count spans all of it.
#
# WARN: THE HISTORICAL WALL NUMBERS ARE PROPERTIES OF A BUILD, NOT OF THE SITE. "56 kills, 23 is
# safe" was measured on the 08-17 engine and does not transfer. Re-measure before designing around
# it. This script was originally written for a fixed-aggregate session-count test (4x14 vs 8x7)
# that could not be run for exactly this reason -- arm 1 refused to reproduce the control, which is
# what a validity check is for.
#
# The ladder, each rung 25 min, stopping at the first rung that shows trouble:
#
#     4 workers   ~26 req/min   measured clean 2026-08-19
#     8 workers   ~52 req/min   <- next
#    12 workers   ~78 req/min   only if 8 is clean, and only with the RAM for it
#
# WARN: EVERY RUNG NEEDS ITS OWN RAM CHECK, AND THE GUARD BELOW REFUSES RATHER THAN SWAP. A
# swapping machine paces its workers by the disk, so the arm measures this PC and not the site --
# and it does it while producing a perfectly plausible number.
#
#   Rate:   python scraper\rate_watch.py --mins 10
#   Score:  python scraper\expduty_score.py
#
param(
    [Parameter(Mandatory=$true)][int]    $Workers,
    [Parameter(Mandatory=$true)][double] $Speed,
    [Parameter(Mandatory=$true)][string] $Arm,
    [string] $Desde   = "01/07/2026",
    [string] $Hasta   = "31/07/2026",
    [double] $Minutes = 25,
    [int]    $BasePort = 9600,
    [int]    $Courts  = 230,
    [switch] $Force
)

$ErrorActionPreference = "Stop"
$scraper = Join-Path $PSScriptRoot "scraper"
$dataH   = Join-Path $PSScriptRoot "data\worker_h"
$py = "C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

# ⚠️ ONE FLEET AT A TIME. Match the worker, not its ingest: '*worker_h.py*' also matches
# 'ingest_worker_h.py', which once made a launcher refuse to start over a correct detached ingest.
$alive = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -match '(?<!\w)worker_[ah]\.py' })
if ($alive.Count -gt 0) {
    throw "$($alive.Count) worker process(es) already running (PID $($alive.ProcessId -join ', ')). Two fleets on one address is the one configuration measured to kill both."
}

# ⚠️ MEMORY IS A CONFOUND, NOT AN INCONVENIENCE. Each arm is DEFINED by its per-worker request
# rate. If the machine swaps, the workers are paced by the disk instead of by --speed, and the
# experiment measures this PC rather than the site. Refuse rather than produce a clean-looking
# number that means nothing.
$freeGB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
$needGB = [math]::Round($Workers * 0.45 + 1.0, 1)
Write-Host "free RAM ${freeGB} GB, this arm needs about ${needGB} GB for $Workers browser(s)"
if ($freeGB -lt $needGB -and -not $Force) {
    throw "not enough free RAM (${freeGB} GB free, ~${needGB} GB needed). Close other browsers, or pass -Force to measure the machine instead of the site."
}

# Archive the previous arm's logs so rate_watch sees THIS arm only. It reads every
# data\worker_h\docs-s*.log, and a finished arm left in place is counted as current traffic.
$old = @(Get-ChildItem (Join-Path $dataH "docs-s*.log") -ErrorAction SilentlyContinue)
if ($old.Count -gt 0) {
    $keep = Join-Path $PSScriptRoot "data\expB\prev-$(Get-Date -Format yyyyMMdd-HHmmss)"
    New-Item -ItemType Directory -Force -Path $keep | Out-Null
    $old | Move-Item -Destination $keep
    Write-Host "archived $($old.Count) log(s) from the previous arm -> $keep"
}
New-Item -ItemType Directory -Force -Path $dataH | Out-Null

$per = [math]::Ceiling($Courts / $Workers)
Write-Host ""
Write-Host "ARM '$Arm': $Workers worker(s), --speed $Speed, --duty off, $Desde .. $Hasta, $Minutes min cap"
Write-Host ""
for ($i = 1; $i -le $Workers; $i++) {
    $start = ($i - 1) * $per
    if ($start -ge $Courts) { Write-Host "  shard $i has no courts"; continue }
    $end  = [math]::Min($start + $per - 1, $Courts - 1)
    $port = $BasePort + $i
    $log  = Join-Path $dataH "docs-s$i.log"
    $wargs = @(
        "-u", "worker_h.py",
        "--launch", "--port", $port,
        "--start", $start, "--end", $end,
        "--desde", $Desde, "--hasta", $Hasta,
        "--speed", $Speed,
        "--duty", "off", "--focus", "off",
        "--gate-release", "form",
        "--max-minutes", $Minutes
    )
    $proc = Start-Process -FilePath $py -ArgumentList $wargs -WorkingDirectory $scraper `
                          -RedirectStandardOutput $log `
                          -RedirectStandardError (Join-Path $dataH "docs-s$i.err") `
                          -WindowStyle Hidden -PassThru
    Write-Host ("  shard {0}/{1}  courts {2}-{3}  port {4}  PID {5}" -f $i, $Workers, $start, $end, $port, $proc.Id)
    Start-Sleep -Seconds 8
}
Write-Host ""
Write-Host "arm '$Arm' launched. Arrivals serialise on the entry gate, so give it a few minutes"
Write-Host "before reading a rate: python scraper\rate_watch.py --mins 10"
