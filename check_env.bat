@echo off
setlocal
cd /d "%~dp0"

echo === Python ===
python --version
echo.

echo === Required modules ===
python -c "import flask, openpyxl; print('Flask', flask.__version__); print('openpyxl', openpyxl.__version__)"
if errorlevel 1 (
  echo.
  echo [ERROR] Flask/openpyxl is not available. Run install_offline_deps.bat first.
  pause
  exit /b 1
)

echo.
echo Environment check passed.
pause
