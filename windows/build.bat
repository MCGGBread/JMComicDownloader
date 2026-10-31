@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 创建虚拟环境...
    python -m venv .venv || goto :fail
)

echo [2/3] 安装依赖...
".venv\Scripts\python.exe" -m pip install -q -U pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller || goto :fail

echo [3/3] 打包 exe...
".venv\Scripts\python.exe" build.py || goto :fail

echo.
echo 完成： dist\JMComicClient.exe
pause
exit /b 0

:fail
echo.
echo 构建失败，请查看上方日志。
pause
exit /b 1
