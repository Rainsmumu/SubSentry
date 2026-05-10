@echo off
setlocal
cd /d "%~dp0"

call resolve_python.bat
if not defined SUBSENTRY_PYTHON (
  echo [ERROR] Python 3.8 or newer is required.
  echo If this computer only has Python 3.6, run install_python_312.bat first.
  pause
  exit /b 1
)

%SUBSENTRY_PYTHON% deploy_check.py --mode start
if errorlevel 1 (
  pause
  exit /b 1
)

echo Starting SubSentry at http://127.0.0.1:8080
echo For LAN access, open http://THIS_COMPUTER_IP:8080 after allowing Windows Firewall.
%SUBSENTRY_PYTHON% app.py
pause
