@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.13 tools\film_lab_gui.py
) else (
  python tools\film_lab_gui.py
)
if errorlevel 1 (
  echo Install Pillow: py -3.13 -m pip install -r requirements-video.txt
  pause
)
