"""Token-efficiency + speed batch (2026-11-03).

Pins the behaviours that keep host-context cost and per-call latency down:
- MCP tool results are compact JSON (no pretty-printing);
- record_quiz_analysis returns a short receipt, not the full markdown;
- duplicate alias tools are out of the schema (handlers still route);
- the programming manager reuses ONE persistent CDP connection;
- load_quiz_analysis never imports another quiz's analysis file.
"""
import asyncio
import json
import os

import pytest

from quiz_pilot import mcp_server
from quiz_pilot.attempt_protector import FastAttemptManager


def test_compact_helper_has_no_whitespace_padding():
    out = mcp_server._compact({"a": [1, 2], "b": {"c": "x"}})
    assert out == json.dumps({"a": [1, 2], "b": {"c": "x"}}, separators=(",", ":"))
    assert "\n" not in out


@pytest.mark.anyio
async def test_tool_results_are_compact_json():
    res = await mcp_server.handle_call_tool(
        "solve_multicast",
        {"mode": "fifo", "num_processes": 2,
         "multicasts": [{"src": 0, "id": "m1"}],
         "arrivals": [{"dst": 1, "msg": "m1"}]},
    )
    text = res["content"][0]["text"]
    json.loads(text)  # still valid JSON
    assert "\n" not in text  # compact: no indent/newlines


@pytest.mark.anyio
async def test_record_quiz_analysis_returns_short_receipt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mgr = FastAttemptManager(base_cache_dir=str(tmp_path / "cache"))
    monkeypatch.setattr(mcp_server, "attempt_mgr", mgr)
    questions = [
        {"index": 0, "prompt": "What is Paxos?", "type": "radio",
         "options": ["Consensus", "Storage"]},
        {"index": 1, "prompt": "What is Raft?", "type": "radio",
         "options": ["Consensus", "Networking"]},
    ]
    res = await mcp_server.handle_call_tool("record_quiz_analysis", {
        "quiz_id": "receipt_quiz", "questions": questions,
        "answers": {"0": 0, "1": 1}, "feedback": {"0": True, "1": False},
        "score_pct": 50.0, "attempt_num": 1,
        "md_path": str(tmp_path / "quiz_analysis.md"),
    })
    text = res["content"][0]["text"]
    receipt = json.loads(text)
    assert receipt["recorded"] is True
    assert receipt["locked_correct"] == 1
    assert receipt["needs_retry"] == 1
    # The full markdown (with its strategy tables) must NOT be in the result.
    assert "Strategy Matrix" not in text
    assert len(text) < 400


def test_tool_schema_has_no_duplicate_aliases():
    names = [t["name"] for t in mcp_server.TOOLS]
    assert len(names) == len(set(names)) == 23
    # Aliases removed from the schema; their handlers still exist.
    assert "inspect_all_tabs" not in names
    assert "solve_parallel_quizzes" not in names
    assert "smart_multiworker" in names


@pytest.mark.anyio
async def test_programming_manager_reuses_one_connection(monkeypatch):
    from quiz_pilot import programming_solver as ps

    class FakeBrowser:
        def __init__(self):
            self.contexts = []

        def is_connected(self):
            return True

    class FakeChromium:
        def __init__(self):
            self.calls = 0
            self.browser = FakeBrowser()

        async def connect_over_cdp(self, url):
            self.calls += 1
            return self.browser

    class FakePW:
        def __init__(self):
            self.chromium = FakeChromium()

        async def stop(self):
            pass

    fake_pw = FakePW()

    async def fake_start():
        return fake_pw

    monkeypatch.setattr(ps, "async_playwright", lambda: _Starter(fake_pw))
    mgr = ps.ProgrammingAssignmentManager()
    b1 = await mgr._get_browser()
    b2 = await mgr._get_browser()
    assert b1 is b2
    assert fake_pw.chromium.calls == 1  # connected once, then reused


class _Starter:
    def __init__(self, pw):
        self._pw = pw

    async def start(self):
        return self._pw


def test_load_quiz_analysis_ignores_other_quizzes_file(tmp_path):
    cache = tmp_path / "cache"
    mgr_a = FastAttemptManager(base_cache_dir=str(cache))
    qs = [{"index": 0, "prompt": "Shared prompt?", "type": "radio",
           "options": ["Yes", "No"]}]
    mgr_a.record_attempt(quiz_id="Quiz A", attempt_num=1, questions=qs,
                         answers={"0": 0}, feedback={"0": True},
                         score_pct=100.0, md_path=str(tmp_path / "a.md"))

    # A different quiz asking to load must NOT inherit Quiz A's answers,
    # even though the shared cache copy of quiz_analysis.md is Quiz A's.
    mgr_b = FastAttemptManager(base_cache_dir=str(cache))
    mgr_b.load_quiz_analysis(md_path=str(cache / "quiz_analysis.md"),
                             quiz_id="Quiz B")
    assert "Quiz B" not in mgr_b.quiz_memory
    answers = mgr_b.get_retry_answers(qs, quiz_id="Quiz B",
                                      md_path=str(cache / "quiz_analysis.md"))
    assert answers == {}
