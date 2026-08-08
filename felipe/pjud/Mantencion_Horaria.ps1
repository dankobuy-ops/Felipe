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

    # ── 1. ingest ───────────────────────────────────────────────────────────────────────────
    Say "ingest start"
    $out = & $py -u (Join-Path $root "scraper\ingest_worker_a.py") 2>&1
    $out | Out-File -FilePath $log -Append -Encoding utf8
    $causas = ""
    if ($LASTEXITCODE -ne 0) {
        Say "ingest FAILED (exit $LASTEXITCODE)"
    } else {
        $causas = ($out | Select-String "upserted Causas\s+(\d+)").Matches.Groups[1].Value
        $eb     = ($out | Select-String "ebooks on disk (\d+)").Matches.Groups[1].Value
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
        if ($restarts -ge 2 -and (Test-Path $Profile)) {
            Say "    $restarts restarts have not helped — retiring this profile and starting fresh"
            Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -like "*--user-data-dir=$Profile*" } |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 5
            $spent = "$Profile.spent-$(Get-Date -Format 'yyyyMMdd\-HHmm')"
            try {
                Rename-Item $Profile $spent -ErrorAction Stop
                Say "    profile retired to $(Split-Path $spent -Leaf)"
            } catch {
                Say "    could not rename the profile ($($_.Exception.Message)) — continuing"
            }
            # Dead profiles are ~1 GB each and 3.58 GB of them had accumulated by 2026-08-05.
            Get-ChildItem "$(Split-Path $Profile -Parent)" -Directory -Filter "$(Split-Path $Profile -Leaf).spent-*" |
                Sort-Object Name -Descending | Select-Object -Skip 2 |
                ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
                                 Say "    pruned old profile $($_.Name)" }
        }

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
