# Hourly maintenance for a SHARDED run: ingest every slot, and restart any worker that has died.
#
# Mantencion_Horaria.ps1 watches slot 0 (data\worker_a) only, which is no use for an overnight
# 4-slot pass — a slot could die at 01:00 and nothing would notice until morning.
#
# ⚠️ RESTARTS GO THROUGH THE ENTRY LOCK, they are not spaced by a timer. Whether it reuses a live
# Chrome or asks the worker to open a fresh one, a restarted worker queues behind whoever is
# currently walking in and only proceeds once that worker's first SEARCH has come back. So this
# script may safely restart all four slots in one pass: they will arrive one at a time by
# themselves. Never add a Chrome launch back into this file — see the note at the restart block.
#
#   Register :  .\Mantencion_Slots.ps1 -Install
#   Remove   :  schtasks /delete /tn "PJUD mantencion slots" /f
#   Watch    :  Get-Content <pjud>\data\slots.log -Tail 40
#
# ⚠️ Keep the UTF-8 BOM. Task Scheduler runs Windows PowerShell 5.1, which reads .ps1 as ANSI
# without one and then chokes on the accented characters below.

param(
    [switch] $Install,
    [int[]]  $Slots  = @(1, 2, 3, 4),
    [string] $Desde  = "01/07/2026",
    [string] $Hasta  = "14/07/2026",
    [string] $OnlyProc = "obligaci.*dar",
    [int]    $StaleMin = 30
)

$ErrorActionPreference = "Stop"
$TASK = "PJUD mantencion slots"

if ($Install) {
    $cmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    schtasks /create /tn $TASK /tr $cmd /sc hourly /f | Out-Null
    Write-Host "registered '$TASK' (hourly, slots $($Slots -join ','))"
    return
}

$root = $PSScriptRoot
$data = Join-Path $root "data"
$log  = Join-Path $data "slots.log"
$lock = Join-Path $data "slots.lock"

function Say($m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

if (Test-Path $lock) {
    $old = Get-Content $lock -First 1 -ErrorAction SilentlyContinue
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) { Say "skipped — previous run still going"; return }
}
$PID | Out-File $lock -Encoding ascii

try {
    $py = "C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

    # Offline is not a dead worker. Skip the whole run rather than spend restarts on a network
    # that is not there.
    $online = $false
    foreach ($h in @('1.1.1.1', '8.8.8.8')) {
        if (Test-Connection -ComputerName $h -Count 1 -Quiet -ErrorAction SilentlyContinue) { $online = $true; break }
    }
    if (-not $online) { Say "no internet — skipping entirely"; return }

    foreach ($s in $Slots) {
        $d = Join-Path $data "worker_a$s"
        if (-not (Test-Path $d)) { continue }

        # ---- ingest whatever this slot has, whether or not it is still running ----
        $out = & $py -u (Join-Path $root "scraper\ingest_worker_a.py") --slot $s --shells 2>&1
        $out | Out-File -FilePath $log -Append -Encoding utf8
        $m = $out | Select-String "upserted Causas\s+(\d+)"
        if ($m) { Say "slot $s ingest ok — causas=$($m.Matches.Groups[1].Value)" }
        else    { Say "slot $s ingest produced no count (see log)" }

        # ---- is its worker alive? The SCAN is authoritative, not the pid file ----
        $alive = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
                   Where-Object { $_.CommandLine -like "*worker_a.py*" -and $_.CommandLine -like "*--slot $s *" })
        $swp = Join-Path $d "sweep.log"
        $age = if (Test-Path $swp) { [int]((Get-Date) - (Get-Item $swp).LastWriteTime).TotalMinutes } else { 9999 }

        if ($alive.Count -gt 0) {
            Say "slot $s alive (PID $($alive[0].ProcessId)), log $age min old"
            if ($age -gt $StaleMin) { Say "  [!] slot $s running but silent for $age min — worth a look" }
            continue
        }
        if ((Test-Path $swp) -and (Get-Content $swp -Tail 3 -ErrorAction SilentlyContinue | Select-String "DONE\.")) {
            Say "slot $s finished (DONE) — nothing to restart"
            continue
        }

        # ---- restart it, on its own port and its own recorded range ----
        # ⚠️ THE SUPERVISOR NO LONGER LAUNCHES CHROME. The worker owns its browser and opens it
        # INSIDE the entry lock (worker_a.py --launch-chrome), because four fresh Chromes arriving
        # together is itself what the site reacts to — so a Chrome started from here would be
        # outside the protocol by construction. The old code was doubly broken anyway: it globbed
        # for a profile called "pjud_wA<slot>-*", which --launch-chrome never creates, so on a real
        # outage it matched nothing and gave up with "still no CDP" every hour.
        $port = 9332 + ($s * 10)
        $cdpOk = $false
        try { $null = Invoke-RestMethod "http://127.0.0.1:$port/json/version" -TimeoutSec 8; $cdpOk = $true } catch {}

        # The range comes from the slot's own state, so a restart never silently changes scope.
        $rng = & $py -c "import json,sys;t=json.load(open(r'$d\state.json',encoding='utf-8'))['tribunales'];i=sorted(v['idx'] for v in t.values());print(f'{i[0]} {i[-1]}')" 2>$null
        if (-not $rng) { Say "slot $s : no state, cannot infer range — skipping"; continue }
        $a, $b = $rng.Split(" ")
        $wargs = @("-u","worker_a.py","--port",$port,"--slot",$s,"--start",$a,"--end",$b,
                   "--only-proc",$OnlyProc,"--desde",$Desde,"--hasta",$Hasta)

        if (-not $cdpOk) {
            # A wedged Chrome still owns the profile directory, and --launch-chrome would then
            # simply hand its arguments to that running instance and never get a debugging port —
            # which reads as "Chrome never opened CDP" and costs the slot the rest of the night.
            Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -like "*pjud_wA$s*" } |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 3
            Say "slot $s : CDP $port down — the worker will open its own Chrome under the entry lock"
            $wargs += "--launch-chrome"
        }

        $pr = Start-Process $py -ArgumentList $wargs -WorkingDirectory (Join-Path $root "scraper") `
              -RedirectStandardOutput $swp -RedirectStandardError (Join-Path $d "sweep.err") `
              -WindowStyle Hidden -PassThru
        $pr.Id | Out-File (Join-Path $d "sweep.pid") -Encoding ascii
        Say "slot $s RESTARTED (PID $($pr.Id), idx $a-$b, opens own Chrome: $(-not $cdpOk))"
        # ⚠️ No stagger here. A timer is exactly what the entry lock replaced: a restarted worker
        # now waits for whoever is walking in to land a real search, however long that takes, and
        # 20 s only ever pretended to do that. This pause is just to keep two Start-Process calls
        # out of the same instant.
        Start-Sleep -Seconds 2
    }
}
catch { Say "ERROR: $($_.Exception.Message -replace "`r?`n", ' | ')" }
finally { Remove-Item $lock -Force -ErrorAction SilentlyContinue }
