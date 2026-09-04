@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "NEW_DLL=D:\Program Files\Foxmail 7.2\7.2.25.563\FMMAPI32.dll"
set "KEY64=HKLM\SOFTWARE\Clients\Mail\Foxmail"
set "KEY32=HKLM\SOFTWARE\WOW6432Node\Clients\Mail\Foxmail"
set "BACKUP_DIR=%~dp0registry_backup"

echo Foxmail Simple MAPI registration repair
echo.
echo New DLLPath:
echo %NEW_DLL%
echo.

if not exist "%NEW_DLL%" (
  echo [ERROR] The new Foxmail MAPI DLL was not found.
  echo No registry value was changed.
  pause
  exit /b 1
)

if exist "%BACKUP_DIR%\Foxmail_HKLM_64.reg" (
  echo [ERROR] A registry backup already exists in:
  echo %BACKUP_DIR%
  echo No registry value was changed. Keep the existing backup for rollback.
  pause
  exit /b 1
)

echo This tool will back up both Foxmail registry keys before changing DLLPath.
echo Right-click this BAT and select "Run as administrator".
choice /C YN /N /M "Continue? [Y/N]: "
if errorlevel 2 exit /b 0

mkdir "%BACKUP_DIR%" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Could not create the backup directory.
  pause
  exit /b 1
)

reg export "%KEY64%" "%BACKUP_DIR%\Foxmail_HKLM_64.reg" /y >nul
if errorlevel 1 goto :backup_failed

reg export "%KEY32%" "%BACKUP_DIR%\Foxmail_HKLM_32.reg" /y >nul
if errorlevel 1 goto :backup_failed

reg add "%KEY64%" /v DLLPath /t REG_SZ /d "%NEW_DLL%" /f >nul
if errorlevel 1 goto :repair_failed

reg add "%KEY32%" /v DLLPath /t REG_SZ /d "%NEW_DLL%" /f >nul
if errorlevel 1 goto :repair_failed

echo.
echo [OK] Foxmail MAPI DLLPath was updated after a successful backup.
echo Backup directory:
echo %BACKUP_DIR%
echo.
reg query "%KEY64%" /v DLLPath
reg query "%KEY32%" /v DLLPath
echo.
echo Restart Foxmail, then run the r2 compatibility test again.
pause
exit /b 0

:backup_failed
echo.
echo [ERROR] Registry backup failed. No registry value was changed.
echo Try again by right-clicking this BAT and selecting "Run as administrator".
pause
exit /b 1

:repair_failed
echo.
echo [ERROR] Registry update failed. Attempting automatic rollback...
reg import "%BACKUP_DIR%\Foxmail_HKLM_64.reg" >nul 2>nul
reg import "%BACKUP_DIR%\Foxmail_HKLM_32.reg" >nul 2>nul
echo Rollback commands completed. Keep the registry_backup folder.
pause
exit /b 1
