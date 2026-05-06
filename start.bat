@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" deploy_check.py --mode start
if errorlevel 1 (
  pause
  exit /b 1
)

echo Starting SubSentry at http://127.0.0.1:8080
echo For LAN access, open http://THIS_COMPUTER_IP:8080 after allowing Windows Firewall.
"%PYTHON_EXE%" app.py
pause
