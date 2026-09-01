# Pull the newest finkit_private.db snapshot from the data repo's GitHub
# Release, backing up the local DB first. Restart the backend afterwards.
# Dual-db mode: only the PRIVATE db (+ strategies/*.py) is synced here.
# finkit_public.db (assets/factors/prices) is NOT synced -- use your cloud drive.
param(
    [string]$Repo = "TTDiang2/TT_FinKit_Data",
    [string]$Tag = "db-snapshot",
    [string]$BackendDir = "$PSScriptRoot\..\backend",
    [string]$StrategiesDir = "$PSScriptRoot\..\strategies",
    [switch]$Force
)
$ErrorActionPreference = "Stop"

# Guard: refuse to swap the db under a running backend (SQLite would break).
$client = New-Object Net.Sockets.TcpClient
try { $client.Connect('127.0.0.1', 8100); $busy = $true } catch { $busy = $false } finally { $client.Close() }
if ($busy -and -not $Force) {
    Write-Error "Backend is RUNNING on :8100 — close it first (or pass -Force if you are sure)."
    exit 1
}

$credInput = "protocol=https`nhost=github.com`n"
$raw = $credInput | & git credential fill 2>$null
$token = ($raw | Select-String '^password=(.+)$').Matches.Groups[1].Value
if (-not $token) { Write-Error "No github.com credential found."; exit 1 }
$headers = @{ Authorization = "token $token"; Accept = "application/octet-stream" }

$rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/tags/$Tag" -Headers @{ Authorization = "token $token"; Accept = "application/vnd.github+json" }
$asset = $rel.assets | Sort-Object created_at -Descending | Select-Object -First 1
if (-not $asset) { Write-Error "Release '$Tag' has no assets."; exit 1 }
Write-Host "[1/3] downloading $($asset.name) ($([math]::Round($asset.size/1MB,1)) MB, pushed $($asset.created_at))..."

$tmpZip = Join-Path $env:TEMP "finkit_pull.zip"
$exDir = Join-Path $env:TEMP "finkit_pull"
Invoke-WebRequest -Uri $asset.url -Headers $headers -OutFile $tmpZip

# --- backup local db, replace ---
$db = Join-Path $BackendDir "finkit_private.db"
$backup = "$db.bak-$(Get-Date -Format yyyyMMdd_HHmmss)"
Move-Item $db $backup -ErrorAction SilentlyContinue
foreach ($side in @("$db-wal", "$db-shm")) { Remove-Item $side -Force -ErrorAction SilentlyContinue }
Expand-Archive -Path $tmpZip -DestinationPath $exDir -Force
Move-Item (Join-Path $exDir "finkit_private.db") $db -Force

# --- restore strategies/*.py if the snapshot carries them ---
if (Test-Path (Join-Path $exDir "strategies")) {
    if (-not (Test-Path $StrategiesDir)) { New-Item -ItemType Directory -Path $StrategiesDir -Force | Out-Null }
    Copy-Item (Join-Path $exDir "strategies\*") $StrategiesDir -Recurse -Force
    Write-Host "      strategies/*.py restored"
}
Remove-Item $tmpZip -Force; Remove-Item $exDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "[2/3] restored. old db kept at: $backup"
Write-Host "[3/3] done. PLEASE RESTART the FinKit backend so SQLite reopens cleanly."
