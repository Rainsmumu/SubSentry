@echo off
setlocal
cd /d "%~dp0"

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.8 or newer is required.
  echo Current Python:
  python --version
  pause
  exit /b 1
)

if not exist "金桥机房电路表.xlsx" (
  echo [ERROR] Missing data file: 金桥机房电路表.xlsx
  echo Please put it in this folder before starting SubSentry.
  pause
  exit /b 1
)

echo Starting SubSentry at http://127.0.0.1:8080
echo For LAN access, open http://THIS_COMPUTER_IP:8080 after allowing Windows Firewall.
python app.py
pause
