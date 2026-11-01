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


def test_entry_points_are_wired():
    from quiz_pilot import mcp_server, course_orchestrator, tab_scheduler

    mcp_src = inspect.getsource(mcp_server)
    assert "ensure_browser_visible_once" in mcp_src
    assert "is_browser_running(_port)" in mcp_src  # raise only when already running

    orch_src = inspect.getsource(course_orchestrator)
    assert orch_src.count("ensure_browser_visible_once()") >= 2  # course + specialization

    sched_src = inspect.getsource(tab_scheduler)
    assert sched_src.count("ensure_browser_visible_once()") >= 3  # batch + open + smart
