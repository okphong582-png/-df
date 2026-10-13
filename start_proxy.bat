@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co .venv. Xem huong dan trong README.md.
  pause
  exit /b 1
)
echo Mo MITMDump Server va Bore Public Tunnel. Khong can tu mo MITM lan nua.
".venv\Scripts\python.exe" run_local.py --proxy-only --show-windows
pause
