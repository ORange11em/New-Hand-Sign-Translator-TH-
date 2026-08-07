@echo off
setlocal
cd /d "%~dp0"
title HandVox V2 - Train and Evaluate

if not exist ".venv\Scripts\python.exe" (
    echo Python environment is not ready. Run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" training_cli.py train
echo.
pause
