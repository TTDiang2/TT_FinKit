@echo off
title FinKit Desktop Build

rem ============================================
rem  FinKit desktop one-click build script
rem  Steps: build frontend -> pake package -> copy launcher
rem  Output: build\desktop\ (exe/msi/bat/pyw)
rem ============================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

rem ---- Tunable parameters (edit as needed) ----
set "APP_NAME=FinKit"
set "APP_URL=http://127.0.0.1:8100"
set "APP_ICON=%ROOT%\build\finkit.ico"
set "WIN_WIDTH=1280"
set "WIN_HEIGHT=800"
rem --------------------------------------------

echo ========================================
echo   FinKit Desktop one-click build
echo   frontend build + Pake exe/msi + launcher
echo ========================================
echo.

rem 1. Check pake is installed
where pake >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pake not found. Install it first: npm i -g pake-cli
    pause
    exit /b 1
)

rem 2. Build frontend (vue-tsc + vite build -^> frontend/dist)
echo [1/4] Building frontend ...
cd /d "%ROOT%\frontend"
call npm run build
if errorlevel 1 (
    echo.
    echo [ERROR] Frontend build failed. Aborting.
    pause
    exit /b 1
)

rem 3. Pake package into build\desktop
echo.
echo [2/4] Packaging desktop app with Pake ...
cd /d "%ROOT%\build\desktop"
pake "%APP_URL%" --name "%APP_NAME%" --icon "%APP_ICON%" --width %WIN_WIDTH% --height %WIN_HEIGHT% --keep-binary
if errorlevel 1 (
    echo.
    echo [ERROR] Pake packaging failed. Aborting.
    pause
    exit /b 1
)

rem 4. Copy launcher files (source lives in launcher\ for git)
echo.
echo [3/4] Copying launcher files ...
copy /Y "%ROOT%\launcher\FinKit-Desktop.bat" "%ROOT%\build\desktop\FinKit-Desktop.bat" >nul
copy /Y "%ROOT%\launcher\FinKit.pyw" "%ROOT%\build\desktop\FinKit.pyw" >nul
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to copy launcher files. Aborting.
    pause
    exit /b 1
)

rem 5. Auto commit & push frontend/dist so other machines can pull directly
echo.
echo [4/4] Syncing frontend/dist to GitHub ...
cd /d "%ROOT%"
git add frontend/dist >nul 2>&1
git diff --cached --quiet
if errorlevel 1 (
    for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"`) do set "TS=%%i"
    git commit -m "build: refresh frontend/dist (%%TS%%)" -q
    git push origin master
    if errorlevel 1 (
        echo   [WARN] Push failed - commit is local, push manually later.
    ) else (
        echo   dist committed and pushed.
    )
) else (
    echo   dist unchanged, nothing to sync.
)

echo.
echo ========================================
echo   Build complete!
echo   exe:      build\desktop\FinKit.exe
echo   msi:      build\desktop\FinKit.msi
echo   launcher: build\desktop\FinKit-Desktop.bat
echo   Run:      build\desktop\FinKit-Desktop.bat
echo ========================================
pause