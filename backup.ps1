# Backup all files in this folder to the Felipe repo (origin/main).
# Usage:  .\backup.ps1            -> commits with a timestamped message
#         .\backup.ps1 "message"  -> commits with your own message
param([string]$Message)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

git add -A

# git diff --cached --quiet exits 0 when nothing is staged, 1 when there are changes.
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "Nothing to back up - working tree is clean." -ForegroundColor Yellow
    exit 0
}

if (-not $Message) {
    $stamp   = Get-Date -Format "yyyy-MM-dd HH:mm"
    $Message = "backup: $stamp"
}

git commit -m $Message
git push origin main

Write-Host "Backup complete -> github.com/dankobuy-ops/Felipe" -ForegroundColor Green
