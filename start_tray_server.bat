@echo off
title Clipboard Sync - Server (Tray)
echo.
echo ========================================
echo     Clipboard Sync Server
echo     (System Tray Version)
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Please install Python from: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if pystray is installed
python -c "import pystray" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing pystray...
    pip install pystray pillow
    echo.
)

echo [INFO] Starting server in system tray...
echo [INFO] Look for the icon in the system tray (bottom right)
echo [INFO] Right-click the icon for options
echo.

start /B pythonw tray_server.py %*
timeout /t 2 >nul
