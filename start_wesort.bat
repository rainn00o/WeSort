@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [WeSort] Missing virtual environment: .venv\Scripts\python.exe
    echo Please create the venv and install dependencies first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [WeSort] Program exited with code: %EXIT_CODE%
    pause
)

endlocal
