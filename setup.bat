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

echo [2/2] Verifying Playwright browser engines...
python -m playwright install chromium

echo.
echo ========================================================
echo   Setup Complete!
echo.
echo   Compatible with ANY browser installed on your machine:
echo   - Microsoft Edge (Default on Windows 10/11)
echo   - Google Chrome
echo   - Brave / Vivaldi / Opera
echo.
echo   How to use:
echo   1. Double-click launch_browser_windows.bat (or open Edge/Chrome with port 9222).
echo   2. Navigate to your Coursera/Canvas quiz in that browser.
echo   3. In Antigravity / Cursor chat, type: /agentic-helper
echo ========================================================
pause
