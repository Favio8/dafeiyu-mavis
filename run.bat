@echo off
rem ============================================
rem  DaFeiYu Mavis - launch with the locked local environment
rem ============================================
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo Mavis needs the locked Python environment in .venv.
    echo See docs\SETUP_WINDOWS.md for setup instructions.
    pause
    exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -m assistant --data-home "%~dp0.mavis-local"
