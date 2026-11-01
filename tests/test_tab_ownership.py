"""
Tab-ownership regression tests (2026-11-01).

Parallel multi-tab / multi-course runs collided because page lookup fell
back to pages[0]: every worker acted on the FIRST tab, so Tab A navigated
away while Tab B was clicking an answer. These tests pin the rules:

1. Page finders never return the first tab when several tabs are open and
   none matches - they return None (single open page may be used implicitly).
2. A tab worker whose tab was navigated away from its assigned URL aborts
   with TAB_OWNERSHIP_LOST instead of solving a foreign assessment.
3. The shared-cache lock is re-entrant (record_attempt nests save/export).
"""
import asyncio
import time

from quiz_pilot.mcp_server import find_assessment_page
from quiz_pilot.programming_solver import ProgrammingAssignmentManager
from quiz_pilot.tab_scheduler import AsyncTabScheduler
from quiz_pilot.attempt_protector import _CacheFileLock


class FakePage:
    def __init__(self, url, title=""):
        self.url = url
        self._title = title

    def title(self):
        return self._title


class FakeCtx:
    def __init__(self, pages):
        self.pages = pages


class FakeBrowser:
    def __init__(self, pages):
        self.contexts = [FakeCtx(pages)]


def test_mcp_finder_no_first_tab_hijack():
    pages = [FakePage("https://site-a.test/a", "Alpha"), FakePage("https://site-b.test/b", "Beta")]
    found = asyncio.run(find_assessment_page(FakeBrowser(pages), None))
    assert found is None  # two unrelated tabs, no keyword -> refuse, don't hijack tab 0


def test_mcp_finder_single_page_implicit_ok():
    only = FakePage("https://site-a.test/only", "Only")
    found = asyncio.run(find_assessment_page(FakeBrowser([only]), None))
    assert found is only


def test_mcp_finder_keyword_picks_matching_tab():
    p1 = FakePage("https://site-a.test/a", "Alpha")
    p2 = FakePage("https://site-b.test/beta-course", "Beta")
    found = asyncio.run(find_assessment_page(FakeBrowser([p1, p2]), "beta"))
    assert found is p2


def test_programming_finder_no_first_tab_hijack():
    pages = [FakePage("https://site-a.test/a", "Alpha"), FakePage("https://site-b.test/b", "Beta")]
    found = asyncio.run(ProgrammingAssignmentManager.find_target_page(FakeBrowser(pages), None))
    assert found is None


class HijackedPage:
    """A page that was navigated to a DIFFERENT course by someone else."""

    def __init__(self):
        self.url = "https://www.coursera.org/learn/other-course/quiz/9"

    async def title(self):
        return "Other Course Quiz"

    async def goto(self, *a, **kw):
        raise RuntimeError("navigation blocked")


def test_scheduler_worker_aborts_on_hijacked_tab(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scheduler = AsyncTabScheduler(max_concurrency=2)
    page = HijackedPage()

    async def run():
        return await scheduler._process_single_tab(
            page=page,
            tab_index=0,
            semaphore=asyncio.Semaphore(1),
            auto_submit=False,
            expected_url="https://www.coursera.org/learn/my-course/quiz/1",
        )

    result = asyncio.run(run())
    assert result["status"] == "TAB_OWNERSHIP_LOST"
    assert result["questions_count"] == 0
    assert result["submitted"] is False


def test_cache_lock_reentrant_and_fast():
    start = time.time()
    with _CacheFileLock():
        with _CacheFileLock():
            pass
    assert time.time() - start < 2.0  # nested use must not spin on the 5 s timeout
