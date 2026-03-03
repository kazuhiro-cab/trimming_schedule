@echo off
setlocal

if not exist .venv\Scripts\activate.bat (
  echo .venv is missing. Run setup.bat first.
  exit /b 1
)

call .venv\Scripts\activate.bat
streamlit run app.py

endlocal
