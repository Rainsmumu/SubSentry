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

%SUBSENTRY_PYTHON_CMD% windows_manage.py backup --root "%SUBSENTRY_ROOT%" --reason manual
if errorlevel 1 (
  echo [ERROR] Backup failed.
  pause
  exit /b 1
)

echo Backup completed.
pause
