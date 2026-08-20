# EXPERIMENTO DUTY — WHAT DOES THE DUTY CYCLE ACTUALLY BUY US?
#
# The duty cycle (going completely still ~3x/min, like the recorded operator) costs roughly HALF
# the throughput. That cost is measured. The benefit has never been measured at all: every
# validation of it was a comparison against a recording, and a recording cannot answer whether a
# fleet gets blocked. See felipe/CLAUDE.md -> "The ultimate goal".
#
# ⚠️ THE METRIC IS THE BENCHMARK, NOT A SIMILARITY SCORE: causas delivered per hour, and whether
# the arm tripped. Not "how close is the pointer to the human's".
#
#     arm duty-off     8 workers, --duty off,   --speed 0, --focus off
#     arm duty-human   8 workers, --duty human, --speed 0, --focus off
#
# EVERYTHING except --duty is identical, so the difference in request rate IS the effect of the
# duty cycle rather than a confound.
#
#   neither trips     -> duty-off wins outright: same survival, ~2x the causas. Remove the spec.
#   only duty-off trips -> stillness buys survival; compare causas DELIVERED, which is the score.
#   both trip         -> compare causas delivered before the trip, and the rate each tripped at.
#
# ⚠️ WHY 8 WORKERS AND NOT 4. On today's build four workers at top speed produce only ~27 req/min
# and ran 19+ min clean, so a 4-worker arm cannot reach the wall no matter how it is paced --
# `--speed` zeroes reading time only, and the engine's motor work sets a floor. Finding out what
# duty is worth requires running where trouble actually happens.
#
# ⚠️ DO NOT "MATCH THE AGGREGATE RATE" BETWEEN THESE ARMS. That was the instinct, and it is wrong
# here: holding the rate equal would need 8 workers against 16, and it would also destroy the thing
# being measured. Duty's whole effect is that it LOWERS the rate for a given fleet. The question is
# not "at equal rate, is stillness safer" but "for one machine and one address, which configuration
# delivers more records without tripping" -- and that is answered by running both as they ship.
#
#   Rate:   python scraper\rate_watch.py --mins 10
#   Score:  python scraper\expduty_score.py
#
param(
    [Parameter(Mandatory=$true)][ValidateSet("off","human")][string] $Duty,
    [int]    $Workers = 8,
    [string] $Desde   = "01/07/2026",
    [string] $Hasta   = "31/07/2026",
    [double] $Minutes = 60,
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

# ⚠️ MEMORY IS A CONFOUND, NOT AN INCONVENIENCE. If the machine swaps, the workers are paced by the
# disk and the arm measures this PC instead of the site -- and the two arms would be paced
# differently, because they hold different numbers of live pages. Refuse rather than produce a
# clean-looking number that means nothing.
$freeGB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
$needGB = [math]::Round($Workers * 0.45 + 1.0, 1)
Write-Host "free RAM ${freeGB} GB, this arm needs about ${needGB} GB for $Workers browser(s)"
if ($freeGB -lt $needGB -and -not $Force) {
    throw "not enough free RAM (${freeGB} GB free, ~${needGB} GB needed). Close other browsers, or pass -Force to measure the machine instead of the site."
}

# Archive the previous arm so rate_watch and the scorer see THIS arm only.
$old = @(Get-ChildItem (Join-Path $dataH "docs-s*.log") -ErrorAction SilentlyContinue)
if ($old.Count -gt 0) {
    $keep = Join-Path $PSScriptRoot "data\expduty\prev-$(Get-Date -Format yyyyMMdd-HHmmss)"
    New-Item -ItemType Directory -Force -Path $keep | Out-Null
    $old | Move-Item -Destination $keep
    Write-Host "archived $($old.Count) log(s) from the previous arm -> $keep"
}
New-Item -ItemType Directory -Force -Path $dataH | Out-Null

$per = [math]::Ceiling($Courts / $Workers)
Write-Host ""
Write-Host "ARM 'duty-$Duty': $Workers workers, --duty $Duty, --speed 0, --focus off, $Minutes min cap"
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
        "--speed", 0,
        "--duty", $Duty, "--focus", "off",
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
Write-Host "arm 'duty-$Duty' launched. Score it when it ends:  python scraper\expduty_score.py"
