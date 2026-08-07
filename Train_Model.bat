@echo off
setlocal
cd /d "%~dp0"
title HandVox - Legacy Model Training

if not exist ".venv\Scripts\python.exe" goto :setup_required
".venv\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 goto :setup_required
goto :train

:setup_required
if not exist ".venv\Scripts\python.exe" (
    echo HandVox is not installed yet.
)
echo Opening setup...
call setup.bat
if errorlevel 1 exit /b 1

:train
echo.
echo ==========================================
echo     HandVox - Legacy Model Training
echo  Use GUI Prepare Training for Dataset V2
echo ==========================================
echo.
".venv\Scripts\python.exe" train_model.py
set "TRAIN_EXIT=%ERRORLEVEL%"

echo.
if not "%TRAIN_EXIT%"=="0" (
    echo Training did not complete. Read the message above.
) else (
    echo Training complete. You can now open HandVox.bat and select option 1.
)
echo.
pause
