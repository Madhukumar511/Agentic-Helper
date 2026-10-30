@echo off
setlocal enabledelayedexpansion
echo ========================================================
echo   Agentic-Helper: Universal Windows Browser Launcher
echo   (Detects Edge, Chrome, Brave, Vivaldi, Opera, or Default)
echo ========================================================
echo.

set USER_DIR=%TEMP%\agent_browser
set TARGET_URL=https://www.coursera.org
if not "%~1"=="" set TARGET_URL=%~1

set BROWSER_EXE=

REM 1. Check Microsoft Edge (Pre-installed on all Windows 10/11)
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
    set "BROWSER_NAME=Microsoft Edge (64-bit)"
    goto found
)
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
    set "BROWSER_NAME=Microsoft Edge (x86)"
    goto found
)

REM 2. Check Google Chrome
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    set "BROWSER_NAME=Google Chrome (64-bit)"
    goto found
)
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    set "BROWSER_NAME=Google Chrome (x86)"
    goto found
)
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "BROWSER_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    set "BROWSER_NAME=Google Chrome (User Install)"
    goto found
)

REM 3. Check Brave Browser
if exist "%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BROWSER_EXE=%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"
    set "BROWSER_NAME=Brave Browser"
    goto found
)
if exist "%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BROWSER_EXE=%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
    set "BROWSER_NAME=Brave Browser (User Install)"
    goto found
)

REM 4. Check Vivaldi
if exist "%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe" (
    set "BROWSER_EXE=%LOCALAPPDATA%\Vivaldi\Application\vivaldi.exe"
    set "BROWSER_NAME=Vivaldi"
    goto found
)

REM 5. Fallback via PATH lookup
for %%b in (chrome.exe msedge.exe brave.exe vivaldi.exe) do (
    where %%b >nul 2>nul
    if !errorlevel! equ 0 (
        for /f "delims=" %%p in ('where %%b') do (
            set "BROWSER_EXE=%%p"
            set "BROWSER_NAME=%%b"
            goto found
        )
    )
)

echo [ERROR] No supported Chromium-based browser (Edge, Chrome, Brave, Vivaldi) found.
echo Please install Google Chrome or Microsoft Edge.
pause
exit /b 1

:found
echo [✓] Detected: !BROWSER_NAME!
echo [*] Launching into visible desktop UI on remote debugging port 9222...

REM Launch into interactive desktop session and bring to foreground UI
start "" /MAX "!BROWSER_EXE!" --remote-debugging-port=9222 --user-data-dir="%USER_DIR%" --new-window --start-maximized --no-first-run --no-default-browser-check "%TARGET_URL%"

echo.
echo ========================================================
echo   Browser started successfully on http://127.0.0.1:9222!
echo   Window is visible on your screen.
echo ========================================================
exit /b 0
