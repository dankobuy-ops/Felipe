# Hourly maintenance for the PJUD worker: ingest what has been scraped, then make sure the sweep
# is still alive — and restart it if it is not.
#
# Supersedes Ingesta_Horaria.ps1 (ingest only). The sweep died twice overnight in different ways
# and both times sat idle until a human looked: 19 hours on 2026-08-07 (a crash), and earlier a
# harness kill. The evidence was in the logs both times. Nothing acted on it.
#
#   Register :  .\Mantencion_Horaria.ps1 -Install
#   Run now  :  schtasks /run /tn "PJUD mantencion horaria"
#   Watch    :  Get-Content <pjud>\data\worker_a\ingesta.log -Tail 40
#   Remove   :  schtasks /delete /tn "PJUD mantencion horaria" /f
#
# ⚠️ This file MUST keep its UTF-8 BOM. Task Scheduler runs Windows PowerShell 5.1, which reads
# .ps1 as ANSI without one — the accented and box-drawing characters below then corrupt the parse
# and the task fails with exit 1 and an empty log, which is exactly as confusing as it sounds.

param(
    [switch] $Install,
    [int]    $Port    = 9342,
    [string] $Profile = "$env:LOCALAPPDATA\pjud_wA1",
    [string] $Desde   = "15/07/2026",
    [int]    $StaleMin = 45,      # sweep.log silence that counts as dead (cool-off tops out ~18)
    [int]    $MaxRestarts = 4     # consecutive restarts with no progress before we stop and shout
)

$ErrorActionPreference = "Stop"
$TASK = "PJUD mantencion horaria"

if ($Install) {
    $cmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    schtasks /create /tn $TASK /tr $cmd /sc hourly /f | Out-Null
    schtasks /delete /tn "PJUD ingesta horaria" /f 2>$null | Out-Null   # the ingest-only ancestor
    Write-Host "registered '$TASK' (hourly); removed the old ingest-only task"
    return
}

$root = $PSScriptRoot
$data = Join-Path $root "data\worker_a"
$log  = Join-Path $data "ingesta.log"
$lock = Join-Path $data "ingesta.lock"
New-Item -ItemType Directory -Force -Path $data | Out-Null

# Add-Content -Encoding UTF8, never Tee-Object: under PS 5.1 Tee-Object writes UTF-16, which
# mixed with the UTF-8 python output left this log half unreadable.
function Say($m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

# ── overlap guard ──────────────────────────────────────────────────────────────────────────────
# A late run is skipped, not stacked. A STALE lock (its process is gone) is ignored rather than
# obeyed — one crash would otherwise stop maintenance forever, which nobody notices until the
# data is weeks behind.
if (Test-Path $lock) {
    $old = (Get-Content $lock -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
        Say "skipped — previous maintenance (PID $old) still running"
        return
    }
    Say "clearing a stale lock (PID $old is gone)"
}
$PID | Out-File $lock -Encoding ascii

function Get-SweepProcess {
    # PID alone is not proof — Windows reuses them. Confirm the command line is really our sweep.
    $pidFile = Join-Path $data "sweep.pid"
    if (-not (Test-Path $pidFile)) { return $null }
    $spid = (Get-Content $pidFile -First 1 -ErrorAction SilentlyContinue)
    if (-not $spid) { return $null }
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$spid" -ErrorAction SilentlyContinue
    if ($p -and $p.CommandLine -match "worker_a\.py") { return $p }
    return $null
}

try {
    $py = "C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

    # ⚠️ OFFLINE IS NOT A FAILING SWEEP. Without this, an internet outage looks exactly like a
    # dead worker: the ingest errors, sweep.log stops, and the supervisor spends its restart
    # budget relaunching into a network that is not there — arriving at "4 restarts have not
    # helped, a human is needed" for a modem reboot. Neutral hosts, never pjud.cl: asking the
    # site that might be refusing us cannot tell an outage from a block.
    $online = $false
    foreach ($h in @('1.1.1.1', '8.8.8.8')) {
        if (Test-Connection -ComputerName $h -Count 1 -Quiet -ErrorAction SilentlyContinue) { $online = $true; break }
    }
    if (-not $online) {
        Say "no internet — skipping this run entirely (no ingest, no restart, no budget spent)"
        return
    }

    # ── 1. ingest ───────────────────────────────────────────────────────────────────────────
    # ⚠️ THE INGEST MUST NOT BE ABLE TO SILENCE SUPERVISION. On 2026-08-10 it threw a
    # PermissionError, the exception unwound past the supervise block, and a dead sweep sat
    # unrestarted for two hours while this log dutifully recorded "maintenance ERROR" each hour.
    # Two jobs, two failure domains: the ingest gets its own try, and whatever it does, the sweep
    # still gets checked below.
    $causas = ""
    try {
        Say "ingest start"
        $out = & $py -u (Join-Path $root "scraper\ingest_worker_a.py") 2>&1
        $out | Out-File -FilePath $log -Append -Encoding utf8
        if ($LASTEXITCODE -ne 0) { Say "ingest FAILED (exit $LASTEXITCODE) — supervising anyway" }
    } catch {
        Say "ingest THREW: $($_.Exception.Message -replace "`r?`n", ' | ') — supervising anyway"
    }
    # Pull the counters out only if the ingest actually produced them. A failed ingest simply
    # leaves $causas empty, which the stall detector below reads as "no reading this hour" rather
    # than as "no progress" — the two must not be confused, or a broken ingest would masquerade
    # as a dead sweep and trigger pointless restarts.
    $m = $out | Select-String "upserted Causas\s+(\d+)"
    if ($m) {
        $causas = $m.Matches.Groups[1].Value
        $ebm    = $out | Select-String "ebooks on disk (\d+)"
        $eb     = if ($ebm) { $ebm.Matches.Groups[1].Value } else { "?" }
        Say "ingest ok — causas=$causas ebooks_on_disk=$eb"
    }

    # ── 2. supervise ────────────────────────────────────────────────────────────────────────
    $sweepLog  = Join-Path $data "sweep.log"
    $markFile  = Join-Path $data ".last_count"
    $restFile  = Join-Path $data ".restarts"
    $prev      = if (Test-Path $markFile) { Get-Content $markFile -First 1 } else { "" }
    $restarts  = if (Test-Path $restFile) { [int](Get-Content $restFile -First 1) } else { 0 }
    $age       = if (Test-Path $sweepLog) {
                     [int]((Get-Date) - (Get-Item $sweepLog).LastWriteTime).TotalMinutes
                 } else { 9999 }
    $proc      = Get-SweepProcess

    # Progress since last hour clears the restart budget. Without this, a run that recovers and
    # then works for days would still be one hiccup away from the "needs a human" ceiling.
    if ($causas -and $prev -and $causas -ne $prev -and $restarts -gt 0) {
        Say "progress since last check ($prev -> $causas) — restart budget reset"
        $restarts = 0
    }
    if ($causas) { $causas | Out-File $markFile -Encoding ascii }

    if ($proc) {
        Say "sweep alive (PID $($proc.ProcessId)), sweep.log $age min old"
        if ($age -gt $StaleMin) {
            # Running but mute for longer than any legitimate pause. Say so; do not kill it —
            # a wrongly-killed sweep costs more than a late warning.
            Say "*** sweep process is alive but has logged NOTHING for $age min — worth a look"
        }
    }
    elseif ((Test-Path $sweepLog) -and ((Get-Content $sweepLog -Tail 3) -match "DONE\.")) {
        Say "sweep finished normally (DONE) — nothing to restart"
    }
    elseif ($restarts -ge $MaxRestarts) {
        Say "*** sweep is down and $restarts restarts have not helped — NOT restarting again."
        Say "*** This needs a human: check sweep.err, and whether the OJV is showing the"
        Say "*** full-page image CAPTCHA (tier 3), which no script may answer."
    }
    else {
        Say "*** sweep is DOWN (no worker_a process; sweep.log $age min old) — restarting"

        # ── escalation: same profile, then a FRESH one ────────────────────────────────────
        # Restart #1 reuses the profile — a warm session is worth keeping and a block clears by
        # re-entry. But if restarting has not helped, the session itself is the problem, and the
        # operator's rule (2026-08-08) is that resetting the profile is fine. Nothing is lost:
        # no login, no history worth keeping, and a virgin profile walks in first try.
        # ⚠️ MOVE TO A NEW DIRECTORY; never rename the old one. The first version retired the
        # profile with Rename-Item and failed both times it ran — "Access to the path is denied",
        # because Chrome still holds the folder. Killing the browser process first does not help
        # reliably either: its children keep handles open for a while. So the current profile path
        # is recorded in a file, and rotating simply picks a NEW path. Nothing has to be unlocked
        # for that to work.
        $profFile = Join-Path $data ".profile"
        $curProf  = if (Test-Path $profFile) { (Get-Content $profFile -First 1).Trim() } else { $Profile }
        if (-not $curProf) { $curProf = $Profile }
        # Exit 6 from the worker = "the IP moved, this profile's F5 session is void". Rotate at
        # once instead of spending two restarts proving what the worker already established.
        $ipMoved = $false
        $errFile = Join-Path $data "sweep.err"
        $logFile = Join-Path $data "sweep.log"
        foreach ($f in @($logFile, $errFile)) {
            if ((Test-Path $f) -and (Get-Content $f -Tail 25 -ErrorAction SilentlyContinue |
                                     Select-String "needs a FRESH PROFILE")) { $ipMoved = $true }
        }
        if ($ipMoved) { Say "    worker reported an IP change — rotating the profile now" }

        if ($restarts -ge 2 -or $ipMoved) {
            $curProf = "$Profile-$(Get-Date -Format 'yyyyMMdd-HHmm')"
            $curProf | Out-File $profFile -Encoding ascii
            Say "    $restarts restarts have not helped — starting a FRESH profile:"
            Say "      $(Split-Path $curProf -Leaf)"
            Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
                # ⚠️ Match the PATH, not "--user-data-dir=<path>". Chrome quotes the value
                # (--user-data-dir="C:\...") so the prefixed form matches nothing — this filter
                # silently returned 0 processes every time it ran.
                Where-Object { $_.CommandLine -like "*$Profile*" } |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 6
            $cdpOk = $false
            # Old profiles are ~400 MB each and 3.58 GB had accumulated by 2026-08-05. Best-effort:
            # a directory still locked by a lingering Chrome is simply skipped and caught next hour.
            Get-ChildItem (Split-Path $Profile -Parent) -Directory `
                -Filter "$(Split-Path $Profile -Leaf)-*" -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending | Select-Object -Skip 2 |
                ForEach-Object {
                    Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                    if (-not (Test-Path $_.FullName)) { Say "    pruned old profile $($_.Name)" } }
        }
        $Profile = $curProf

        # Chrome: the worker cannot walk in without it, and restarting Chrome on the SAME
        # profile dir is the documented, safe recovery — cookies and TSPD_101_DID survive, so
        # nothing is burned.
        $cdpOk = $false
        try { $null = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 8; $cdpOk = $true } catch {}
        if (-not $cdpOk) {
            Say "    CDP port $Port is not answering — relaunching Chrome on the same profile"
            $chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
            if (-not (Test-Path $chrome)) { $chrome = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" }
            Start-Process $chrome -ArgumentList `
                "--remote-debugging-port=$Port","--user-data-dir=$Profile","--no-first-run",
                "--no-default-browser-check","--start-maximized","https://www.pjud.cl" | Out-Null
            Start-Sleep -Seconds 12
            try { $null = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 10; $cdpOk = $true } catch {}
            Say "    CDP after relaunch: $(if ($cdpOk) {'up'} else {'STILL DOWN'})"
        }

        if ($cdpOk) {
            # -Hasta is left to the launcher's default, which formats the date with ESCAPED
            # separators — "dd/MM/yyyy" yields 08-08-2026 under es-CL and poisons the window.
            & (Join-Path $root "Iniciar_Worker_A.ps1") -Port $Port -Desde $Desde | ForEach-Object { Say "    $_" }
            $restarts++
            Say "    restart #$restarts issued"
        } else {
            Say "    cannot restart: no CDP. Chrome may need to be launched by hand."
            $restarts++
        }
    }
    $restarts | Out-File $restFile -Encoding ascii
}
catch {
    Say "maintenance ERROR: $($_.Exception.Message)"
}
finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
