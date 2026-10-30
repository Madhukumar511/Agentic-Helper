# WINDOWS_GUIDE.md — Complete Windows Setup & User Guide 🪟

This guide explains how to install, configure, and run **Agentic-Helper** on **Windows 10 / Windows 11**, with **Google Chrome** or **Microsoft Edge**, and use it inside **Antigravity IDE**, **Cursor**, or **CLI**.

---

## ⚡ 1. Prerequisites on Windows

1. **Python 3.10+**: Download from [python.org](https://www.python.org/) or install via winget:
   ```powershell
   winget install Python.Python.3.12
   ```
   *(Make sure to check "Add Python to PATH" during installation!)*
2. **Google Chrome** or **Microsoft Edge** (pre-installed on Windows).
3. **Git**:
   ```powershell
   winget install Git.Git
   ```

---

## 🚀 2. Installation (PowerShell)

Open **PowerShell** and run:

```powershell
# 1. Clone the repository
git clone https://github.com/Madhukumar511/Agentic-Helper.git
cd Agentic-Helper

# 2. Allow script execution in current PowerShell session (if restricted)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 3. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 4. Install Agentic-Helper in editable mode
pip install -e .

# 5. Install Playwright browser drivers
playwright install chromium
```

---

## 🌐 3. Launching Browser with Remote Debugging (Port 9222)

To allow AI agents to connect without needing passwords or login APIs, launch your browser with the remote debugging port enabled.

### Option A: Using Google Chrome
In PowerShell:
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\tmp\agent_browser"
```

### Option B: Using Microsoft Edge
In PowerShell:
```powershell
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\tmp\agent_browser"
```

### Option C: One-Click Batch File (`launch_browser.bat`)
Double-click `launch_browser_windows.bat` in the repository root, or create one with:
```bat
@echo off
echo Starting Chrome with remote debugging on port 9222...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%TEMP%\agent_browser"
```

> **Tip:** You only need to log in to Coursera, Canvas, or Moodle **once**. Your login session is saved in the directory!

---

## 🤖 4. How Other Agents Use Agentic-Helper on Windows

### A. Antigravity IDE (Windows)
1. Copy the skill file to your global Antigravity skills directory:
   ```powershell
   mkdir -p "$env:USERPROFILE\.agents\skills\agentic-helper"
   Copy-Item "SKILL.md" "$env:USERPROFILE\.agents\skills\agentic-helper\SKILL.md"
   ```
2. In Antigravity IDE Chat, type:
   ```text
   /agentic-helper
   ```
   Or ask: *"Please solve the current quiz in my browser."*
3. Antigravity connects to your open browser, reads the questions, solves them, and submits!

---

### B. Cursor IDE (Windows)
1. Open Cursor Settings -> Features -> **MCP Servers**.
2. Or edit `%USERPROFILE%\.cursor\mcp.json`:
   ```json
   {
     "mcpServers": {
       "agentic-helper": {
         "command": "cmd.exe",
         "args": ["/c", "python -m quiz_pilot.mcp_server"],
         "cwd": "C:\\path\\to\\Agentic-Helper"
       }
     }
   }
   ```
3. In Cursor Composer / Chat, type:
   > *"Extract questions using agentic-helper MCP and solve them."*

---

### C. Claude Desktop (Windows)
Edit `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "agentic-helper": {
      "command": "python",
      "args": ["-m", "quiz_pilot.mcp_server"],
      "cwd": "C:\\Users\\YOUR_USERNAME\\Agentic-Helper"
    }
  }
}
```

---

## 🛠️ 5. Windows Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **`Scripts\Activate.ps1 cannot be loaded`** | PowerShell script restriction | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| **`connect ECONNREFUSED 127.0.0.1:9222`** | Chrome is not listening on 9222 | Close all Chrome windows completely and restart with `--remote-debugging-port=9222` |
| **Chrome opens without debugging** | Background Chrome process already running | Run in PowerShell: `Get-Process chrome | Stop-Process -Force` then restart Chrome with the flag |
| **File paths with backslashes** | Python escape issue on Windows | Always use forward slashes `/` or double backslashes `\\` in paths |
