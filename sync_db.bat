@echo off
title FinKit Data Sync (GitHub private repo)

rem ============================================================
rem  FinKit multi-PC data sync via private GitHub repository
rem
rem  Usage:
rem    sync_db.bat push     - upload local backend\finkit.db (default)
rem    sync_db.bat pull     - download latest finkit.db from data repo
rem    sync_db.bat restore  - restore local db from a backup snapshot
rem
rem  Safety:
rem    - Local db is auto-backed up (backups\*.bak) before every
rem      pull and before conflict resolution.
rem    - Push conflict (remote has newer commits): you choose
rem      keep-local / keep-remote / abort.
rem    - Data repo must stay PRIVATE (contains personal data).
rem ============================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "DATA_REPO_URL=https://github.com/TTDiang2/TT_FinKit_Data.git"
set "DATA_DIR=%ROOT%\..\TT_FinKit_Data"
set "LOCAL_DB=%ROOT%\backend\finkit.db"
set "BACKUP_DIR=%DATA_DIR%\backups"
set "REMOTE_BRANCH=main"

rem ---- resolve mode ----
set "MODE=push"
if /i "%~1"=="pull" set "MODE=pull"
if /i "%~1"=="push" set "MODE=push"
if /i "%~1"=="restore" set "MODE=restore"

echo Mode: %MODE%
echo Data repo: %DATA_REPO_URL%
echo Data dir: %DATA_DIR%
echo.

rem ---- clone data repo on first run ----
if not exist "%DATA_DIR%\.git" (
    echo [CLONE] First run - cloning data repo ...
    git clone "%DATA_REPO_URL%" "%DATA_DIR%"
    if errorlevel 1 (
        echo.
        echo [ERROR] Clone failed. Check gh auth or git credentials.
        pause
        exit /b 1
    )
)

rem ---- ensure backups dir + gitignore ----
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
if not exist "%DATA_DIR%\.gitignore" (
    (echo backups/) > "%DATA_DIR%\.gitignore"
)

if /i "%MODE%"=="pull" goto :do_pull
if /i "%MODE%"=="restore" goto :do_restore
goto :do_push

rem ============ PUSH ============
:do_push
echo [1/4] Checking remote state ...
git -C "%DATA_DIR%" fetch origin >nul 2>&1
set "REMOTE_EXISTS=0"
git -C "%DATA_DIR%" rev-parse --verify origin/%REMOTE_BRANCH% >nul 2>&1
if not errorlevel 1 set "REMOTE_EXISTS=1"

set "BEHIND=0"
if "%REMOTE_EXISTS%"=="1" (
    for /f "usebackq delims=" %%i in (`git -C "%DATA_DIR%" rev-list --count HEAD..origin/%REMOTE_BRANCH% 2^>nul`) do set "BEHIND=%%i"
)

if "%BEHIND%"=="0" goto :push_clean

rem ---- remote has newer commits: possible conflict ----
echo.
echo [WARNING] Remote data repo has newer commits (another PC pushed).
echo Local database will be backed up before any change.
call :backup_local
echo.
echo Choose how to resolve:
echo   1 = Keep LOCAL database (overwrite remote, force push)
echo   2 = Keep REMOTE database (overwrite local, discard local changes)
echo   3 = Abort (do nothing)
choice /c 123 /t 30 /d 3 /m "Your choice (1/2/3, default 3=abort in 30s)" >nul
if errorlevel 3 exit /b 0
if errorlevel 2 goto :conflict_keep_remote
goto :conflict_keep_local

:conflict_keep_local
echo [2/4] Keeping local - resetting data repo to remote state ...
git -C "%DATA_DIR%" reset --hard origin/%REMOTE_BRANCH% >nul 2>&1
echo [3/4] Copying local database ...
copy /Y "%LOCAL_DB%" "%DATA_DIR%\finkit.db" >nul
echo [4/4] Force pushing local database ...
git -C "%DATA_DIR%" add finkit.db
git -C "%DATA_DIR%" commit -m "sync: local db wins" >nul 2>&1
git -C "%DATA_DIR%" push --force-with-lease origin %REMOTE_BRANCH%
if errorlevel 1 (
    echo.
    echo [ERROR] Force push failed.
    pause
    exit /b 1
)
echo.
echo Done. Local database now authoritative on remote.
pause
exit /b 0

:conflict_keep_remote
echo [2/4] Keeping remote - resetting data repo ...
git -C "%DATA_DIR%" reset --hard origin/%REMOTE_BRANCH% >nul 2>&1
echo [3/4] Copying remote database into local backend ...
copy /Y "%DATA_DIR%\finkit.db" "%LOCAL_DB%" >nul
echo [4/4] Done.
echo.
echo Local database replaced by remote version.
echo Your previous local db is backed up in %BACKUP_DIR%.
pause
exit /b 0

:push_clean
echo [2/4] Copying local database into data repo ...
copy /Y "%LOCAL_DB%" "%DATA_DIR%\finkit.db" >nul
if errorlevel 1 (
    echo [ERROR] Cannot copy %LOCAL_DB%. Does it exist?
    pause
    exit /b 1
)
echo [3/4] Committing ...
git -C "%DATA_DIR%" add finkit.db
git -C "%DATA_DIR%" commit -m "sync: finkit.db" >nul 2>&1
echo [4/4] Pushing ...
git -C "%DATA_DIR%" push origin %REMOTE_BRANCH%
if errorlevel 1 (
    echo.
    echo [ERROR] Push failed. Check credentials and network.
    pause
    exit /b 1
)
echo.
echo Done. Local data pushed to private repo.
pause
exit /b 0

rem ============ PULL ============
:do_pull
echo [1/3] Backing up current local database ...
call :backup_local
echo [2/3] Pulling latest database from data repo ...
git -C "%DATA_DIR%" pull --rebase origin %REMOTE_BRANCH%
if errorlevel 1 (
    echo.
    echo [ERROR] Pull failed. Check credentials and network.
    pause
    exit /b 1
)
echo [3/3] Copying database into local backend ...
copy /Y "%DATA_DIR%\finkit.db" "%LOCAL_DB%" >nul
echo.
echo Done. Database restored from private repo.
echo Previous local db backed up in %BACKUP_DIR%.
pause
exit /b 0

rem ============ RESTORE ============
:do_restore
echo Available backups in %BACKUP_DIR%:
echo.
dir /b "%BACKUP_DIR%\*.bak" 2>nul
echo.
set /p "BKFILE=Enter backup filename to restore (or leave empty to cancel): "
if "%BKFILE%"=="" exit /b 0
if not exist "%BACKUP_DIR%\%BKFILE%" (
    echo [ERROR] Backup not found: %BKFILE%
    pause
    exit /b 1
)
copy /Y "%BACKUP_DIR%\%BKFILE%" "%LOCAL_DB%" >nul
echo.
echo Done. Local database restored from %BKFILE%.
pause
exit /b 0

rem ============ HELPERS ============
:backup_local
if not exist "%LOCAL_DB%" (
    echo [SKIP] No local database to back up.
    exit /b 0
)
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "TS=%%i"
set "BK=%BACKUP_DIR%\finkit.db.%TS%.bak"
copy /Y "%LOCAL_DB%" "%BK%" >nul
echo   backed up: %BK%
rem keep only latest 20 backups
powershell -NoProfile -Command "Get-ChildItem '%BACKUP_DIR%\*.bak' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 | Remove-Item -Force" >nul 2>&1
exit /b 0