# Hourly ingest of worker A's output into Neon + Drive. Registered as a Windows Scheduled Task,
# so it is independent of Chrome, of the sweep, and of any agent session.
#
# Safe to run at ANY time, including mid-sweep: the sweep writes state.json and PDFs to disk,
# this reads them and writes to Postgres/Drive. It never touches CDP and never issues a request
# to pjud.cl, so it cannot spend WAF budget or disturb a run.
#
#   Register :  .\Ingesta_Horaria.ps1 -Install
#   Remove   :  schtasks /delete /tn "PJUD ingesta horaria" /f
#   Watch    :  Get-Content <pjud>\data\worker_a\ingesta.log -Tail 40
#   Run now  :  schtasks /run /tn "PJUD ingesta horaria"

param([switch] $Install)

$ErrorActionPreference = "Stop"
$TASK = "PJUD ingesta horaria"

if ($Install) {
    $cmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    schtasks /create /tn $TASK /tr $cmd /sc hourly /f | Out-Null
    Write-Host "registered '$TASK' — runs hourly"
    schtasks /query /tn $TASK /fo LIST | Select-String "Nombre de tarea|TaskName|Pr.xima|Next Run|Estado|Status"
    return
}

$data = Join-Path $PSScriptRoot "data\worker_a"
$log  = Join-Path $data "ingesta.log"
$lock = Join-Path $data "ingesta.lock"
New-Item -ItemType Directory -Force -Path $data | Out-Null

# Add-Content -Encoding UTF8, never Tee-Object: under Windows PowerShell 5.1 Tee-Object writes
# UTF-16, so mixing it with the UTF-8 python output left the log half-unreadable.
function Say($m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

# ── overlap guard ──────────────────────────────────────────────────────────────
# An ingest that uploads a few hundred PDFs can outlast its own hour. Two copies running at once
# would upload the same files twice and race on the same rows, so a late run is skipped rather
# than stacked. A stale lock (process already gone) is ignored, not obeyed — otherwise one crash
# silently stops the ingest forever, which is the failure nobody notices.
if (Test-Path $lock) {
    $old = (Get-Content $lock -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
        Say "skipped — previous ingest (PID $old) is still running"
        return
    }
    Say "clearing a stale lock (PID $old no longer exists)"
}
$PID | Out-File $lock -Encoding ascii

try {
    $py = "C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

    Say "ingest start"
    $out = & $py -u (Join-Path $PSScriptRoot "scraper\ingest_worker_a.py") 2>&1
    $out | Out-File -FilePath $log -Append -Encoding utf8
    if ($LASTEXITCODE -ne 0) { Say "ingest FAILED (exit $LASTEXITCODE)" }
    else {
        # Report the numbers that matter, so the log answers "is it still working?" at a glance
        # rather than needing the DB opened.
        $causas = ($out | Select-String "upserted Causas\s+(\d+)").Matches.Groups[1].Value
        $eb     = ($out | Select-String "ebooks on disk (\d+)").Matches.Groups[1].Value
        Say "ingest ok — causas=$causas ebooks_on_disk=$eb"
    }
} catch {
    Say "ingest ERROR: $($_.Exception.Message)"
} finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
