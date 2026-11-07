@echo off
setlocal
cd /d "%~dp0"
if exist ".film-venv\Scripts\python.exe" (
    ".film-venv\Scripts\python.exe" tools\film_lab_gui.py
) else (
    echo Film Lab AI environment is not installed yet.
    echo Run install_film_lab.bat once to install CUDA PyTorch and DreamShaper 8.
    echo Trying existing Python for graphic mode or already-installed AI models...
    py -3.13 tools\film_lab_gui.py
)
if errorlevel 1 (
    echo.
    echo Check the errors above. For the one-time installer, run install_film_lab.bat.
    pause
)
