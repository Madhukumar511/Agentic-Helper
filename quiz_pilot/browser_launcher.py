"""
Autonomous Browser Launcher for Agentic-Helper / Quiz-Pilot.
Cross-platform: Windows, Linux, and macOS.
Launches Google Chrome (Windows: Chrome first, other Chromium browsers only as
fallback) with remote debugging port 9222, verifies the CDP endpoint is live,
and BRINGS THE BROWSER WINDOW TO THE FRONT on Windows.

Why the bring-to-front step exists (bug fixed 2026-11-01):
When an IDE agent / background shell launches a browser, Windows' foreground
lock forbids the new window from taking focus, so the browser used to start
invisibly in the background even though the process and the CDP port were
fine. Users then reported "the browser did not open". After a successful
launch this module now (1) activates the course tab over CDP and (2) raises
the actual OS window with the Win32 foreground APIs, so the window is
genuinely visible on the desktop.
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


def _cdp_get(port: int, path: str, timeout: float = 2.0):
    """GET a CDP HTTP endpoint and return parsed JSON (or raw text)."""
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "QuizPilot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except Exception:
        return body


def is_browser_running(port: int = CDP_DEFAULT_PORT) -> bool:
    """Checks if a browser is actively listening on the CDP debugging port."""
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "QuizPilot/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def activate_first_page_tab(port: int = CDP_DEFAULT_PORT) -> str:
    """Activates the first real page tab over CDP and returns its title ('' if none)."""
    try:
        tabs = _cdp_get(port, "/json/list")
        if not isinstance(tabs, list):
            return ""
        page = next((t for t in tabs if t.get("type") == "page"), None)
        if not page:
            return ""
        tab_id = page.get("id")
        if tab_id:
            try:
                _cdp_get(port, f"/json/activate/{tab_id}")
            except Exception:
                pass
        return page.get("title", "") or ""
    except Exception:
        return ""


def _raise_browser_window_windows(tab_title: str = "") -> bool:
    """
    Raises the browser's OS window to the foreground on Windows.

    A plain SetForegroundWindow call from a background process is blocked by
    the Windows foreground lock, so this uses the standard workarounds:
    a simulated Alt keypress (grants foreground rights), AttachThreadInput
    with the foreground and target threads, ShowWindow restore/maximise,
    then SetForegroundWindow. Returns True if a browser window was found.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        windows = []
        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    windows.append((hwnd, pid.value, buf.value))
            return True

        user32.EnumWindows(enum_proc_type(_cb), 0)

        def _image_name(pid: int) -> str:
            handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not handle:
                return ""
            try:
                buf = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(32768)
                if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                    return os.path.basename(buf.value).lower()
                return ""
            finally:
                kernel32.CloseHandle(handle)

        browser_images = {"chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "chromium.exe"}
        target_hwnd = None
        if tab_title:
            frag = tab_title.strip()[:25].lower()
            for hwnd, pid, title in windows:
                if frag and frag in title.lower() and _image_name(pid) in browser_images:
                    target_hwnd = hwnd
                    break
        if target_hwnd is None:
            for hwnd, pid, title in windows:
                if _image_name(pid) in browser_images:
                    target_hwnd = hwnd
                    break
        if target_hwnd is None:
            return False

        SW_RESTORE, SW_MAXIMIZE = 9, 3
        VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002
        # Simulated Alt press releases the foreground lock for this process.
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

        if user32.IsIconic(target_hwnd):
            user32.ShowWindow(target_hwnd, SW_RESTORE)

        cur_thread = kernel32.GetCurrentThreadId()
        win_thread = user32.GetWindowThreadProcessId(target_hwnd, None)
        fg_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        user32.AttachThreadInput(cur_thread, win_thread, True)
        if fg_thread and fg_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, True)
        try:
            user32.BringWindowToTop(target_hwnd)
            user32.ShowWindow(target_hwnd, SW_MAXIMIZE)
            user32.SetForegroundWindow(target_hwnd)
        finally:
            user32.AttachThreadInput(cur_thread, win_thread, False)
            if fg_thread and fg_thread != cur_thread:
                user32.AttachThreadInput(cur_thread, fg_thread, False)
        return True
    except Exception:
        return False


def bring_browser_to_front(port: int = CDP_DEFAULT_PORT) -> bool:
    """
    Makes the running browser genuinely visible: activates its page tab over
    CDP, then raises the OS window (Windows). Safe to call repeatedly.
    """
    title = activate_first_page_tab(port)
    if sys.platform == "win32":
        for _ in range(3):
            if _raise_browser_window_windows(title):
                return True
            time.sleep(0.4)
        return False
    return True


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
    """Finds available browsers on the host OS.

    Windows priority is deliberately GOOGLE CHROME FIRST (product decision).
    The system default browser is NOT prioritised: on many machines the
    default is Edge, whose "Startup Boost" background process can swallow a
    launch so that no visible window ever appears. Edge/Brave/Vivaldi are
    only fallbacks for machines with no Chrome installed.
    """
    candidates = []

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        program_w64 = os.environ.get("ProgramW6432", r"C:\Program Files")

        paths = [
            # 1. Google Chrome — the supported browser
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_w64, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
            # 2. Fallbacks, only used when Chrome is absent
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

        # 3. Fallback to PATH lookup (Chrome first)
        for name in ["chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "chromium.exe"]:
            w = shutil.which(name)
            if w and w not in candidates:
                candidates.append(w)

        # 4. System default browser as a last resort (if Chromium-based)
        default_browser = get_windows_default_browser()
        if default_browser and os.path.exists(default_browser) and default_browser not in candidates:
            name_lower = os.path.basename(default_browser).lower()
            if any(k in name_lower for k in ["chrome", "msedge", "edge", "brave", "vivaldi", "chromium"]):
                candidates.append(default_browser)

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


def get_profile_dir() -> str:
    """
    Persistent, dedicated browser profile.

    Windows: %LOCALAPPDATA%\\AgenticHelper\\browser-profile — deliberately NOT
    %TEMP%: Windows Storage Sense / Disk Cleanup periodically wipe TEMP, which
    used to delete the profile and the saved Coursera login with it.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "AgenticHelper", "browser-profile")
    return os.path.expanduser("~/.assessment_browser")


def launch_browser(url: Optional[str] = None, port: int = CDP_DEFAULT_PORT) -> Tuple[bool, str]:
    """
    Launches Chrome on the remote debugging port with the dedicated profile,
    verifies the CDP endpoint actually responds (up to ~20 s), and brings the
    browser window to the front so the user can see it and log in.
    """
    if is_browser_running(port):
        if url:
            open_url_in_running_browser(url, port)
        bring_browser_to_front(port)
        return True, f"Browser is already running and listening on port {port} (window brought to front)."

    candidates = get_browser_candidates()
    if not candidates:
        return False, "No Chromium-based browser (Chrome, Edge, Brave, Chromium) found installed on this machine."

    browser_bin = candidates[0]
    user_data = get_profile_dir()
    os.makedirs(user_data, exist_ok=True)

    target_url = url or "https://www.coursera.org"
    cmd = [
        browser_bin,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "--start-maximized",
        target_url
    ]

    try:
        if sys.platform == "win32":
            # Launch the browser exe DIRECTLY (no powershell / cmd /c chain):
            # nested shell launches are a classic malware pattern and get
            # blocked by antivirus "malicious command line" heuristics.
            flags = 0
            if hasattr(subprocess, "DETACHED_PROCESS"):
                flags |= subprocess.DETACHED_PROCESS
            if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                flags |= subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(
                cmd,
                creationflags=flags,
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
    except Exception as e:
        return False, f"Failed to launch browser '{browser_bin}': {e}"

    # Wait up to ~20 seconds for CDP to come online (slow first launches and
    # antivirus scanning can delay the port well past the old 6 s limit)
    for _ in range(40):
        time.sleep(0.5)
        if is_browser_running(port):
            if target_url:
                open_url_in_running_browser(target_url, port)
            raised = bring_browser_to_front(port)
            front_note = "window brought to front" if raised else "window may be behind other windows"
            return True, f"Successfully launched {os.path.basename(browser_bin)} on port {port} and opened {target_url} ({front_note})!"

    return False, f"Browser launched, but port {port} did not respond within 20 seconds."


_visibility_ensured = False


def ensure_browser_visible_once(port: int = CDP_DEFAULT_PORT) -> bool:
    """Make sure the browser is running AND its window is raised - once
    per process.

    The tool's Chrome survives between runs, often minimized or behind
    the IDE. Every connect site used to attach silently, so the agent
    worked in a browser the user could not see (reported 2026-11-01:
    a full run executed with no visible window). Callers invoke this
    before their first CDP connection; the once-guard keeps later calls
    free and never steals focus mid-run.
    """
    global _visibility_ensured
    if _visibility_ensured:
        return True
    _visibility_ensured = True
    try:
        return ensure_browser(port=port)
    except Exception:
        return False


def ensure_browser(url: Optional[str] = None, port: int = CDP_DEFAULT_PORT) -> bool:
    """Ensures browser is alive and listening, launching if needed, navigating
    to the target URL, and bringing the window to the front."""
    if is_browser_running(port):
        if url:
            open_url_in_running_browser(url, port)
        bring_browser_to_front(port)
        return True
    ok, msg = launch_browser(url=url, port=port)
    print(msg)
    return ok


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.coursera.org"
    success, message = launch_browser(target)
    print(message)
    sys.exit(0 if success else 1)
