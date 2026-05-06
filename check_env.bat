@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" deploy_check.py --mode env
) else (
  python deploy_check.py --mode env
)
if errorlevel 1 (
  pause
  exit /b 1
)

pause
