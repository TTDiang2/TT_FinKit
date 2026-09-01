# Push finkit_private.db snapshot to the private data repo's GitHub Release.
# Releases bypass the 50MB repo-tree warning entirely (asset cap is 2GB);
# history never re-stores each snapshot, so the repo stays tiny forever.
# Auth: token comes from Windows git credential manager (same creds as push).
# Dual-db mode: only the PRIVATE db (+ strategies/*.py) is synced here.
# finkit_public.db (assets/factors/prices) is NOT synced -- use your cloud drive.
param(
    [string]$Repo = "TTDiang2/TT_FinKit_Data",
    [string]$Tag = "db-snapshot",
    [string]$DbPath = "$PSScriptRoot\..\backend\finkit_private.db",
    [string]$StrategiesDir = "$PSScriptRoot\..\strategies"
)
$ErrorActionPreference = "Stop"

if (-not (Test-Path $DbPath)) { Write-Error "DB not found: $DbPath"; exit 1 }

# --- resolve token from git credentials ---
$credInput = "protocol=https`nhost=github.com`n"
$raw = $credInput | & git credential fill 2>$null
$token = ($raw | Select-String '^password=(.+)$').Matches.Groups[1].Value
if (-not $token) { Write-Error "No github.com credential found in git credential store."; exit 1 }
$headers = @{ Authorization = "token $token"; Accept = "application/vnd.github+json"; "X-GitHub-Api-Version" = "2022-11-28" }

# --- consistent snapshot WITHOUT touching the live file ---
# The running backend holds locks, so never zip/checkpoint in place:
# sqlite3 backup() merges the WAL and copies around any lock cleanly.
$snapDir = Join-Path $env:TEMP "finkit_snap_$PID"
New-Item -ItemType Directory -Path $snapDir -Force | Out-Null
$snap = Join-Path $snapDir "finkit_private.db"
$helper = Join-Path $PSScriptRoot "..\backend\scripts\_db_snapshot.py"
& python $helper $DbPath $snap
if ($LASTEXITCODE -ne 0) { Write-Error "sqlite backup failed"; exit 1 }

# --- include strategies/*.py (they live OUTSIDE the db) ---
if (Test-Path $StrategiesDir) {
    Copy-Item $StrategiesDir -Destination (Join-Path $snapDir "strategies") -Recurse -Force
    Write-Host "      strategies/*.py included"
}

# --- compress the consistent snapshot ---
$stamp = Get-Date -Format yyyyMMdd_HHmm
$tmpZip = Join-Path $env:TEMP "finkit_private_db_$stamp.zip"
Compress-Archive -Path "$snapDir\*" -DestinationPath $tmpZip -Force
Remove-Item $snapDir -Recurse -Force
$sizeMb = [math]::Round((Get-Item $tmpZip).Length / 1MB, 1)
Write-Host "[1/3] snapshot zipped: $sizeMb MB"

# --- get or create the rolling release ---
$rel = $null
try {
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/tags/$Tag" -Headers $headers
} catch {
    $body = @{ tag_name = $Tag; name = "DB snapshots (rolling)"; body = "Auto-managed private-db snapshots pushed by sync_db_release.bat" } | ConvertTo-Json
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases" -Method Post -Headers $headers -ContentType "application/json" -Body $body
}
$relId = $rel.id

# --- remove stale asset(s), upload fresh ---
foreach ($a in @($rel.assets)) {
    Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/assets/$($a.id)" -Method Delete -Headers $headers | Out-Null
    Write-Host "      removed old asset $($a.name)"
}
$assetName = "finkit-private-db-$stamp.zip"
Invoke-RestMethod -Uri "https://uploads.github.com/repos/$Repo/releases/$relId/assets?name=$assetName" `
    -Method Post -Headers $headers -ContentType "application/zip" -InFile $tmpZip | Out-Null
Remove-Item $tmpZip -Force
Write-Host "[2/3] uploaded asset: $assetName"

# --- prune: keep newest 4 assets total across this release ---
$allAssets = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/$relId/assets?per_page=100" -Headers $headers
$extra = @($allAssets | Sort-Object created_at -Descending | Select-Object -Skip 4)
foreach ($a in $extra) {
    Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/assets/$($a.id)" -Method Delete -Headers $headers | Out-Null
    Write-Host "      pruned $([math]::Round($a.size/1MB,1))MB asset from $(Get-Date $a.created_at -Format yyyy-MM-dd)"
}
Write-Host "[3/3] done. Other machine pulls with: sync_db_release.bat PULL"
