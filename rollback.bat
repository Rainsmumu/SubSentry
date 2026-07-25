@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

call set_env.bat
call resolve_python.bat
if not defined SUBSENTRY_PYTHON_CMD (
  echo [ERROR] Python 3.12 was not found.
  pause
  exit /b 1
)

set "PORT_IN_USE="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%SUBSENTRY_PORT% .*LISTENING"') do set "PORT_IN_USE=%%P"
if defined PORT_IN_USE (
  echo [ERROR] Stop SubSentry before rollback. Port %SUBSENTRY_PORT% is still in use.
  pause
  exit /b 1
)

%SUBSENTRY_PYTHON_CMD% windows_manage.py backup --root "%SUBSENTRY_ROOT%" --reason rollback
if errorlevel 1 goto :failed
%SUBSENTRY_PYTHON_CMD% windows_manage.py rollback --root "%SUBSENTRY_ROOT%"
if errorlevel 1 goto :failed

echo Rollback completed. Run check_env.bat, then start.bat.
pause
exit /b 0

:failed
echo [ERROR] Rollback failed. Existing data was not removed.
pause
exit /b 1
