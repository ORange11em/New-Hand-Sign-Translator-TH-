@echo off
chcp 65001 >nul
cd /d "%~dp0\..\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "figure_capture_tests\figure_3_2_collect_screen\capture.py" --gesture "สวัสดี" --clip 7
) else (
  py -3.11 "figure_capture_tests\figure_3_2_collect_screen\capture.py" --gesture "สวัสดี" --clip 7
)
if errorlevel 1 pause

