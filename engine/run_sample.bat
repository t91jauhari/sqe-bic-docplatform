@echo off
setlocal
cd /d "%~dp0"
if not exist .env (
  copy .env.example .env >nul
  echo Created .env. Edit LLAMA_CLOUD_API_KEY in that file, then run this script again.
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  if errorlevel 1 exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe run.py %*
exit /b %errorlevel%
