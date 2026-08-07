# Launch worker A DETACHED, so nothing reaps it mid-sweep.
#
# ⚠️ WHY THIS SCRIPT EXISTS. A long run started as a background task from the agent harness is
# KILLED after roughly half an hour. That is what actually happened to the census that appeared
# to "stall overnight" on 2026-08-06 at 208/230 — it was not blocked and it had not hung; the
# task was reaped, and the run sat dead for sixteen hours. Start-Process reparents the worker so
# it outlives whatever started it, and progress is read from the log file instead of a pipe.
#
# The sweep saves state after every causa, so stopping it costs one causa, never the run.
#   Resume:  just run this again — completed tribunales are skipped without a request.
#   Watch:   Get-Content <scraper>\..\data\worker_a\sweep.log -Wait -Tail 20
#   Stop:    Stop-Process -Id (Get-Content <...>\sweep.pid)

param(
    [int]    $Port   = 9342,
    [string] $Desde  = "15/07/2026",
    [string] $Hasta  = (Get-Date -Format "dd/MM/yyyy"),
    [switch] $NoEbook,                      # metadata only, request no documents
    [switch] $NoDetail                      # census only, open nothing
)

$ErrorActionPreference = "Stop"
$scraper = Join-Path $PSScriptRoot "scraper"
$data    = Join-Path $PSScriptRoot "data\worker_a"
New-Item -ItemType Directory -Force -Path $data | Out-Null

$py = "C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = (Get-Command python).Source }

# Chrome must already be up on this port with a walked-in or fresh profile. Fail loudly here
# rather than let the worker spend its startup discovering it.
try   { $null = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 8 }
catch { throw "No Chrome on CDP port $Port. Launch it first (--remote-debugging-port=$Port --user-data-dir=...)." }

$args = @("-u", "worker_a.py", "--port", $Port, "--desde", $Desde, "--hasta", $Hasta)
if ($NoEbook)  { $args += "--no-ebook" }
if ($NoDetail) { $args += "--no-detail" }

$log = Join-Path $data "sweep.log"
$err = Join-Path $data "sweep.err"
$proc = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $scraper `
                      -RedirectStandardOutput $log -RedirectStandardError $err `
                      -WindowStyle Hidden -PassThru
$proc.Id | Out-File (Join-Path $data "sweep.pid") -Encoding ascii

Write-Host "worker A detached — PID $($proc.Id)"
Write-Host "  window : $Desde .. $Hasta"
Write-Host "  log    : $log"
Write-Host "  follow : Get-Content `"$log`" -Wait -Tail 20"
Write-Host "  stop   : Stop-Process -Id $($proc.Id)"
