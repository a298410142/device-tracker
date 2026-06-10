@echo off
REM 一鍵打包 redfish-test.exe(需在 Windows 上執行)
setlocal

cd /d "%~dp0"

if not exist .venv (
    echo [1/3] Creating virtual environment...
    python -m venv .venv || goto :error
)

echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements-dev.txt || goto :error

echo [3/3] Building exe with PyInstaller...
pyinstaller redfish_test_tool.spec --noconfirm || goto :error

echo.
echo Build OK: dist\redfish-test.exe
exit /b 0

:error
echo Build FAILED.
exit /b 1
