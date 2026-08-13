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
    # ⚠️ KEEP THIS IN STEP WITH THE WINDOW THE SLOTS WERE SEEDED FOR. worker_a.py refuses to
    # resume a state whose meta window differs from the one it is handed, so a restart carrying
    # the old 14/07 against a 31/07 state does not run with the wrong dates — it does not run at
    # all, and the slot stays dead until someone reads the log. Changed 2026-08-12 when the four
    # slots were re-seeded for the whole of July.
    [string] $Hasta  = "31/07/2026",
    [string] $OnlyProc = "obligaci.*dar",
    [int]    $StaleMin = 30,
    [int]    $LiveMin  = 12      # a log written within this many minutes proves the worker lives
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

        # ---- is its worker alive? ----
        # ⚠️ "THE SCAN IS AUTHORITATIVE" WAS WRONG, AND IT COST FOUR DUPLICATE WORKERS.
        # Win32_Process.CommandLine is only readable when the querying process has rights over the
        # target. Run by hand from the operator's shell this lists every worker; run from Task
        # Scheduler — different session, different elevation — it comes back EMPTY. So at 09:55 on
        # 2026-08-11 all four slots looked dead, and the supervisor started a second worker for
        # each: two processes per Chrome, two writing one state file, on overlapping ranges.
        #
        # AN UNREADABLE COMMAND LINE IS IGNORANCE, NOT DEATH. Evidence of LIFE now wins, and a
        # restart needs every source to agree the worker is gone:
        #   * the log advanced recently   -> alive. The worker is its only writer.
        #   * the recorded pid is a live python -> alive.
        #   * the scan found it           -> alive.
        $swp = Join-Path $d "sweep.log"
        $age = if (Test-Path $swp) { ((Get-Date) - (Get-Item $swp).LastWriteTime).TotalMinutes } else { 9999 }
        # -notlike ingest_worker_a.py: that script is ALSO called with --slot $s, so the obvious
        # pattern matches this supervisor's own ingest child and would report a dead slot alive.
        $scan = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
                  Where-Object { $_.CommandLine -like "*worker_a.py*" -and
                                 $_.CommandLine -notlike "*ingest_worker_a.py*" -and
                                 $_.CommandLine -like "*--slot $s *" })
        $pidLive = $false
        $pidF = Join-Path $d "sweep.pid"
        if (Test-Path $pidF) {
            $wpid = (Get-Content $pidF -First 1 -ErrorAction SilentlyContinue).Trim()
            $pr0 = Get-Process -Id $wpid -ErrorAction SilentlyContinue
            if ($pr0 -and $pr0.ProcessName -like "python*") { $pidLive = $true }
        }
        # A worker is legitimately quiet during a throttle recovery (180 s cool-off, then a full
        # re-entry), so LiveMin must sit comfortably above that. It is not the stale warning.
        $logLive = $age -lt $LiveMin

        # ...but a FRESH log does not prove life when the last thing it said was "I am stopping".
        # A worker that exits on form-loss or a spent recovery budget leaves a log seconds old,
        # and waiting out LiveMin before restarting it wastes up to 12 min of the run. Only the
        # log check is overridden — if the process is genuinely visible, believe that instead.
        $terminal = $false
        if (Test-Path $swp) {
            $tail2 = Get-Content $swp -Tail 2 -ErrorAction SilentlyContinue
            if ($tail2 -match "TALLY at form-loss:|resume with --start|DONE\.") { $terminal = $true }
        }

        if ($scan.Count -gt 0 -or $pidLive -or ($logLive -and -not $terminal)) {
            Say ("slot {0} alive (scan={1} pid={2} log={3}m)" -f $s, $scan.Count, $pidLive, [int]$age)
            if ($age -gt $StaleMin) { Say "  [!] slot $s running but silent for $([int]$age) min — worth a look" }
            continue
        }
        Say "slot $s looks dead (scan=0, pid not running, log $([int]$age) min old)"
        # ⚠️ ASK THE STATE, NOT THE LOG. This used to grep the last THREE lines for "DONE." — and
        # on 2026-08-13 worker_a grew two more closing lines (the RUN REPORT, and close_chrome's
        # "closed the Chrome this worker opened"), which pushed "DONE." out of that window. The
        # supervisor stopped being able to see a finished slot and restarted it EVERY HOUR: 21
        # times in one day, each one launching Chrome, walking into the OJV, running a search,
        # finding nothing to do and exiting. Twenty-one pointless arrivals at the site, and it
        # would have gone on for ever.
        # A worker's own log format is not an interface. meta.finished IS one — worker_a writes it
        # on every exit path precisely so something else can read the verdict.
        $finished = $false
        $stf = Join-Path $d "state.json"
        if (Test-Path $stf) {
            try {
                $finished = (& $py -c "import json;print(json.load(open(r'$stf',encoding='utf-8'))['meta'].get('finished') is True)" 2>$null).Trim() -eq "True"
            } catch { $finished = $false }
        }
        # Fall back to the log only for states written before meta.finished existed, and read a
        # generous tail this time rather than exactly three lines.
        if (-not $finished -and (Test-Path $swp)) {
            $finished = [bool](Get-Content $swp -Tail 12 -ErrorAction SilentlyContinue | Select-String "DONE\.")
        }
        if ($finished) {
            Say "slot $s finished — nothing to restart"
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

        # ⚠️ THE RANGE COMES FROM meta, NOT from the tribunal indices. Inferring it from min/max
        # of what state contains looks equivalent and is not: state ACCUMULATES across runs with
        # different shard boundaries, so on 2026-08-11 that inference restarted the slots as
        # 39-120, 78-171 and 117-229 — overlapping, each redoing its neighbour's courts. meta
        # holds what the slot was actually told to sweep. Only fall back to the old guess when
        # meta predates this change.
        # ⚠️ NO \" ESCAPES IN A POWERSHELL STRING. PowerShell escapes with a BACKTICK; a backslash
        # is literal, so `print(f\"...\")` ends the string early and PowerShell then parses
        # {m['start']} as a ScriptBlock — "ScriptBlock should only be specified as a value of the
        # Command parameter", which is exactly how this died at 10:55 on 2026-08-11, after
        # correctly deciding slot 2 needed restarting and before restarting it. Keep the python
        # free of double quotes entirely.
        $rng = & $py -c "import json;m=json.load(open(r'$d\state.json',encoding='utf-8'))['meta'];print(str(m['start'])+' '+str(m['end'])) if 'start' in m else print('')" 2>$null
        if (-not $rng) {
            # Fall back to THIS SUPERVISOR'S OWN EVEN SPLIT, never to min/max of what state
            # happens to hold: state accumulates across runs with different shard boundaries, and
            # that guess produced the overlapping 39-120 / 78-171 / 117-229 ranges. The even split
            # is what the slots were launched with, so it is right by construction.
            $n = $Slots.Count
            $i = [array]::IndexOf($Slots, $s)
            $a0 = [int][math]::Round($i * 230.0 / $n)
            $b0 = [int][math]::Round(($i + 1) * 230.0 / $n) - 1
            $rng = "$a0 $b0"
            Say "slot $s : no range in meta (state predates it) — using the even split $a0-$b0"
        }
        if (-not $rng) { Say "slot $s : no state, cannot infer range — skipping"; continue }
        $a, $b = $rng.Trim().Split(" ")
        $wargs = @("-u","worker_a.py","--port",$port,"--slot",$s,"--start",$a,"--end",$b,
                   "--only-proc",$OnlyProc,"--desde",$Desde,"--hasta",$Hasta)

        # ⚠️ FORM-LOSS NEEDS A FRESH BROWSER, NOT A FRESH PROCESS. A worker that stopped with
        # "the form is not usable" is telling us its PAGE is wedged, not that it crashed — so
        # restarting it onto the same live Chrome just reproduces the fault. Measured twice on
        # 2026-08-11: slot 2 died of form-loss at 10:36, was restarted onto its existing Chrome at
        # 11:00, and was dead again by 11:02 having managed one search and zero causas.
        $lastLog = Get-ChildItem (Join-Path $d "sweep.log*") -ErrorAction SilentlyContinue |
                   Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($lastLog -and (Get-Content $lastLog.FullName -Tail 6 -ErrorAction SilentlyContinue |
                           Select-String "form is not usable")) {
            Say "slot $s : last exit was FORM-LOSS — replacing its Chrome instead of reusing it"
            $cdpOk = $false
        }

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

        # ⚠️ ROTATE THE LOG, NEVER OVERWRITE IT. -RedirectStandardOutput truncates, so restarting
        # a dead worker used to destroy the very lines that said WHY it died — which is the only
        # reason anyone reads this file. Cost us the diagnosis of slot 1 on 2026-08-11 at 09:55:
        # it exited during a throttle recovery and the restart wiped the evidence 4 min later.
        # Truncation also leaves NUL bytes behind, which makes `grep` call the stream binary and
        # go silent, so any monitor tailing it stops reporting too.
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        foreach ($f in @("sweep.log", "sweep.err")) {
            $src = Join-Path $d $f
            if (Test-Path $src) { Move-Item $src (Join-Path $d "$f.$stamp") -Force -ErrorAction SilentlyContinue }
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
