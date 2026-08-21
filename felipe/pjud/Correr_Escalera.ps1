# CORRER LA ESCALERA — 1 worker, then 4, then 8, unattended, one label per ladder.
#
# The ladder is always 1 -> 4 -> 8. The baseline is a SINGLE worker, and every rung after it is
# compared against that, on the same code, the same window, the same address and the same
# COURTS PER WORKER.
#
# WARN: PER-WORKER WORK IS HELD CONSTANT, NOT TOTAL WORK. This is the whole reason the first
# ladder was not comparable: rung 1 swept 230 courts, rung 2 got 58 each and rung 3 got 29 each,
# so each rung ran a different LENGTH for a reason that had nothing to do with fleet size. A fixed
# corpus divided N ways gives each worker 1/N the runtime -- at ~1.65 min/court a 58-court shard
# exhausts in ~95 min and a 29-court shard in ~48. Give every worker the same 29 courts and every
# rung runs the same ~48 min with fleet size as the only variable.
#
# WARN: A FLEET DOES NOT END, IT DISASSEMBLES. Shards exhaust at different times, so a rung left
# running becomes an (N-1)-worker rung, then (N-2), while still being labelled N -- and the final
# averages silently mix every regime. Each rung here STOPS AT THE FIRST `DONE in`, so every number
# comes from the all-N-live window.
#
# WARN: DO NOT KILL -- OR REFUSE -- A RUNG ON FREE RAM. An 8-worker arm was killed on 2026-08-20
# for sitting at 0.54 GB free, and it was HEALTHY -- 6.85-9.73 s per open, better than the
# 4-worker rung. Swapping shows up as workers getting SLOWER. Free RAM is a proxy;
# seconds-per-open is the harm, and it is the only thing that should stop a rung.
# So the check below WARNS and runs. It refuses only under -FloorGB, where Chrome cannot start
# at all, and it writes the free figure to ladder.log so the rung can be read with it in view.
#
#   .\Correr_Escalera.ps1 -Label "con-tab-fix"
#   .\Correr_Escalera.ps1 -Label "sin-tab-fix" -Rungs 1,4,8
#
param(
    [Parameter(Mandatory=$true)][string] $Label,
    [int[]] $Rungs           = @(1, 4, 8),
    [int]   $CourtsPerWorker = 29,
    [double] $MaxMinutes     = 180,
    [string] $Desde          = "01/07/2026",
    [string] $Hasta          = "31/07/2026",
    [int]    $BasePort       = 9600,
    [int]    $Courts         = 230,
    [double] $FloorGB        = 1.0
)

$ErrorActionPreference = "Stop"
$scraper = Join-Path $PSScriptRoot "scraper"
$dataH   = Join-Path $PSScriptRoot "data\worker_h"
$outRoot = Join-Path $PSScriptRoot "data\ladder\$Label"
$py = "C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null

function Stop-Fleet {
    $ps = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match '(?<!\w)worker_h\.py' })
    $ps | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 3
    foreach ($c in @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
                     Where-Object { $_.CommandLine -match 'pjud_' })) {
        Stop-Process -Id $c.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 4
}

function Health {
    param([string] $When, [string] $Rung)
    Push-Location $scraper
    $out = & $py site_health.py 2>&1 | Out-String
    Pop-Location
    $verdict = if ($out -match "SITE (\w[\w-]*)") { $matches[1] } else { "UNKNOWN" }
    Write-Host ("  health {0,-6} rung {1}: {2}" -f $When, $Rung, $verdict)
    Add-Content -Path (Join-Path $outRoot "ladder.log") -Value ("[{0}] health {1} rung {2}: {3}" -f (Get-Date -Format HH:mm:ss), $When, $Rung, $verdict)
    return $verdict
}

Stop-Fleet
Add-Content -Path (Join-Path $outRoot "ladder.log") -Value ("=== ladder '{0}' started {1} · {2} courts/worker · {3}..{4} ===" -f $Label, (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $CourtsPerWorker, $Desde, $Hasta)

foreach ($n in $Rungs) {
    Write-Host ""
    Write-Host ("=== RUNG {0} worker(s) · {1} courts each ===" -f $n, $CourtsPerWorker)

    $freeGB = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1)
    $needGB = [math]::Round($n * 0.55 + 0.8, 1)
    Write-Host ("  free RAM {0} GB, estimate {1} GB" -f $freeGB, $needGB)
    Add-Content -Path (Join-Path $outRoot "ladder.log") -Value ("[{0}] rung {1} free RAM {2} GB (estimate {3} GB)" -f (Get-Date -Format HH:mm:ss), $n, $freeGB, $needGB)
    if ($freeGB -lt $needGB) {
        Write-Host "  WARN - under the estimate. Running anyway: judge it by seconds-per-open, not by free RAM."
    }
    if ($freeGB -lt $FloorGB) {
        Write-Host ("  SKIPPED - under the {0} GB floor, where Chrome cannot start at all." -f $FloorGB)
        Add-Content -Path (Join-Path $outRoot "ladder.log") -Value ("[{0}] rung {1} SKIPPED: {2} GB free, floor {3} GB" -f (Get-Date -Format HH:mm:ss), $n, $freeGB, $FloorGB)
        continue
    }

    if ((Health "before" $n) -ne "FORM") {
        Write-Host "  SKIPPED — the address is not clean before the rung, so the result would mean nothing."
        continue
    }

    # Archive whatever is in the shared log dir so this rung is scored alone.
    $old = @(Get-ChildItem (Join-Path $dataH "docs-s*.log") -ErrorAction SilentlyContinue)
    if ($old.Count -gt 0) { $old | Remove-Item -Force -ErrorAction SilentlyContinue }

    for ($i = 1; $i -le $n; $i++) {
        $start = ($i - 1) * $CourtsPerWorker
        if ($start -ge $Courts) { continue }
        $end = [math]::Min($start + $CourtsPerWorker - 1, $Courts - 1)
        $wargs = @(
            "-u", "worker_h.py",
            "--launch", "--port", ($BasePort + $i),
            "--start", $start, "--end", $end,
            "--desde", $Desde, "--hasta", $Hasta,
            "--speed", 0, "--duty", "off", "--focus", "off",
            "--gate-release", "form",
            "--max-minutes", $MaxMinutes
        )
        $proc = Start-Process -FilePath $py -ArgumentList $wargs -WorkingDirectory $scraper `
                              -RedirectStandardOutput (Join-Path $dataH "docs-s$i.log") `
                              -RedirectStandardError (Join-Path $dataH "docs-s$i.err") `
                              -WindowStyle Hidden -PassThru
        Write-Host ("  shard {0}/{1} courts {2}-{3} PID {4}" -f $i, $n, $start, $end, $proc.Id)
        Start-Sleep -Seconds 8
    }

    # Wait for the FIRST shard to exhaust its courts, then stop the rung.
    $deadline = (Get-Date).AddMinutes($MaxMinutes + 20)
    $why = "timeout"
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 20
        $done = @(Get-ChildItem (Join-Path $dataH "docs-s*.log") -ErrorAction SilentlyContinue |
                  Where-Object { Select-String -Path $_.FullName -Pattern "DONE in" -Quiet })
        if ($done.Count -gt 0) { $why = "first shard finished"; break }
        $alive = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
                   Where-Object { $_.CommandLine -match '(?<!\w)worker_h\.py' })
        if ($alive.Count -eq 0) { $why = "all shards exited"; break }
    }
    Write-Host ("  stopping rung {0}: {1}" -f $n, $why)
    Stop-Fleet

    $rungDir = Join-Path $outRoot ("rung{0}" -f $n)
    New-Item -ItemType Directory -Force -Path $rungDir | Out-Null
    Get-ChildItem (Join-Path $dataH "docs-s*.log"), (Join-Path $dataH "docs-s*.err") -ErrorAction SilentlyContinue |
        Copy-Item -Destination $rungDir -Force
    Add-Content -Path (Join-Path $outRoot "ladder.log") -Value ("[{0}] rung {1} stopped: {2} -> {3}" -f (Get-Date -Format HH:mm:ss), $n, $why, $rungDir)
    Health "after" $n | Out-Null
}

Write-Host ""
Write-Host ("ladder '{0}' complete -> {1}" -f $Label, $outRoot)
Write-Host "score each rung:  python scraper\expduty_score.py --dir data\ladder\$Label\rung<N>"
Add-Content -Path (Join-Path $outRoot "ladder.log") -Value ("=== ladder '{0}' complete {1} ===" -f $Label, (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
