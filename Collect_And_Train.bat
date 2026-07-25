@echo off
setlocal
cd /d "%~dp0"
title HandVox - Collect and Train

if not exist ".venv\Scripts\python.exe" goto :setup_required
".venv\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 goto :setup_required
goto :collect

:setup_required
if not exist ".venv\Scripts\python.exe" (
    echo HandVox is not installed yet.
)
echo Opening setup...
call setup.bat
if errorlevel 1 exit /b 1

:collect
echo.
echo ==========================================
echo   Step 1 of 2 - Collect gesture samples
echo ==========================================
echo.
echo Add the new gesture first in gesture_config.py.
echo Existing complete gestures are skipped automatically.
echo.
".venv\Scripts\python.exe" collect_data.py
set "COLLECT_EXIT=%ERRORLEVEL%"
if not "%COLLECT_EXIT%"=="0" goto :collect_failed

echo.
echo ==========================================
echo      Step 2 of 2 - Train the model
echo ==========================================
echo.
".venv\Scripts\python.exe" train_model.py
set "TRAIN_EXIT=%ERRORLEVEL%"
if not "%TRAIN_EXIT%"=="0" goto :train_failed

echo.
echo Complete. Open Run_Detector.bat to test the new gesture.
echo.
pause
exit /b 0

:collect_failed
echo.
echo Collection did not complete. Model training was not started.
echo.
pause
exit /b 1

:train_failed
echo.
echo Training did not complete. Read the message above.
echo.
pause
exit /b 1
