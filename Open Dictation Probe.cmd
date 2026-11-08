@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo JARVIS Python environment was not found.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 dictation_probe.py
if errorlevel 1 pause
