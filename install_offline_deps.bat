@echo off
setlocal
cd /d "%~dp0"

if not exist "wheels" (
  echo [ERROR] Missing wheels folder.
  echo Copy the prepared wheels folder into this directory first.
  pause
  exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info[0] == 3 and sys.version_info[1] >= 8 else 1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.8 or newer is required.
  python --version
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating local virtual environment: .venv
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -m pip install --no-index --find-links=wheels -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" deploy_check.py --mode env
if errorlevel 1 (
  pause
  exit /b 1
)

echo Dependencies installed successfully in .venv.
pause
