@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co .venv. Xem huong dan trong README.md.
  pause
  exit /b 1
)
echo Dang chay proxy va bot. Ctrl+C de dung. Log hien ben duoi.
".venv\Scripts\python.exe" run_local.py
pause
