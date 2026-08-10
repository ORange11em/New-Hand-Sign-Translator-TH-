@echo off
chcp 65001 >nul
cd /d "%~dp0\..\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "figure_capture_tests\figure_4_1_confusion_matrix\generate.py"
) else (
  py -3.11 "figure_capture_tests\figure_4_1_confusion_matrix\generate.py"
)
if errorlevel 1 pause

