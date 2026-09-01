@echo off
title FinKit Data Sync (GitHub private repo)

rem ============================================================
rem  FinKit multi-PC data sync via private GitHub repository
rem
rem  Usage:
rem    sync_db.bat            - interactive menu (double-click friendly)
rem    sync_db.bat push       - upload local db + strategies (default)
rem    sync_db.bat pull       - download latest data from data repo
rem    sync_db.bat restore    - restore local db from a backup snapshot
rem
rem  What gets synced:
rem    - backend\finkit_private.db (accounts, transactions, investments,
rem      backtests, signals, user settings -- personal data ONLY)
rem    - strategies\*.py           (strategy files, live OUTSIDE the db)
rem  NOTE: finkit_public.db (assets/factors/prices) is NOT synced here;
rem  sync it with your own cloud drive.
rem
rem  Safety:
rem    - SQLite WAL is checkpointed before every copy so no recent
rem      writes are left behind in -wal files.
rem    - Warns if the backend is still running (inconsistent snapshot).
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
set "LOCAL_DB=%ROOT%\backend\finkit_private.db"
set "STRATEGIES_DIR=%ROOT%\strategies"
set "BACKUP_DIR=%DATA_DIR%\backups"
set "REMOTE_BRANCH=main"

rem ---- resolve mode: command-line arg, or interactive menu on double-click ----
set "MODE=%~1"
if /i "%MODE%"=="push" goto :mode_chosen
if /i "%MODE%"=="pull" goto :mode_chosen
if /i "%MODE%"=="restore" goto :mode_chosen

:menu
cls
title FinKit Data Sync
echo.
echo   ==========================================
echo    FinKit Data Sync  (db + strategies)
echo   ==========================================
echo.
echo    [1] PUSH    upload local data to private repo
echo    [2] PULL    download private repo data to this PC
echo    [3] RESTORE restore db from a local backup
echo    [Q] quit
echo.
choice /c 123q /n /t 30 /d q /m "   Choose (1/2/3, auto-quit in 30s): "
if errorlevel 4 exit /b 0
if errorlevel 3 ( set "MODE=restore" & goto :mode_chosen )
if errorlevel 2 ( set "MODE=pull" & goto :mode_chosen )
set "MODE=push"

:mode_chosen
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

rem ---- warn if backend is running (db may be mid-write) ----
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "try { (Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'run\.py|uvicorn' } | Measure-Object).Count } catch { 0 }"`) do set "BACKEND_RUNNING=%%i"
if not "%BACKEND_RUNNING%"=="0" (
    echo [WARNING] FinKit backend appears to be RUNNING.
    echo   Data written recently may still be in the SQLite WAL file, and the
    echo   copied db snapshot can be inconsistent. Best: stop the backend first.
    echo   Continuing anyway in 10 seconds ...
    timeout /t 10 /nobreak >nul
)

rem ---- flush SQLite WAL into the main db file before copying ----
echo [PREP] Flushing SQLite WAL (ensuring all data is inside finkit_private.db) ...
python -c "import sqlite3; c = sqlite3.connect(r'%LOCAL_DB%'); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.close()" >nul 2>&1
if errorlevel 1 echo   [WARN] WAL checkpoint skipped (python or db not available).

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
echo [3/4] Copying local database + strategies ...
copy /Y "%LOCAL_DB%" "%DATA_DIR%\finkit_private.db" >nul
call :sync_strategies_to_datarepo
rem    - backend\finkit_private.db (accounts, transactions, investments,
inkit.db" (
    git -C "%DATA_DIR%" rm -q --cached finkit.db >nul 2>&1
rem    - backend\finkit_private.db (accounts, transactions, investments,
inkit.db" >nul 2>&1
)
echo [4/4] Force pushing local database ...
git -C "%DATA_DIR%" add finkit_private.db strategies
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
echo [3/4] Copying remote database + strategies into local ...
copy /Y "%DATA_DIR%\finkit_private.db" "%LOCAL_DB%" >nul
call :sync_strategies_from_datarepo
echo [4/4] Done.
echo.
echo Local database replaced by remote version.
echo Your previous local db is backed up in %BACKUP_DIR%.
pause
exit /b 0

:push_clean
echo [2/4] Copying local database + strategies into data repo ...
copy /Y "%LOCAL_DB%" "%DATA_DIR%\finkit_private.db" >nul
if errorlevel 1 (
    echo [ERROR] Cannot copy %LOCAL_DB%. Does it exist?
    pause
    exit /b 1
)
call :sync_strategies_to_datarepo
rem drop legacy single-db file from data repo tree (kept in history anyway)
rem    - backend\finkit_private.db (accounts, transactions, investments,
inkit.db" (
    git -C "%DATA_DIR%" rm -q --cached finkit.db >nul 2>&1
rem    - backend\finkit_private.db (accounts, transactions, investments,
inkit.db" >nul 2>&1
)
echo [3/4] Committing ...
git -C "%DATA_DIR%" add finkit_private.db strategies
git -C "%DATA_DIR%" commit -m "sync: finkit_private.db + strategies" >nul 2>&1
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
echo [3/3] Copying database + strategies into local ...
copy /Y "%DATA_DIR%\finkit_private.db" "%LOCAL_DB%" >nul
call :sync_strategies_from_datarepo
echo.
echo Done. Database restored from private repo.
echo Previous local db backed up in %BACKUP_DIR%.
echo [NOTE] Restart the FinKit backend so it reopens the updated database.
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

:sync_strategies_to_datarepo
rem copy local strategies/*.py into the data repo (they live OUTSIDE finkit.db)
if not exist "%STRATEGIES_DIR%" exit /b 0
if not exist "%DATA_DIR%\strategies" mkdir "%DATA_DIR%\strategies"
copy /Y "%STRATEGIES_DIR%\*.py" "%DATA_DIR%\strategies\" >nul 2>&1
echo   synced: strategies\*.py -^> data repo
exit /b 0

:sync_strategies_from_datarepo
rem restore strategies/*.py from the data repo into the main workspace
if not exist "%DATA_DIR%\strategies" exit /b 0
if not exist "%STRATEGIES_DIR%" mkdir "%STRATEGIES_DIR%"
copy /Y "%DATA_DIR%\strategies\*.py" "%STRATEGIES_DIR%\" >nul 2>&1
echo   synced: data repo strategies -^> %STRATEGIES_DIR%
exit /b 0

:backup_local
if not exist "%LOCAL_DB%" (
    echo [SKIP] No local database to back up.
    exit /b 0
)
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"`) do set "TS=%%i"
set "BK=%BACKUP_DIR%\finkit_private.db.%TS%.bak"
copy /Y "%LOCAL_DB%" "%BK%" >nul
echo   backed up: %BK%
rem keep only latest 20 backups
powershell -NoProfile -Command "Get-ChildItem '%BACKUP_DIR%\*.bak' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 | Remove-Item -Force" >nul 2>&1
exit /b 0