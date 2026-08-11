@echo off
chcp 65001 >nul 2>&1
title FinKit - Personal Finance App

echo ========================================
echo        FinKit Starting...
echo ========================================
echo.

:: Resolve project root from this batch file's location (works from any drive/path)
set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

:: Start backend in a new window
echo [1/2] Starting backend (FastAPI on port 8000)...
start "FinKit Backend" cmd /k "cd /d %PROJECT_ROOT%\backend && python run.py"

:: Wait a moment for backend to initialize
timeout /t 2 /nobreak >nul

:: Start frontend in a new window
echo [2/2] Starting frontend (Vite on port 5173)...
start "FinKit Frontend" cmd /k "cd /d %PROJECT_ROOT%\frontend && npm run dev"

echo.
echo ========================================
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo  API Docs: http://localhost:8000/docs
echo ========================================
echo.
echo Close the two windows to stop the servers.
pause
