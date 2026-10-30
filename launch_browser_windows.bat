@echo off
echo ========================================================
echo   Agentic-Helper: Windows Browser Launcher (Port 9222)
echo ========================================================
echo.

set USER_DIR=%TEMP%\agent_browser

REM 1. Try Google Chrome 64-bit
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    echo Launching Google Chrome on port 9222...
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USER_DIR%"
    goto done
)

REM 2. Try Google Chrome 32-bit
if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    echo Launching Google Chrome (x86) on port 9222...
    start "" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USER_DIR%"
    goto done
)

REM 3. Try Microsoft Edge
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    echo Launching Microsoft Edge on port 9222...
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="%USER_DIR%"
    goto done
)

echo ERROR: Neither Google Chrome nor Microsoft Edge was found in standard locations.
echo Please install Google Chrome or Microsoft Edge.
pause

:done
echo.
echo Browser started successfully with remote debugging on http://127.0.0.1:9222!
echo You can now run your AI agent in Antigravity or Cursor.
echo ========================================================
