@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
:menu
cls
echo ==============================================
echo       HandVox - เครื่องมือเก็บภาพรายงาน
echo ==============================================
echo 1. ภาพที่ 2.1 จุดสำคัญ MediaPipe
echo 2. ภาพที่ 2.2 ลำดับ 30 เฟรม
echo 3. ภาพที่ 3.1 สถาปัตยกรรม
echo 4. ภาพที่ 3.2 หน้าจอเก็บคลิปจำลอง
echo 5. ภาพที่ 4.1 Confusion Matrix
echo 6. ภาพที่ 4.2 หน้าจอภาพรวมระบบ
echo 0. ออก
echo.
set /p choice=เลือกหมายเลข: 
if "%choice%"=="1" call "figure_2_1_landmarks\run.bat"
if "%choice%"=="2" call "figure_2_2_sequence\run.bat"
if "%choice%"=="3" call "figure_3_1_architecture\run.bat"
if "%choice%"=="4" call "figure_3_2_collect_screen\run.bat"
if "%choice%"=="5" call "figure_4_1_confusion_matrix\run.bat"
if "%choice%"=="6" call "figure_4_2_system_ui\run.bat"
if "%choice%"=="0" exit /b 0
pause
goto menu
