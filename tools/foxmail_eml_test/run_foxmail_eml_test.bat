@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHON_CMD="

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  set PYTHON_CMD="%LocalAppData%\Programs\Python\Python312\python.exe"
  goto :run
)

if exist "%ProgramFiles%\Python312\python.exe" (
  set PYTHON_CMD="%ProgramFiles%\Python312\python.exe"
  goto :run
)

py -3.12 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=py -3.12"
  goto :run
)

python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_CMD=python"
  goto :run
)

echo [ERROR] Python 3.12 was not found.
pause
exit /b 1

:run
%PYTHON_CMD% foxmail_eml_test.py
set "TEST_RC=%ERRORLEVEL%"
echo.
if "%TEST_RC%"=="0" (
  echo Test program completed.
) else (
  echo Test program reported a compatibility problem. Please keep the result file.
)
pause
exit /b %TEST_RC%
