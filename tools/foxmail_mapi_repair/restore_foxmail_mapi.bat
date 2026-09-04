@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "BACKUP_DIR=%~dp0registry_backup"

echo Restore the original Foxmail Simple MAPI registration
echo.

if not exist "%BACKUP_DIR%\Foxmail_HKLM_64.reg" goto :missing
if not exist "%BACKUP_DIR%\Foxmail_HKLM_32.reg" goto :missing

echo Right-click this BAT and select "Run as administrator".
choice /C YN /N /M "Restore the original registry values? [Y/N]: "
if errorlevel 2 exit /b 0

reg import "%BACKUP_DIR%\Foxmail_HKLM_64.reg"
if errorlevel 1 goto :failed
reg import "%BACKUP_DIR%\Foxmail_HKLM_32.reg"
if errorlevel 1 goto :failed

echo.
echo [OK] The original Foxmail registry values were restored.
echo Restart Foxmail before testing again.
pause
exit /b 0

:missing
echo [ERROR] The original registry backup files were not found.
echo No registry value was changed.
pause
exit /b 1

:failed
echo [ERROR] Restore failed. Run this BAT as administrator and try again.
pause
exit /b 1
