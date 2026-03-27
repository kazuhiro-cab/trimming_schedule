@echo off
setlocal

cd /d %~dp0

if not exist .venv\Scripts\python.exe (
  echo [ERROR] Virtual environment not found.
  echo [HINT] Run setup.bat first.
  exit /b 1
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo [ERROR] Failed to activate virtual environment.
  exit /b 1
)

echo [INFO] Starting Streamlit app ...
python -m streamlit run app.py

endlocal
