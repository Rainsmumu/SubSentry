@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_INSTALLER=python-installer\python-3.12.10-amd64.exe"

if not exist "%PYTHON_INSTALLER%" (
  echo [ERROR] Missing Python installer: %PYTHON_INSTALLER%
  echo Please use the complete Windows offline package.
  pause
  exit /b 1
)

echo Installing Python 3.12.10 64-bit for the current Windows user...
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=0 Include_pip=1 Include_launcher=1 Include_test=0
if errorlevel 1 (
  echo [ERROR] Python installer failed. Contact desktop support if security software blocked it.
  pause
  exit /b 1
)

call resolve_python.bat
if not defined SUBSENTRY_PYTHON_CMD (
  echo [ERROR] Python 3.12 was installed but could not be located.
  echo Close this window and run check_env.bat again.
  pause
  exit /b 1
)

echo Installed Python:
%SUBSENTRY_PYTHON_CMD% --version
echo.
echo Next step: run install_offline_deps.bat.
pause
