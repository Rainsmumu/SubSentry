@echo off
set "SUBSENTRY_PYTHON="

if exist ".venv\Scripts\python.exe" (
  set "SUBSENTRY_PYTHON=.venv\Scripts\python.exe"
  exit /b 0
)

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  set "SUBSENTRY_PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
  exit /b 0
)

if exist "%ProgramFiles%\Python312\python.exe" (
  set "SUBSENTRY_PYTHON=%ProgramFiles%\Python312\python.exe"
  exit /b 0
)

if exist "%ProgramFiles(x86)%\Python312-32\python.exe" (
  set "SUBSENTRY_PYTHON=%ProgramFiles(x86)%\Python312-32\python.exe"
  exit /b 0
)

py -3.12 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "SUBSENTRY_PYTHON=py -3.12"
  exit /b 0
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "SUBSENTRY_PYTHON=python"
  exit /b 0
)

exit /b 1
