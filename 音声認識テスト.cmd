@echo off
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
  echo Python virtual environment not found. See README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 voice_live.py
pause
