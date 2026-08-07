@echo off
setlocal
cd /d "%~dp0"
title HandVox - Developer Tools

if not exist ".venv\Scripts\python.exe" goto :setup_required
".venv\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 goto :setup_required
goto :menu

:setup_required
echo HandVox is not installed yet. Opening setup...
call setup.bat
if errorlevel 1 exit /b 1

:menu
cls
echo.
echo ==========================================
echo          HandVox - Developer Tools
echo ==========================================
echo.
echo  [1] Start sign detection
echo  [2] Train legacy 4-gesture model
echo  [3] Collect legacy gesture samples
echo  [4] Install or repair packages
echo  [5] Add a legacy gesture (collect and train)
echo  [6] Remove a legacy gesture (backup and train)
echo  [7] Check Dataset V2 training readiness
echo  [8] Train, evaluate, and create V2 report
echo  [0] Exit
echo.
set /p "choice=Select an option: "

if "%choice%"=="1" goto :detect
if "%choice%"=="2" goto :train
if "%choice%"=="3" goto :collect
if "%choice%"=="4" goto :setup
if "%choice%"=="5" goto :add_gesture
if "%choice%"=="6" goto :remove_gesture
if "%choice%"=="7" goto :v2_status
if "%choice%"=="8" goto :v2_train
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

:add_gesture
call Add_New_Gesture.bat
goto :menu

:remove_gesture
call Remove_Gesture.bat
goto :menu

:v2_status
".venv\Scripts\python.exe" training_cli.py status
pause
goto :menu

:v2_train
".venv\Scripts\python.exe" training_cli.py train
pause
goto :menu
