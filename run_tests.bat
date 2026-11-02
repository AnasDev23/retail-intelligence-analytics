
@echo off
setlocal

cd /d "%~dp0"

echo ==========================================
echo   Retail Intelligence - Test Suite
echo ==========================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found.
    echo Please run setup_windows.bat first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo Running pytest...
echo.

python -m pytest tests -v

set "TEST_EXIT_CODE=%ERRORLEVEL%"

echo.
if "%TEST_EXIT_CODE%"=="0" (
    echo All tests passed!
) else (
    echo Some tests failed. Check the output above.
)

pause
exit /b %TEST_EXIT_CODE%
