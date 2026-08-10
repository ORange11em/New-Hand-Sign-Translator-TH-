@echo off
chcp 65001 >nul
cd /d "%~dp0\..\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "figure_capture_tests\figure_2_1_landmarks\capture.py"
) else (
  py -3.11 "figure_capture_tests\figure_2_1_landmarks\capture.py"
)
if errorlevel 1 pause

