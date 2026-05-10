@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_INSTALLER=python-installer\python-3.12.10-amd64.exe"

if not exist "%PYTHON_INSTALLER%" (
  echo [ERROR] Missing Python installer: %PYTHON_INSTALLER%
  echo Please download the release package that includes python-installer.
  pause
  exit /b 1
)

echo Installing Python 3.12.10 for current user...
echo This may take a few minutes.
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
if errorlevel 1 (
  echo [ERROR] Python installer failed.
  pause
  exit /b 1
)

call resolve_python.bat
if not defined SUBSENTRY_PYTHON (
  echo [ERROR] Python 3.12 was installed, but this script cannot find it.
  echo Close this window and open a new command window, then run check_env.bat.
  pause
  exit /b 1
)

echo Installed Python:
%SUBSENTRY_PYTHON% --version
echo.
echo Python installation finished. Next, run install_offline_deps.bat.
pause
