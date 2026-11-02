"""
Browser-visibility wiring tests (2026-11-01).

Bug: a full agent run executed with NO visible browser window. The tool's
Chrome (separate persistent profile) survives between runs - often
minimized or behind the IDE - and every CDP entry point connected to it
silently. ensure_browser() already knew how to raise the window, but
nothing called it outside the explicit launch_browser tool.

Fix: browser_launcher.ensure_browser_visible_once() raises the window
exactly once per process, wired into the MCP tool handler (when a
browser is already running - it never launches from there), the
orchestrator's course/specialization runs, and the scheduler's three
entry points.
"""
import inspect

import quiz_pilot.browser_launcher as bl


def test_visible_once_raises_only_once(monkeypatch):
    calls = {"n": 0}

    def fake_ensure(url=None, port=9222):
        calls["n"] += 1
        return True

    monkeypatch.setattr(bl, "ensure_browser", fake_ensure)
    bl._visibility_ensured = False
    try:
        assert bl.ensure_browser_visible_once() is True
        assert bl.ensure_browser_visible_once() is True
        assert bl.ensure_browser_visible_once() is True
        assert calls["n"] == 1  # raised once - later calls are free, no focus stealing
    finally:
        bl._visibility_ensured = False


def test_ensure_browser_relaunches_when_window_cannot_surface(monkeypatch):
    """The reported failure: browser alive on CDP, raise 'succeeds', yet no
    window anywhere (cloaked on another virtual desktop). ensure_browser
    must now detect the failed raise, close that instance over CDP, and
    relaunch fresh - a new window always lands on the current desktop."""
    calls = {"close": 0, "launch": 0}
    monkeypatch.setattr(bl, "is_browser_running", lambda port=9222: True)
    monkeypatch.setattr(bl, "open_url_in_running_browser", lambda url, port=9222: True)
    monkeypatch.setattr(bl, "bring_browser_to_front", lambda port=9222: False)

    def fake_close(port=9222, timeout=6.0):
        calls["close"] += 1
        return True

    def fake_launch(url=None, port=9222):
        calls["launch"] += 1
        return True, "launched"

    monkeypatch.setattr(bl, "_close_browser_via_cdp", fake_close)
    monkeypatch.setattr(bl, "launch_browser", fake_launch)
    assert bl.ensure_browser(url="https://www.coursera.org") is True
    assert calls == {"close": 1, "launch": 1}


def test_ensure_browser_keeps_browser_when_raise_works(monkeypatch):
    calls = {"close": 0, "launch": 0}
    monkeypatch.setattr(bl, "is_browser_running", lambda port=9222: True)
    monkeypatch.setattr(bl, "open_url_in_running_browser", lambda url, port=9222: True)
    monkeypatch.setattr(bl, "bring_browser_to_front", lambda port=9222: True)
    monkeypatch.setattr(bl, "_close_browser_via_cdp",
                        lambda port=9222, timeout=6.0: calls.__setitem__("close", calls["close"] + 1) or True)
    monkeypatch.setattr(bl, "launch_browser",
                        lambda url=None, port=9222: calls.__setitem__("launch", calls["launch"] + 1) or (True, "x"))
    assert bl.ensure_browser(url="https://www.coursera.org") is True
    assert calls == {"close": 0, "launch": 0}  # healthy path: no disruption


def test_ensure_browser_leaves_unclosable_browser_alone(monkeypatch):
    monkeypatch.setattr(bl, "is_browser_running", lambda port=9222: True)
    monkeypatch.setattr(bl, "open_url_in_running_browser", lambda url, port=9222: True)
    monkeypatch.setattr(bl, "bring_browser_to_front", lambda port=9222: False)
    monkeypatch.setattr(bl, "_close_browser_via_cdp", lambda port=9222, timeout=6.0: False)
    monkeypatch.setattr(bl, "launch_browser",
                        lambda url=None, port=9222: (_ for _ in ()).throw(AssertionError("must not launch")))
    # Could not close it: keep the (invisible but working) browser rather
    # than failing the run.
    assert bl.ensure_browser(url="https://www.coursera.org") is True


def test_close_browser_via_cdp_closes_all_pages(monkeypatch):
    closed = []
    tabs = [
        {"type": "page", "id": "A"},
        {"type": "page", "id": "B"},
        {"type": "background_page", "id": "C"},
    ]

    def fake_get(port, path, timeout=2.0):
        if path == "/json/list":
            return tabs
        if path.startswith("/json/close/"):
            closed.append(path.rsplit("/", 1)[-1])
            return {}
        return {}

    monkeypatch.setattr(bl, "_cdp_get", fake_get)
    monkeypatch.setattr(bl, "is_browser_running", lambda port=9222: False)
    assert bl._close_browser_via_cdp() is True
    assert closed == ["A", "B"]  # pages only


def test_launch_browser_already_running_returns_tuple(monkeypatch):
    """Regression guard: launch_browser's contract is (bool, str). An edit
    once truncated its already-running return to a bare bool (the tuple
    tail was swallowed into a comment), which would crash every caller's
    unpacking. It must also keep its original semantics - the
    close-and-relaunch fallback lives in ensure_browser, not here."""
    monkeypatch.setattr(bl, "is_browser_running", lambda port=9222: True)
    monkeypatch.setattr(bl, "open_url_in_running_browser", lambda url, port=9222: True)
    monkeypatch.setattr(bl, "bring_browser_to_front", lambda port=9222: False)
    monkeypatch.setattr(bl, "_close_browser_via_cdp",
                        lambda port=9222, timeout=6.0: (_ for _ in ()).throw(
                            AssertionError("launch_browser must not close the browser")))
    result = bl.launch_browser(url="https://www.coursera.org")
    assert isinstance(result, tuple) and len(result) == 2
    ok, msg = result
    assert ok is True and "already running" in msg


def test_entry_points_are_wired():
    from quiz_pilot import mcp_server, course_orchestrator, tab_scheduler

    mcp_src = inspect.getsource(mcp_server)
    assert "ensure_browser_visible_once" in mcp_src
    assert "is_browser_running(_port)" in mcp_src  # raise only when already running

    orch_src = inspect.getsource(course_orchestrator)
    assert orch_src.count("ensure_browser_visible_once()") >= 2  # course + specialization

    sched_src = inspect.getsource(tab_scheduler)
    assert sched_src.count("ensure_browser_visible_once()") >= 3  # batch + open + smart
