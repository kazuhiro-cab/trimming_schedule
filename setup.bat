@echo off
setlocal

cd /d %~dp0

if not exist .venv (
  echo [INFO] Creating virtual environment at .venv ...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    exit /b 1
  )
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo [ERROR] Failed to activate virtual environment.
  exit /b 1
)

echo [INFO] Upgrading pip ...
python -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip.
  exit /b 1
)

echo [INFO] Installing dependencies from requirements.txt ...
pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies.
  exit /b 1
)

echo [OK] Setup completed.
endlocal
