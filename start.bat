@echo off
setlocal
cd /d "%~dp0"

set "BASE_PY=C:\venv\python3_12_10\python.exe"
set "PIP_CACHE_DIR=%CD%\.pip-cache"
if not exist ".tmp" mkdir ".tmp"
set "TEMP=%CD%\.tmp"
set "TMP=%CD%\.tmp"

if not exist ".venv\Scripts\python.exe" (
  if not exist "%BASE_PY%" (
    echo Python nicht gefunden: %BASE_PY%
    pause
    exit /b 1
  )
  "%BASE_PY%" -m venv ".venv"
  if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
  ".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
  if errorlevel 1 goto :error
)

".venv\Scripts\pythonw.exe" "app.py"
exit /b %errorlevel%

:error
echo Einrichtung fehlgeschlagen. Details stehen oben.
pause
exit /b 1
