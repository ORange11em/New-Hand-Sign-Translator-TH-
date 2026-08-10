@echo off
chcp 65001 >nul
cd /d "%~dp0\..\.."
py -3.11 "figure_capture_tests\figure_3_1_architecture\export.py"
if errorlevel 1 pause

