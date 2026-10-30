@echo off
echo ========================================================
echo   Agentic-Helper: 1-Click Setup for Windows
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in PATH. Please install Python 3.10+ from python.org.
    pause
    exit /b 1
)

echo [1/2] Installing package dependencies...
python -m pip install -e .

echo [2/2] Installing Playwright Chromium engine...
python -m playwright install chromium

echo.
echo ========================================================
echo   Setup Complete!
echo.
echo   How to use in Antigravity IDE:
echo   1. Double-click launch_browser_windows.bat (or open Chrome with port 9222).
echo   2. Navigate to your Coursera/Canvas quiz in that browser.
echo   3. In Antigravity IDE chat, type: /agentic-helper
echo ========================================================
pause
