@echo off
setlocal
cd /d "%~dp0"

if not exist "wheels" (
  echo [ERROR] Missing wheels folder.
  echo Copy the prepared wheels folder into this directory first.
  pause
  exit /b 1
)

call resolve_python.bat
if not defined SUBSENTRY_PYTHON (
  echo [ERROR] Python 3.8 or newer is required.
  echo If this computer only has Python 3.6, run install_python_312.bat first.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating local virtual environment: .venv
  %SUBSENTRY_PYTHON% -m venv .venv
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
