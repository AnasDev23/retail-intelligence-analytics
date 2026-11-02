
@echo off
setlocal

cd /d "%~dp0"

echo ==========================================
echo   Retail Intelligence - Project Setup
echo ==========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python was not found in PATH.
    echo Install Python 3.11 or newer from python.org.
    pause
    exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
    echo ERROR: Python 3.11 or newer is required.
    python --version
    pause
    exit /b 1
)

python --version

echo.
echo Creating virtual environment...

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create virtual environment.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo.
echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Pip upgrade failed.
    pause
    exit /b 1
)

echo.
echo Installing project dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)

echo.
echo Downloading official UCI Online Retail II dataset...
python scripts\download_data.py
if errorlevel 1 (
    echo ERROR: Dataset download failed.
    echo Check your internet connection and README instructions.
    pause
    exit /b 1
)

echo.
echo Preparing retail data...
python scripts\prepare_data.py
if errorlevel 1 (
    echo ERROR: Data preparation failed.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   Setup completed successfully!
echo ==========================================
echo.
echo Run run_dashboard.bat to launch the app.
echo.

pause
exit /b 0
