@echo off
title FinKit DB Sync (GitHub Releases)
rem ============================================
rem  FinKit DB sync via GitHub RELEASES (not the
rem  repo tree) - no 50MB warning, no history bloat.
rem    PUSH  zip local finkit.db -> release asset (keep newest 4)
rem    PULL  download newest asset, backup local db, restore
rem  Auth: git credential manager token (same as push).
rem ============================================

set "HERE=%~dp0"
if /i "%~1"=="PUSH" goto push
if /i "%~1"=="PULL" goto pull

echo ========================================
echo   FinKit DB sync (GitHub Releases)
echo ========================================
choice /c pq /n /m "  [P] PUSH local DB snapshot   [Q] PULL latest snapshot ? "
if errorlevel 2 goto pull
goto push

:push
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\db_release_push.ps1"
pause
exit /b %errorlevel%

:pull
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\db_release_pull.ps1"
pause
exit /b %errorlevel%
