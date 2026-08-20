# EXPERIMENTO SPECS — GOAL 1: THE BEST SPECS FOR *ONE* WORKER, BY THE NEW STANDARD
#
# The score is new records per minute without tripping (felipe/CLAUDE.md -> "The ultimate goal").
# It factors:
#
#     new records/min  =  opens/min  x  useful %
#
# SPECS move the first term. The JOB and the WINDOW move the second (a July sweep ran 53% useful,
# --fill runs ~95%). So specs are compared on OPENS/MIN here, deliberately.
#
# WARN: DO NOT COMPARE SPEC ARMS ON "NEW RECORDS". Each arm banks what it opens, so a later arm on
# the same courts finds less left to find and scores worse for a reason that has nothing to do with
# its specs. Depletion looks exactly like a slow configuration.
#
# A clean 2x2, --speed held at 1.0 throughout:
#
#     arm 1   --focus off   --duty off      the August spans, always-on hum
#     arm 2   --focus fast  --duty off      operator's p0-p25 band
#     arm 3   --focus off   --duty human    stillness, standard reading
#     arm 4   --focus fast  --duty human    NEVER RUN TOGETHER BEFORE
#
# WARN: --speed IS HELD AT 1.0 ON PURPOSE. --speed and --focus are two knobs on the same quantity
# (the reading times), and human_engine's own header says to leave one alone while the other works.
# Arm 1 of the rate test used --speed 0 and reached 6.5 opens/min per worker; that is a separate
# point on a different axis, not a fifth cell of this matrix.
#
# WARN: THE FOUR RUN IN PARALLEL, WHICH CONTROLS FOR THE SITE AND CONFOUNDS ON THE COURTS. All
# four meet identical site load and time of day -- worth a lot, since this project has attributed
# to specs what was really the hour. The cost is court density: four identical shards in the rate
# test produced 4.6 to 6.7 opens/min purely from which courts they drew. That is +/-20%, so trust a
# 50% effect and re-run with the ranges ROTATED before trusting a 20% one.
#
#   Score:  python scraper\expduty_score.py
#
param(
    [string] $Desde   = "01/07/2026",
    [string] $Hasta   = "31/07/2026",
    [double] $Minutes = 25,
    [int]    $BasePort = 9700,
    [int]    $Courts  = 230,
    [int]    $Rotate  = 0,        # shift the spec->court-range assignment, to cancel density
    [switch] $Force
)

$ErrorActionPreference = "Stop"
$scraper = Join-Path $PSScriptRoot "scraper"
$dataH   = Join-Path $PSScriptRoot "data\worker_h"
$py = "C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

$matrix = @(
    @{ focus = "off";  duty = "off"   },
    @{ focus = "fast"; duty = "off"   },
    @{ focus = "off";  duty = "human" },
    @{ focus = "fast"; duty = "human" }
)

$alive = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
           Where-Object { $_.CommandLine -match '(?<!\w)worker_[ah]\.py' })
if ($alive.Count -gt 0) {
    throw "$($alive.Count) worker process(es) already running (PID $($alive.ProcessId -join ', ')). Two fleets on one address is the one configuration measured to kill both."
}

$freeGB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
$needGB = [math]::Round($matrix.Count * 0.45 + 1.0, 1)
Write-Host "free RAM ${freeGB} GB, this matrix needs about ${needGB} GB"
if ($freeGB -lt $needGB -and -not $Force) {
    throw "not enough free RAM (${freeGB} GB free, ~${needGB} GB needed). A swapping machine is paced by its disk, not by its specs."
}

$old = @(Get-ChildItem (Join-Path $dataH "docs-s*.log") -ErrorAction SilentlyContinue)
if ($old.Count -gt 0) {
    $keep = Join-Path $PSScriptRoot "data\expspecs\prev-$(Get-Date -Format yyyyMMdd-HHmmss)"
    New-Item -ItemType Directory -Force -Path $keep | Out-Null
    $old | Move-Item -Destination $keep
    Write-Host "archived $($old.Count) log(s) -> $keep"
}
New-Item -ItemType Directory -Force -Path $dataH | Out-Null

$per = [math]::Ceiling($Courts / $matrix.Count)
Write-Host ""
Write-Host "SPECS MATRIX, $($matrix.Count) single workers in parallel, --speed 1.0, $Minutes min"
Write-Host ""
for ($i = 0; $i -lt $matrix.Count; $i++) {
    $spec = $matrix[$i]
    $r = ($i + $Rotate) % $matrix.Count           # which court range this spec draws
    $start = $r * $per
    $end   = [math]::Min($start + $per - 1, $Courts - 1)
    $port  = $BasePort + $i + 1
    $log   = Join-Path $dataH ("docs-s{0}.log" -f ($i + 1))
    $wargs = @(
        "-u", "worker_h.py",
        "--launch", "--port", $port,
        "--start", $start, "--end", $end,
        "--desde", $Desde, "--hasta", $Hasta,
        "--speed", "1.0",
        "--focus", $spec.focus, "--duty", $spec.duty,
        "--gate-release", "form",
        "--max-minutes", $Minutes
    )
    $proc = Start-Process -FilePath $py -ArgumentList $wargs -WorkingDirectory $scraper `
                          -RedirectStandardOutput $log `
                          -RedirectStandardError (Join-Path $dataH ("docs-s{0}.err" -f ($i + 1))) `
                          -WindowStyle Hidden -PassThru
    Write-Host ("  s{0}  focus={1,-4} duty={2,-5}  courts {3}-{4}  port {5}  PID {6}" -f `
                ($i + 1), $spec.focus, $spec.duty, $start, $end, $port, $proc.Id)
    Start-Sleep -Seconds 8
}
Write-Host ""
Write-Host "shard N maps to matrix row N. Score with: python scraper\expduty_score.py"
