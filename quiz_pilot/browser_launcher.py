"""
Autonomous Browser Launcher for Agentic-Helper / Quiz-Pilot.
Cross-platform: Windows, Linux, and macOS.
Auto-detects Chrome, Edge, Chromium, or Brave, launches with remote debugging port 9222,
and ensures CDP endpoint is live.
"""

import os
import sys
import time
import shutil
import subprocess
import urllib.request
import urllib.error
from typing import Optional, List, Tuple


CDP_DEFAULT_PORT = 9222


def is_browser_running(port: int = CDP_DEFAULT_PORT) -> bool:
    """Checks if a browser is actively listening on the CDP debugging port."""
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "QuizPilot/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_browser_candidates() -> List[str]:
    """Finds available Chromium-based browser executables on the host OS."""
    candidates = []

    if sys.platform == "win32":
        # Windows standard Chrome & Edge paths
        local_app_data = os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

        paths = [
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
        for p in paths:
            if os.path.exists(p):
                candidates.append(p)

        # Fallback to PATH lookup
        for name in ["chrome.exe", "msedge.exe", "brave.exe"]:
            w = shutil.which(name)
            if w and w not in candidates:
                candidates.append(w)

    elif sys.platform == "darwin":
        # macOS paths
        mac_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium"
        ]
        for p in mac_paths:
            if os.path.exists(p):
                candidates.append(p)
        for name in ["google-chrome", "chromium", "brave"]:
            w = shutil.which(name)
            if w and w not in candidates:
                candidates.append(w)

    else:
        # Linux / POSIX
        for name in [
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
            "brave",
            "brave-browser",
            "/opt/google/chrome/chrome",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome"
        ]:
            if os.path.isabs(name):
                if os.path.exists(name):
                    candidates.append(name)
            else:
                w = shutil.which(name)
                if w and w not in candidates:
                    candidates.append(w)

    return candidates


def launch_browser(url: Optional[str] = None, port: int = CDP_DEFAULT_PORT) -> Tuple[bool, str]:
    """
    Launches a Chromium browser on the remote debugging port with an isolated profile.
    """
    if is_browser_running(port):
        return True, f"Browser is already running and listening on port {port}."

    candidates = get_browser_candidates()
    if not candidates:
        return False, "No Chromium-based browser (Chrome, Edge, Brave, Chromium) found installed on this machine."

    browser_bin = candidates[0]

    # Dedicated isolated profile directory
    if sys.platform == "win32":
        user_data = os.path.join(os.environ.get("TEMP", r"C:\tmp"), "agent_browser")
    else:
        user_data = os.path.expanduser("~/.assessment_browser")

    os.makedirs(user_data, exist_ok=True)

    target_url = url or "https://www.coursera.org"
    cmd = [
        browser_bin,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check",
        target_url
    ]

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        return False, f"Failed to launch browser '{browser_bin}': {e}"

    # Wait up to 6 seconds for CDP to come online
    for _ in range(12):
        time.sleep(0.5)
        if is_browser_running(port):
            return True, f"Successfully launched {os.path.basename(browser_bin)} on port {port}!"

    return False, f"Browser launched, but port {port} did not respond within 6 seconds."


def ensure_browser(url: Optional[str] = None, port: int = CDP_DEFAULT_PORT) -> bool:
    """Ensures browser is alive and listening, launching if needed."""
    if is_browser_running(port):
        return True
    ok, msg = launch_browser(url=url, port=port)
    print(msg)
    return ok


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.coursera.org"
    success, message = launch_browser(target)
    print(message)
    sys.exit(0 if success else 1)
