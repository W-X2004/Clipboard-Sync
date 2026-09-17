@echo off
title Clipboard Sync Auto-Start Manager
cd /d "%~dp0"
python "%~dp0autostart.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start manager. Is Python installed and on PATH?
    pause
)
