"""
Autonomous Browser Launcher for Agentic-Helper / Quiz-Pilot.
Cross-platform: Windows, Linux, and macOS.
Auto-detects Chrome, Edge, Chromium, or Brave, launches with remote debugging port 9222,
and ensures CDP endpoint is live.
"""

import os
import sys
import time
import json
import shutil
import subprocess
import urllib.request
import urllib.error
import urllib.parse
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


def open_url_in_running_browser(url: str, port: int = CDP_DEFAULT_PORT) -> bool:
    """
    Opens or navigates to the given URL in the currently running browser over CDP.
    1. If a tab already matches the URL, activates that tab.
    2. Opens a new tab via CDP HTTP endpoint '/json/new?{url}'.
    3. Seamless Playwright fallback if HTTP endpoint is restricted.
    """
    if not url:
        return True

    # Normalize url for comparison
    clean_url = url.split("?")[0].rstrip("/").lower()

    # 1. Inspect existing tabs via CDP HTTP endpoint
    try:
        list_url = f"http://127.0.0.1:{port}/json/list"
        req = urllib.request.Request(list_url, headers={"User-Agent": "QuizPilot/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            tabs = json.loads(resp.read().decode("utf-8"))

        target_tab_id = None
        for tab in tabs:
            if tab.get("type") != "page":
                continue
            tab_url = tab.get("url", "").split("?")[0].rstrip("/").lower()
            if clean_url in tab_url or tab_url in clean_url:
                target_tab_id = tab.get("id")
                break

        if target_tab_id:
            # Activate tab
            act_url = f"http://127.0.0.1:{port}/json/activate/{target_tab_id}"
            try:
                urllib.request.urlopen(urllib.request.Request(act_url, method="POST"), timeout=2.0)
                return True
            except Exception:
                pass

        # 2. Open new tab via CDP HTTP PUT /json/new?{url}
        encoded_url = urllib.parse.quote(url, safe=":/%?&=#+@$,;~-._")
        new_url = f"http://127.0.0.1:{port}/json/new?{encoded_url}"
        new_req = urllib.request.Request(new_url, method="PUT", headers={"User-Agent": "QuizPilot/1.0"})
        with urllib.request.urlopen(new_req, timeout=3.0) as resp:
            if resp.status == 200:
                return True
    except Exception:
        pass

    # 3. Playwright fallback if direct HTTP CDP call fails
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            for p_tab in ctx.pages:
                if clean_url in p_tab.url.lower():
                    p_tab.bring_to_front()
                    return True
            new_p = ctx.new_page()
            new_p.goto(url)
            return True
    except Exception:
        return False


def get_windows_default_browser() -> Optional[str]:
    """Retrieves the system default browser executable from the Windows Registry."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        import re
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
        )
        prog_id, _ = winreg.QueryValueEx(key, "ProgId")
        winreg.CloseKey(key)

        cmd_key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command")
        cmd_str, _ = winreg.QueryValueEx(cmd_key, "")
        winreg.CloseKey(cmd_key)

        m = re.search(r'"([^"]+)"', cmd_str)
        if m and os.path.exists(m.group(1)):
            return m.group(1)
        parts = cmd_str.split()
        if parts and os.path.exists(parts[0]):
            return parts[0]
    except Exception:
        pass
    return None


def get_browser_candidates() -> List[str]:
    """Finds available browsers on the host OS, prioritizing user's system default."""
    candidates = []

    if sys.platform == "win32":
        # 1. System Default Browser via Registry (if Chromium-based)
        default_browser = get_windows_default_browser()
        if default_browser and os.path.exists(default_browser):
            name_lower = os.path.basename(default_browser).lower()
            if any(k in name_lower for k in ["chrome", "msedge", "edge", "brave", "vivaldi", "chromium"]):
                candidates.append(default_browser)

        # 2. Windows standard Chrome, Edge, Brave, Vivaldi paths
        local_app_data = os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        program_w64 = os.environ.get("ProgramW6432", r"C:\Program Files")

        paths = [
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_w64, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_w64, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(local_app_data, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_app_data, "Vivaldi", "Application", "vivaldi.exe"),
        ]
        for p in paths:
            if os.path.exists(p) and p not in candidates:
                candidates.append(p)

        # 3. Fallback to PATH lookup
        for name in ["chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "chromium.exe"]:
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
        if url:
            open_url_in_running_browser(url, port)
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
        "--new-window",
        "--start-maximized",
        target_url
    ]

    try:
        if sys.platform == "win32":
            # On Windows, launch detached GUI process directly without cmd.exe shell mangling
            flags = 0
            if hasattr(subprocess, "DETACHED_PROCESS"):
                flags |= subprocess.DETACHED_PROCESS
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                flags |= subprocess.CREATE_NEW_PROCESS_GROUP
            try:
                subprocess.Popen(
                    cmd,
                    creationflags=flags,
                    close_fds=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                # Safe fallback if direct spawn restricted
                quoted_cmd = [f'"{c}"' if (' ' in c or '&' in c or '^' in c) else c for c in cmd]
                subprocess.Popen(f'start "" {" ".join(quoted_cmd)}', shell=True)
        else:
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
            if target_url:
                open_url_in_running_browser(target_url, port)
            return True, f"Successfully launched {os.path.basename(browser_bin)} on port {port} and opened {target_url}!"

    return False, f"Browser launched, but port {port} did not respond within 6 seconds."


def ensure_browser(url: Optional[str] = None, port: int = CDP_DEFAULT_PORT) -> bool:
    """Ensures browser is alive and listening, launching if needed, and navigates to target URL."""
    if is_browser_running(port):
        if url:
            open_url_in_running_browser(url, port)
        return True
    ok, msg = launch_browser(url=url, port=port)
    print(msg)
    return ok


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.coursera.org"
    success, message = launch_browser(target)
    print(message)
    sys.exit(0 if success else 1)
