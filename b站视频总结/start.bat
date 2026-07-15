@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   B站视频学习笔记一条龙
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

echo [1/2] 检查依赖...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo [2/2] 启动面板...
echo 浏览器将自动打开 http://127.0.0.1:7860
echo 关闭本窗口或按 Ctrl+C 可停止服务
echo 若端口未释放，可双击 stop.bat
echo.

python app.py
if errorlevel 1 pause
