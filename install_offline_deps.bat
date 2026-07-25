@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

call set_env.bat
call resolve_python.bat
if not defined SUBSENTRY_PYTHON_CMD (
  echo [ERROR] Python 3.12 64-bit is required.
  echo Run install_python_312.bat first.
  pause
  exit /b 1
)

if not exist "PACKAGE_VERSION.txt" (
  echo [ERROR] Missing PACKAGE_VERSION.txt.
  pause
  exit /b 1
)
set /p "SUBSENTRY_VERSION="<PACKAGE_VERSION.txt

set "VERSION_DIR=%SUBSENTRY_ROOT%\versions\%SUBSENTRY_VERSION%"
set "VENV_PYTHON=%VERSION_DIR%\.venv\Scripts\python.exe"

if not exist "%VERSION_DIR%\app.py" (
  echo [ERROR] Version files are missing: %VERSION_DIR%
  pause
  exit /b 1
)
if not exist "wheels" (
  echo [ERROR] Missing offline wheels folder.
  pause
  exit /b 1
)

if not exist "%VENV_PYTHON%" (
  echo Creating isolated environment for %SUBSENTRY_VERSION%...
  %SUBSENTRY_PYTHON_CMD% -m venv "%VERSION_DIR%\.venv"
  if errorlevel 1 goto :failed
)

echo Installing dependencies without network access...
"%VENV_PYTHON%" -m pip install --no-index --find-links="%SUBSENTRY_ROOT%\wheels" -r "%VERSION_DIR%\requirements.txt"
if errorlevel 1 goto :failed

%SUBSENTRY_PYTHON_CMD% windows_manage.py initialize ^
  --root "%SUBSENTRY_ROOT%" ^
  --version "%SUBSENTRY_VERSION%" ^
  --bootstrap-source "%SUBSENTRY_DEFAULT_SOURCE%" ^
  --bootstrap-reference "%SUBSENTRY_ROOT%\bootstrap\reference"
if errorlevel 1 goto :failed

pushd "%VERSION_DIR%"
"%VENV_PYTHON%" deploy_check.py --mode env
if errorlevel 1 (
  popd
  goto :failed
)
"%VENV_PYTHON%" -m unittest discover -s tests
if errorlevel 1 (
  popd
  goto :failed
)
popd

%SUBSENTRY_PYTHON_CMD% windows_manage.py activate ^
  --root "%SUBSENTRY_ROOT%" ^
  --version "%SUBSENTRY_VERSION%"
if errorlevel 1 goto :failed

echo.
echo Installation completed successfully.
echo Start SubSentry with start.bat.
pause
exit /b 0

:failed
echo.
echo [ERROR] Offline installation failed. No existing version or data was removed.
pause
exit /b 1
