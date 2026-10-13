@echo off
chcp 65001 >nul
title Tao Key Hang Loat (Rentry + Link4m)
color 0b

echo =======================================================================
echo          CONG CU TAO KEY HANG LOAT (RENTRY.CO + LINK4M API)
echo =======================================================================
echo.

set "PYTHON_EXE=python"
if exist "C:\Users\A thuy SG\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set "PYTHON_EXE=C:\Users\A thuy SG\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)

set /p count="Nhap so luong Key muon tao (Mac dinh: 5): "
if "%count%"=="" set count=5

set /p prefix="Nhap tien to Key (Mac dinh: MIZZE): "
if "%prefix%"=="" set prefix=MIZZE

echo.
"%PYTHON_EXE%" generate_keys.py %count% %prefix%

echo.
echo =======================================================================
echo  Key da duoc tu dong day len Firebase va san sang cho Bot Telegram!
echo =======================================================================
pause
