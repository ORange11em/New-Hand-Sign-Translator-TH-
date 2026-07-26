@echo off
setlocal
cd /d "%~dp0"
title HandVox - Setup

echo.
echo ==========================================
echo      HandVox - First-time setup
echo ==========================================
echo.

set "PYTHON_CMD="
py -3.11 --version >nul 2>&1 && set "PYTHON_CMD=py -3.11"
if not defined PYTHON_CMD py -3.10 --version >nul 2>&1 && set "PYTHON_CMD=py -3.10"

rem Some Windows installations do not register a newly installed Python with "py" immediately.
rem Use the standard per-user installation location as a fallback.
if not defined PYTHON_CMD if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_CMD="%LocalAppData%\Programs\Python\Python311\python.exe""
if not defined PYTHON_CMD if exist "%LocalAppData%\Programs\Python\Python310\python.exe" set "PYTHON_CMD="%LocalAppData%\Programs\Python\Python310\python.exe""

if not defined PYTHON_CMD (
    echo [Python 3.10 or 3.11 was not found]
    echo Install it from https://www.python.org/downloads/
    echo Select "Add Python to PATH", then open this file again.
    echo.
    pause
    exit /b 1
)

echo Python selected:
%PYTHON_CMD% --version

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if errorlevel 1 (
        echo A broken project environment was found. Rebuilding it...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Creating HandVox environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

echo.
echo Installing required packages. This can take a few minutes...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo ==========================================
echo   Setup complete
echo   Open HandVox.bat to start
echo ==========================================
echo.
pause
exit /b 0

:error
echo.
echo Setup failed. Check your internet connection and try again.
echo.
pause
exit /b 1
