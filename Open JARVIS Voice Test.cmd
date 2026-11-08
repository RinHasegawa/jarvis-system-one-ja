@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo JARVIS could not find its Python environment. Please contact Codex for help.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0jarvis_voice_app.py"
