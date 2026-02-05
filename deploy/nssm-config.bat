@echo off
REM ============================================================
REM Vibe Agents - NSSM Service Configuration (Manual)
REM ============================================================
REM
REM This script manually configures the NSSM service.
REM Normally you should use install-windows.ps1 instead.
REM Use this only if you need to reconfigure the service.
REM
REM Requirements:
REM   - NSSM must be in PATH or in deploy\nssm\nssm.exe
REM   - Python 3.9+ must be installed
REM   - Run as Administrator
REM ============================================================

setlocal enabledelayedexpansion

set SERVICE_NAME=VibeAgents
set PORT=8000

REM Find project root (parent of deploy directory)
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..

REM Find NSSM
if exist "%SCRIPT_DIR%nssm\nssm.exe" (
    set NSSM=%SCRIPT_DIR%nssm\nssm.exe
) else (
    where nssm >nul 2>&1
    if errorlevel 1 (
        echo [FAIL] NSSM not found. Run install-windows.ps1 first.
        exit /b 1
    )
    set NSSM=nssm
)

REM Find Python
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.executable)"') do set PYTHON=%%i

echo.
echo   Vibe Agents - NSSM Service Configuration
echo   ==========================================
echo   Service : %SERVICE_NAME%
echo   Python  : %PYTHON%
echo   Project : %PROJECT_DIR%
echo   Port    : %PORT%
echo.

REM Stop and remove existing service
echo   Stopping existing service...
%NSSM% stop %SERVICE_NAME% 2>nul
timeout /t 2 /nobreak >nul
%NSSM% remove %SERVICE_NAME% confirm 2>nul

REM Install service
echo   Installing service...
%NSSM% install %SERVICE_NAME% "%PYTHON%" "-m uvicorn backend.main:app --host 0.0.0.0 --port %PORT%"
%NSSM% set %SERVICE_NAME% AppDirectory "%PROJECT_DIR%"
%NSSM% set %SERVICE_NAME% DisplayName "Vibe Agents Server"
%NSSM% set %SERVICE_NAME% Description "Vibe Agents - Multi-Agent AI Coding Platform"
%NSSM% set %SERVICE_NAME% Start SERVICE_AUTO_START

REM Logging
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"
%NSSM% set %SERVICE_NAME% AppStdout "%PROJECT_DIR%\logs\vibe-agents-stdout.log"
%NSSM% set %SERVICE_NAME% AppStderr "%PROJECT_DIR%\logs\vibe-agents-stderr.log"
%NSSM% set %SERVICE_NAME% AppRotateFiles 1
%NSSM% set %SERVICE_NAME% AppRotateBytes 5242880

REM Auto-restart on failure
%NSSM% set %SERVICE_NAME% AppExit Default Restart
%NSSM% set %SERVICE_NAME% AppRestartDelay 5000

echo.
echo   [OK] Service configured.
echo.
echo   Start with: %NSSM% start %SERVICE_NAME%
echo   Stop with:  %NSSM% stop %SERVICE_NAME%
echo   Edit with:  %NSSM% edit %SERVICE_NAME%
echo.

pause
