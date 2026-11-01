@echo off
setlocal enabledelayedexpansion
echo ========================================================
echo   Agentic-Helper: Windows Browser Launcher (Chrome)
echo   Launches Google Chrome on remote debugging port 9222
echo   and VERIFIES the browser is actually responding.
echo ========================================================
echo.

REM Persistent profile: NOT %TEMP% (Windows cleanup wipes TEMP and the
REM saved Coursera login with it). This folder survives reboots.
set USER_DIR=%LOCALAPPDATA%\AgenticHelper\browser-profile
set TARGET_URL=https://www.coursera.org
if not "%~1"=="" set TARGET_URL=%~1

set BROWSER_EXE=

REM 1. Google Chrome FIRST (supported browser). Edge is only a fallback:
REM    Edge's "Startup Boost" background process can swallow the launch
REM    so that no visible window ever appears.
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

REM 2. Fallbacks only if Chrome is not installed
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
    set "BROWSER_NAME=Microsoft Edge (fallback - Chrome not found)"
    goto found
)
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
    set "BROWSER_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
    set "BROWSER_NAME=Microsoft Edge x86 (fallback - Chrome not found)"
    goto found
)
if exist "%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BROWSER_EXE=%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"
    set "BROWSER_NAME=Brave Browser (fallback - Chrome not found)"
    goto found
)
if exist "%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe" (
    set "BROWSER_EXE=%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
    set "BROWSER_NAME=Brave Browser User Install (fallback - Chrome not found)"
    goto found
)

REM 3. Fallback via PATH lookup
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

echo [ERROR] No supported Chromium-based browser (Chrome preferred) found.
echo Please install Google Chrome.
pause
exit /b 1

:found
echo [OK] Detected: !BROWSER_NAME!
echo [*] Launching on remote debugging port 9222...

REM Already running? Just report it (the Python launcher raises its window).
curl -s -o nul http://127.0.0.1:9222/json/version && (
    echo [OK] A browser is already listening on port 9222.
    echo      If its window is hidden, run:  python -m quiz_pilot.browser_launcher "%TARGET_URL%"
    exit /b 0
)

start "" /MAX "!BROWSER_EXE!" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="%USER_DIR%" --new-window --start-maximized --no-first-run --no-default-browser-check "%TARGET_URL%"

REM VERIFY: do not claim success blindly (the old version printed
REM "started successfully" even when no window/process existed).
REM Poll the CDP endpoint for up to ~20 seconds.
set TRIES=0
:verify
set /a TRIES+=1
curl -s -o nul http://127.0.0.1:9222/json/version && goto verified
if !TRIES! geq 40 goto failed
timeout /t 1 /nobreak >nul
goto verify

:verified
REM Best effort: activate the first tab over CDP.
for /f "tokens=2 delims=:" %%i in ('curl -s http://127.0.0.1:9222/json/list ^| findstr /C:"\"id\":"') do (
    set FIRST_ID=%%i
    goto activate
)
:activate
if defined FIRST_ID (
    set FIRST_ID=!FIRST_ID:"=!
    set FIRST_ID=!FIRST_ID:,=!
    set FIRST_ID=!FIRST_ID: =!
    curl -s http://127.0.0.1:9222/json/activate/!FIRST_ID! >nul 2>nul
)
echo.
echo ========================================================
echo   Browser VERIFIED on http://127.0.0.1:9222
echo   (!BROWSER_NAME!, profile: %USER_DIR%)
echo ========================================================
exit /b 0

:failed
echo.
echo [ERROR] Browser process was started but port 9222 did not respond
echo within 20 seconds. Common causes: antivirus blocked the launch
echo (add this project folder as an antivirus exclusion) or the browser
echo is set to run only in the background (Edge Startup Boost).
echo Nothing was "successfully started" - please check and retry.
pause
exit /b 1
