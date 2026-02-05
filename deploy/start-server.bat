@echo off
REM Quick-start script for Vibe Agents on Windows
REM Double-click to launch the server

cd /d "%~dp0.."
python deploy\start.py %*

if errorlevel 1 (
    echo.
    echo   Failed to start. Make sure you have run install-windows.ps1 first.
    echo.
    pause
)
