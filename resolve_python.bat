@echo off
set "SUBSENTRY_PYTHON_CMD="

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  set SUBSENTRY_PYTHON_CMD="%LocalAppData%\Programs\Python\Python312\python.exe"
  exit /b 0
)

if exist "%ProgramFiles%\Python312\python.exe" (
  set SUBSENTRY_PYTHON_CMD="%ProgramFiles%\Python312\python.exe"
  exit /b 0
)

py -3.12 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "SUBSENTRY_PYTHON_CMD=py -3.12"
  exit /b 0
)

python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "SUBSENTRY_PYTHON_CMD=python"
  exit /b 0
)

exit /b 1
