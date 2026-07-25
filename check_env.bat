@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

call set_env.bat
call resolve_python.bat
if not defined SUBSENTRY_PYTHON_CMD (
  echo [ERROR] Python 3.12 64-bit was not found.
  pause
  exit /b 1
)

echo === System Python ===
%SUBSENTRY_PYTHON_CMD% --version
%SUBSENTRY_PYTHON_CMD% -c "import struct,sys; print('Architecture:', struct.calcsize('P')*8, 'bit'); sys.exit(0 if struct.calcsize('P')*8 == 64 else 1)"
if errorlevel 1 (
  echo [ERROR] 64-bit Python is required.
  pause
  exit /b 1
)

if not exist "current_version.txt" (
  echo.
  echo SubSentry has not been installed yet.
  pause
  exit /b 0
)
set /p "SUBSENTRY_VERSION="<current_version.txt
set "VERSION_DIR=%SUBSENTRY_ROOT%\versions\%SUBSENTRY_VERSION%"
set "VENV_PYTHON=%VERSION_DIR%\.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
  echo [ERROR] Current version environment is missing: %SUBSENTRY_VERSION%
  pause
  exit /b 1
)

pushd "%VERSION_DIR%"
"%VENV_PYTHON%" deploy_check.py --mode env
set "CHECK_RC=%ERRORLEVEL%"
popd

%SUBSENTRY_PYTHON_CMD% windows_manage.py status --root "%SUBSENTRY_ROOT%"
pause
exit /b %CHECK_RC%
