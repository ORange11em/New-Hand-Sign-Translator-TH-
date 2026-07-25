@echo off
setlocal
cd /d "%~dp0"
title HandVox - Sign Language Translator

if not exist ".venv\Scripts\python.exe" goto :setup_required
".venv\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 goto :setup_required
goto :menu

:setup_required
if not exist ".venv\Scripts\python.exe" (
    echo HandVox is not installed yet.
)
echo Opening setup...
call setup.bat
if errorlevel 1 exit /b 1

:menu
cls
echo.
echo ==========================================
echo       HandVox - Sign Language Translator
echo ==========================================
echo.
echo  [1] Start sign detection
echo  [2] Train model with current data
echo  [3] Collect gesture samples
echo  [4] Install or repair packages
echo  [0] Exit
echo.
set /p "choice=Select an option: "

if "%choice%"=="1" goto :detect
if "%choice%"=="2" goto :train
if "%choice%"=="3" goto :collect
if "%choice%"=="4" goto :setup
if "%choice%"=="0" exit /b 0

echo Invalid option.
timeout /t 2 /nobreak >nul
goto :menu

:detect
".venv\Scripts\python.exe" run_detector.py
pause
goto :menu

:train
".venv\Scripts\python.exe" train_model.py
pause
goto :menu

:collect
".venv\Scripts\python.exe" collect_data.py
pause
goto :menu

:setup
call setup.bat
goto :menu
