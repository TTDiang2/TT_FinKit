@echo off
rem ============================================
rem  FinKit 桌面启动器
rem  1. 检查后端是否已运行, 未运行则隐藏启动 (FastAPI 127.0.0.1:8100)
rem  2. 等待后端就绪
rem  3. 启动桌面客户端 FinKit.exe
rem  双击本文件即可, 无黑色命令行窗口
rem  停止后端: 任务管理器结束 python 进程
rem ============================================

rem ---- 首次执行: 静默重新启动自身, 实现无窗口 ----
if "%~1"=="--hidden" goto :hidden
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%~f0' -ArgumentList '--hidden' -WindowStyle Hidden"
exit /b

:hidden
setlocal
cd /d "%~dp0"

set "BACKEND_DIR=%~dp0backend"
set "EXE=%~dp0build\desktop\FinKit.exe"
set "LOG=%BACKEND_DIR%\finkit_backend.log"

rem ---- 检查桌面程序是否存在 ----
if not exist "%EXE%" (
    echo [错误] 未找到 FinKit.exe, 请先运行 build_desktop.bat 打包
    exit /b 1
)

rem ---- 检查后端是否已在运行 (端口 8100) ----
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 8100); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto :start_app

rem ---- 隐藏启动后端 ----
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath 'python' -ArgumentList 'run.py' -WorkingDirectory '%BACKEND_DIR%' -WindowStyle Hidden -RedirectStandardOutput '%LOG%' -RedirectStandardError '%LOG%.err'"

rem ---- 等待后端就绪 (最多 30 秒) ----
set /a tries=0
:wait_loop
set /a tries+=1
if %tries% gtr 30 (
    echo [错误] 后端 30 秒内未就绪, 请查看 %LOG%
    exit /b 1
)
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 8100); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto :wait_loop
)

:start_app
rem ---- 启动桌面客户端 ----
start "" "%EXE%"
exit /b 0
