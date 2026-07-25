@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

call set_env.bat
if not exist "current_version.txt" (
  echo [ERROR] SubSentry is not installed. Run install_offline_deps.bat first.
  pause
  exit /b 1
)
set /p "SUBSENTRY_VERSION="<current_version.txt

set "VERSION_DIR=%SUBSENTRY_ROOT%\versions\%SUBSENTRY_VERSION%"
set "VENV_PYTHON=%VERSION_DIR%\.venv\Scripts\python.exe"
set "WAITRESS=%VERSION_DIR%\.venv\Scripts\waitress-serve.exe"

if not exist "%VENV_PYTHON%" (
  echo [ERROR] Version environment is missing: %SUBSENTRY_VERSION%
  pause
  exit /b 1
)
if not exist "%WAITRESS%" (
  echo [ERROR] Waitress is missing. Reinstall this version.
  pause
  exit /b 1
)

set "PORT_IN_USE="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%SUBSENTRY_PORT% .*LISTENING"') do set "PORT_IN_USE=%%P"
if defined PORT_IN_USE (
  echo [ERROR] Port %SUBSENTRY_PORT% is already in use by PID %PORT_IN_USE%.
  echo Close the other program or contact support before starting SubSentry.
  pause
  exit /b 1
)

pushd "%VERSION_DIR%"
"%VENV_PYTHON%" deploy_check.py --mode start
if errorlevel 1 (
  popd
  pause
  exit /b 1
)

echo.
echo ============================================================
echo SubSentry %SUBSENTRY_VERSION%
echo URL: http://127.0.0.1:%SUBSENTRY_PORT%
echo Keep this window open. Press Ctrl+C to stop the application.
echo ============================================================
echo.
"%WAITRESS%" --listen=%SUBSENTRY_HOST%:%SUBSENTRY_PORT% --threads=4 --channel-timeout=120 app:app
popd

echo.
echo SubSentry has stopped.
pause
