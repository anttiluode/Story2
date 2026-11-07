@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_film_lab_windows.ps1"
if errorlevel 1 (
  echo.
  echo Installation failed. Review the message above.
  pause
)
