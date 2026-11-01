"""
Specialization-completion regression tests (2026-11-01).

Bug: the tool completed ONE course of a 7-course specialization and then
reported there were no more courses. Two causes: (1) the single-course
entry point never continued into the parent specialization, and (2)
auto_complete_specialization counted ATTEMPTED courses as completed and
never verified or re-checked for remaining courses.

These tests pin the loop contract of _loop_until_complete: keep going
until every item VERIFIES complete; stop honestly (with the remaining
items reported) when a full pass makes no progress; never spin forever.
"""
import asyncio

from quiz_pilot.course_orchestrator import _loop_until_complete


def test_loop_continues_until_all_verified():
    state = {"A": 0, "B": 0}

    async def run_one(item):
        state[item] += 1
        return {"item": item, "run": state[item]}

    async def verify_one(item):
        # A completes after 1 run, B only after 2 runs
        return state[item] >= (1 if item == "A" else 2)

    out = asyncio.run(_loop_until_complete(["A", "B"], run_one, verify_one, max_passes=3))
    assert out["remaining_items"] == []
    assert sorted(i for i in out["completed_items"]) == ["A", "B"]
    assert out["passes"] == 2  # B needed a second pass - a single pass would have lied


def test_loop_stops_on_no_progress_and_reports_remaining():
    async def run_one(item):
        return {"item": item}

    async def verify_one(item):
        return item == "A"  # B can never complete

    out = asyncio.run(_loop_until_complete(["A", "B"], run_one, verify_one, max_passes=3))
    assert out["completed_items"] == ["A"]
    assert out["remaining_items"] == ["B"]  # reported, not silently dropped
    assert out["passes"] <= 3  # bounded - no infinite retry


def test_loop_single_pass_when_all_complete():
    async def run_one(item):
        return {"item": item}

    async def verify_one(item):
        return True

    out = asyncio.run(_loop_until_complete(["A", "B", "C"], run_one, verify_one))
    assert out["passes"] == 1
    assert out["remaining_items"] == []
    assert len(out["completed_items"]) == 3


def test_loop_verify_errors_count_as_incomplete():
    calls = {"n": 0}

    async def run_one(item):
        return {"item": item}

    async def verify_one(item):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("page not ready")
        return True

    out = asyncio.run(_loop_until_complete(["A"], run_one, verify_one, max_passes=3))
    assert out["remaining_items"] == []  # recovered on the next pass instead of crashing
