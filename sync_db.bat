@echo off
title FinKit Data Sync (GitHub private repo)

rem ============================================================
rem  FinKit multi-PC data sync via private GitHub repository
rem
rem  Usage:
rem    sync_db.bat push   - copy local backend\finkit.db to data repo (default)
rem    sync_db.bat pull   - fetch latest finkit.db from data repo to local
rem
rem  Requirements:
rem    - gh CLI authenticated (gh auth login) OR git credential set up
rem    - Data repo is PRIVATE and must stay private (contains personal data)
rem ============================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "DATA_REPO_URL=https://github.com/TTDiang2/TT_FinKit_Data.git"
set "DATA_DIR=%ROOT%\..\TT_FinKit_Data"
set "LOCAL_DB=%ROOT%\backend\finkit.db"

rem ---- resolve mode ----
set "MODE=push"
if /i "%~1"=="pull" set "MODE=pull"
if /i "%~1"=="push" set "MODE=push"

echo Mode: %MODE%
echo Data repo: %DATA_REPO_URL%
echo Data dir: %DATA_DIR%
echo.

rem ---- clone data repo on first run ----
if not exist "%DATA_DIR%\.git" (
    echo [1/3] Cloning data repo for the first time ...
    git clone "%DATA_REPO_URL%" "%DATA_DIR%"
    if errorlevel 1 (
        echo.
        echo [ERROR] Clone failed. Check gh auth or git credentials.
        pause
        exit /b 1
    )
)

if /i "%MODE%"=="push" goto :do_push
goto :do_pull

:do_push
echo [1/3] Pulling latest state (rebase) ...
git -C "%DATA_DIR%" pull --rebase
echo.
echo [2/3] Copying local database into data repo ...
copy /Y "%LOCAL_DB%" "%DATA_DIR%\finkit.db" >nul
if errorlevel 1 (
    echo [ERROR] Cannot copy %LOCAL_DB%. Does it exist?
    pause
    exit /b 1
)
echo.
echo [3/3] Committing and pushing ...
git -C "%DATA_DIR%" add finkit.db
git -C "%DATA_DIR%" commit -m "sync: finkit.db (%date% %time%)" >nul 2>&1
git -C "%DATA_DIR%" push
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

:do_pull
echo [1/3] Pulling latest database from data repo ...
git -C "%DATA_DIR%" pull --rebase
if errorlevel 1 (
    echo.
    echo [ERROR] Pull failed. Check credentials and network.
    pause
    exit /b 1
)
echo.
echo [2/3] Copying database into local backend ...
copy /Y "%DATA_DIR%\finkit.db" "%LOCAL_DB%" >nul
if errorlevel 1 (
    echo [ERROR] Cannot copy database into %LOCAL_DB%.
    pause
    exit /b 1
)
echo.
echo [3/3] Done. Database restored from private repo.
pause
exit /b 0