@echo off
setlocal
cd /d "%~dp0"

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.8 or newer is required.
  python --version
  pause
  exit /b 1
)

if not exist "wheels" (
  echo [ERROR] Missing wheels folder.
  echo Copy the prepared wheels folder into this directory first.
  pause
  exit /b 1
)

python -m pip install --no-index --find-links=wheels -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  pause
  exit /b 1
)

echo Dependencies installed successfully.
pause
