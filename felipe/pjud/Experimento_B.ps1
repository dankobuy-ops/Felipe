# EXPERIMENTO B — DOES SESSION COUNT MATTER AT A FIXED AGGREGATE RATE?
#
# The 2026-08-17 test settled that the RATE kills: four workers at --speed 0 produced ~56 POST/min
# and were all dead by minute 5, while the same four at --speed 1.0 produced ~23 and two ran the
# full hour. It is written up as "IT IS THE AGGREGATE RATE PER ADDRESS, NOT THE SESSION COUNT".
#
# ⚠️ THAT TITLE IS STRONGER THAN ITS EVIDENCE. Session count was held at FOUR in both arms; only
# the pace moved. It proves rate matters at a fixed session count. It never tested session count
# at a fixed rate, so "session count is close to free" rests on a separate low-rate run (four
# sessions, one hour, ~23/min) where nothing was near the wall anyway.
#
# This script runs the missing cell. Same aggregate, different number of sessions:
#
#     arm 4x14   4 workers, --speed 0     ~56 POST/min aggregate   (replicates the known kill)
#     arm 8x7    8 workers, --speed CAL   ~56 POST/min aggregate   (half the rate per session)
#
#   both die      -> the wall is the ADDRESS's aggregate; sessions do not shield you, and 23/min
#                    is a real ceiling until the IP count goes up.
#   8x7 survives  -> the wall is PER SESSION; the fleet can be widened to raise total throughput,
#                    and every "add workers, do not accelerate them" note gets a number behind it.
#
# ⚠️ ARM 1 IS ALSO THE VALIDITY CHECK. If 4 workers at --speed 0 do NOT die, the setup has not
# reproduced the control and arm 2 is uninterpretable — stop rather than launch it. The code has
# changed a great deal since 08-17 (engine collapse, duty cycle, focus bands), and a rate measured
# under one build is not a rate under another.
#
# ⚠️ --duty off AND --focus off IN BOTH ARMS, deliberately. They are our best specs and they are
# not what is being tested: duty roughly halves the request rate, which is the very quantity being
# held constant. This experiment reproduces the 08-17 configuration, where the ONLY difference
# between arms was --speed.
#
# ⚠️ A SWEEP, NOT --docs-c2. The doc pass makes ~2.7x the requests per open, so it cannot be
# compared against a control measured on a sweep. Same job in both arms, and the same job as the
# run being replicated.
#
#   Rate:   python scraper\rate_watch.py --mins 10
#   Watch:  Get-Content data\worker_h\docs-s1.log -Wait -Tail 20
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
