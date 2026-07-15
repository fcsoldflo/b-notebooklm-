@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在释放端口 7860 ...

set found=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7860" ^| findstr "LISTENING"') do (
    echo 结束进程 PID=%%a
    taskkill /F /PID %%a >nul 2>&1
    set found=1
)

if "%found%"=="0" (
    echo 未发现占用 7860 端口的进程。
) else (
    echo 端口已释放。
)

pause
