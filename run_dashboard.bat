
@echo off
setlocal

cd /d "%~dp0"

echo ==========================================
echo   Retail Intelligence Dashboard
echo ==========================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found.
    echo Please run setup_windows.bat first.
    pause
    exit /b 1
)

if not exist "app.py" (
    echo ERROR: app.py not found.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo Starting Streamlit dashboard...
echo.

python -m streamlit run app.py

if errorlevel 1 (
    echo.
    echo ERROR: Dashboard stopped unexpectedly.
    pause
    exit /b 1
)

endlocal
