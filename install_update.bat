@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "SUBSENTRY_ROOT=E:\SubSentry"
if not "%~1"=="" set "SUBSENTRY_ROOT=%~f1"

if not exist "%SUBSENTRY_ROOT%\current_version.txt" (
  echo [ERROR] Existing SubSentry installation was not found at:
  echo %SUBSENTRY_ROOT%
  echo For first installation, use the complete offline package.
  pause
  exit /b 1
)
if not exist "PACKAGE_VERSION.txt" (
  echo [ERROR] Missing PACKAGE_VERSION.txt.
  pause
  exit /b 1
)
set /p "SUBSENTRY_VERSION="<PACKAGE_VERSION.txt

call "%SUBSENTRY_ROOT%\set_env.bat"
call "%SUBSENTRY_ROOT%\resolve_python.bat"
if not defined SUBSENTRY_PYTHON_CMD (
  echo [ERROR] Python 3.12 was not found.
  pause
  exit /b 1
)

set "PORT_IN_USE="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%SUBSENTRY_PORT% .*LISTENING"') do set "PORT_IN_USE=%%P"
if defined PORT_IN_USE (
  echo [ERROR] Stop SubSentry before updating. Port %SUBSENTRY_PORT% is still in use.
  pause
  exit /b 1
)

set "TARGET_DIR=%SUBSENTRY_ROOT%\versions\%SUBSENTRY_VERSION%"
if exist "%TARGET_DIR%" (
  echo [ERROR] Version directory already exists:
  echo %TARGET_DIR%
  echo Use a new version number or remove only the failed version after review.
  pause
  exit /b 1
)

%SUBSENTRY_PYTHON_CMD% windows_manage.py backup --root "%SUBSENTRY_ROOT%" --reason update-%SUBSENTRY_VERSION%
if errorlevel 1 goto :failed

echo Copying complete application version...
xcopy "app" "%TARGET_DIR%\" /E /I /H /Y >nul
if errorlevel 1 goto :failed

echo Creating isolated version environment...
%SUBSENTRY_PYTHON_CMD% -m venv "%TARGET_DIR%\.venv"
if errorlevel 1 goto :failed

set "VENV_PYTHON=%TARGET_DIR%\.venv\Scripts\python.exe"
"%VENV_PYTHON%" -m pip install --no-index --find-links="%~dp0wheels" -r "%TARGET_DIR%\requirements.txt"
if errorlevel 1 goto :failed

pushd "%TARGET_DIR%"
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

echo Updating management scripts...
xcopy "root_files" "%SUBSENTRY_ROOT%\" /E /I /H /Y >nul
if errorlevel 1 goto :failed

%SUBSENTRY_PYTHON_CMD% "%SUBSENTRY_ROOT%\windows_manage.py" activate --root "%SUBSENTRY_ROOT%" --version "%SUBSENTRY_VERSION%"
if errorlevel 1 goto :failed

echo.
echo Update installed successfully: %SUBSENTRY_VERSION%
echo Run check_env.bat, then start.bat.
pause
exit /b 0

:failed
echo.
echo [ERROR] Update failed. The previous active version and data were preserved.
echo Review the error before deleting any files.
pause
exit /b 1
