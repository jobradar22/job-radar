@echo off
REM ---- JobRadar launcher for Windows ----
cd /d "%~dp0"

if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
)

call .venv\Scripts\activate.bat
echo Installing/updating dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo Starting JobRadar...
python -m app.main
pause
