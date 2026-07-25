@echo off
setlocal
cd /d "%~dp0"
title HandVox - Sign Detection

if not exist ".venv\Scripts\python.exe" goto :setup_required
".venv\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 goto :setup_required
goto :detect

:setup_required
if not exist ".venv\Scripts\python.exe" (
    echo HandVox is not installed yet.
)
echo Opening setup...
call setup.bat
if errorlevel 1 exit /b 1

:detect
echo.
echo ==========================================
echo       HandVox - Sign Detection
echo ==========================================
echo.
".venv\Scripts\python.exe" run_detector.py
set "DETECT_EXIT=%ERRORLEVEL%"

echo.
if not "%DETECT_EXIT%"=="0" (
    echo Detection did not start. If the model is outdated, run Train_Model.bat first.
)
echo.
pause
