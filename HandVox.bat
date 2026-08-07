@echo off
setlocal
cd /d "%~dp0"
title HandVox - Sign Language Translator

if not exist ".venv\Scripts\python.exe" goto :setup_required
".venv\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 goto :setup_required
goto :start

:setup_required
echo HandVox is not installed yet. Opening setup...
call setup.bat
if errorlevel 1 exit /b 1

:start
".venv\Scripts\python.exe" app.py
if errorlevel 1 (
    echo.
    echo HandVox closed with an error. See handvox.log for details.
    pause
)
