"""
Async Multi-Tab Concurrent Queue Scheduler for Agentic-Helper / Quiz-Pilot.

Enables true parallel multi-tab execution across browser contexts:
- Discovers all open assessment tabs simultaneously.
- Maintains isolated per-tab workers with independent state machines.
- Concurrency bounded by Semaphore to prevent resource exhaustion.
- Handles tab-isolated DOM interactions, submissions, and feedback without cross-tab modal collisions.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable
from playwright.async_api import async_playwright, Page, Browser

from quiz_pilot.lms_adapters import get_lms_adapter
from quiz_pilot.attempt_protector import FastAttemptManager

logger = logging.getLogger("quiz_pilot.tab_scheduler")

LMS_KEYWORDS = [
    "coursera.org", "instructure.com", "canvas", "moodle",
    "blackboard", "forms.gle", "docs.google.com/forms",
    "assignment-submission", "quiz", "exam", "assessment", "attempt"
]


class AsyncTabScheduler:
    """
    Asynchronous Concurrent Multi-Tab Scheduler for Autonomous Assessment Automation.
    """
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222", max_concurrency: int = 4):
        self.cdp_url = cdp_url
        self.max_concurrency = max_concurrency
        self.attempt_mgr = FastAttemptManager()

    @staticmethod
    def is_assessment_page(page: Page) -> bool:
        """Determines if a given page is an active LMS assessment or course page."""
        try:
            url_lower = page.url.lower()
            return any(k in url_lower for k in LMS_KEYWORDS)
        except Exception:
            return False

    def discover_assessment_tabs(self, browser: Browser) -> List[Page]:
        """Discovers all open assessment and quiz pages across all browser contexts."""
        assessment_pages = []
        for ctx in browser.contexts:
            for p in ctx.pages:
                if self.is_assessment_page(p):
                    assessment_pages.append(p)
        return assessment_pages

    async def inspect_all_tabs(self) -> List[Dict[str, Any]]:
        """Returns structured metadata of all open tabs across the browser."""
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
            except Exception as e:
                logger.error(f"CDP connection failed: {e}")
                return []

            tabs = []
            idx = 0
            for ctx in browser.contexts:
                for page in ctx.pages:
                    try:
                        title = await page.title()
                        url = page.url
                        is_lms = self.is_assessment_page(page)
                        tabs.append({
                            "tab_index": idx,
                            "title": title,
                            "url": url,
                            "is_assessment": is_lms
                        })
                        idx += 1
                    except Exception:
                        pass
            return tabs

    async def _process_single_tab(
        self,
        page: Page,
        tab_index: int,
        semaphore: asyncio.Semaphore,
        expected_url: str = None,
        answer_generator: Optional[Callable[[List[Dict[str, Any]]], Dict[int, Any]]] = None,
        auto_submit: bool = True
    ) -> Dict[str, Any]:
        """
        Isolated worker processing a single tab through the full assessment lifecycle:
        DETECTION -> EXTRACTION -> ANSWERING -> SUBMISSION -> FEEDBACK.
        """
        async with semaphore:
            title = ""
            url = ""
            try:
                title = await page.title()
                url = page.url
            except Exception:
                pass

            result: Dict[str, Any] = {
                "tab_index": tab_index,
                "title": title,
                "url": url,
                "questions_count": 0,
                "submitted": False,
                "score_pct": None,
                "passed": False,
                "error": None
            }

            # TAB OWNERSHIP: this worker acts ONLY on its assigned tab/URL.
            # If the tab no longer shows the assigned work (another worker
            # navigated it), try ONE re-navigation to our own URL; if that
            # fails, abort WITHOUT touching whatever foreign assessment is
            # now displayed - never adopt another worker's tab.
            assigned_url = (expected_url or url or "").split("?")[0].rstrip("/")
            current_base = ""
            try:
                current_base = (page.url or "").split("?")[0].rstrip("/")
            except Exception:
                pass
            if assigned_url and current_base and current_base != assigned_url:
                try:
                    await page.goto(expected_url, wait_until="commit")
                    current_base = (page.url or "").split("?")[0].rstrip("/")
                except Exception:
                    pass
                if current_base != assigned_url:
                    result["status"] = "TAB_OWNERSHIP_LOST"
                    result["error"] = (
                        f"Tab navigated away from its assigned URL ({assigned_url}); "
                        "aborted without touching another tab's work."
                    )
                    return result

            # Per-tab quiz identity: title ALONE collides across workers
            # (two courses can hold same-titled quizzes and would share
            # one memory file). Scope memory to this tab's course slug.
            _slug = assigned_url.rstrip("/").split("/")[-1] if assigned_url else ""
            quiz_key = f"{title} [{_slug}]" if title else (_slug or f"tab_{tab_index}")
            result["quiz_key"] = quiz_key

            try:
                adapter = get_lms_adapter(page)
                
                # 1. Extract Questions via LMS Adapter
                questions = await adapter.extract_questions_async()
                
                result["questions_count"] = len(questions)
                if not questions:
                    result["status"] = "NO_QUESTIONS_FOUND"
                    return result

                # 2. Determine Answers
                answers: Dict[int, Any] = {}
                if answer_generator:
                    answers = answer_generator(questions)
                else:
                    answers = self.attempt_mgr.get_retry_answers(questions, quiz_id=quiz_key)

                # Guarantee 100% of questions are answered (never leave any question unanswered)
                for q in questions:
                    q_idx = q.get("index", 0)
                    if q_idx not in answers and str(q_idx) not in answers:
                        answers[q_idx] = 0

                # 3. Fill Answers via LMS Adapter (fill only)
                if hasattr(adapter, "batch_fill_answers_async"):
                    await adapter.batch_fill_answers_async(answers, auto_submit=False)
                elif hasattr(adapter, "batch_fill_answers"):
                    adapter.batch_fill_answers(answers, auto_submit=False)
                else:
                    for q_idx, val in answers.items():
                        await adapter.fill_answer_async(int(q_idx), val)

                # 4. Handle Submission & Feedback
                if auto_submit:
                    await adapter.submit_assessment_async()
                    result["submitted"] = True
                    await asyncio.sleep(0.5)

                    try:
                        fb = await adapter.extract_feedback_async()
                    except Exception:
                        fb = {}

                    result["score_pct"] = fb.get("score_pct")
                    result["passed"] = fb.get("passed", False)
                    result["status"] = "PASSED" if result["passed"] else "COMPLETED"

                    # 5. Record feedback and update memory
                    try:
                        fb_map = fb.get("feedback")
                        if fb_map is None:
                            fb_map = {q["index"]: fb.get("passed", False) for q in questions} if fb.get("passed") else {}
                        self.attempt_mgr.record_attempt(
                            quiz_id=quiz_key,
                            attempt_num=1,
                            questions=questions,
                            answers=answers,
                            feedback=fb_map,
                            score_pct=fb.get("score_pct")
                        )
                    except Exception:
                        pass
                else:
                    result["status"] = "ANSWERS_FILLED"

            except Exception as e:
                logger.error(f"Error processing tab {tab_index} ({url}): {e}")
                result["error"] = str(e)
                result["status"] = "ERROR"

            return result

    async def run_parallel_batch(
        self,
        answer_generator: Optional[Callable[[List[Dict[str, Any]]], Dict[int, Any]]] = None,
        auto_submit: bool = True
    ) -> Dict[str, Any]:
        """
        Main entry point for concurrent multi-tab quiz execution.
        Discovers all open assessment tabs and processes them concurrently.
        """
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
            except Exception as e:
                return {"error": f"Failed to connect to browser on CDP {self.cdp_url}: {e}"}

            tabs = self.discover_assessment_tabs(browser)
            if not tabs:
                return {
                    "total_tabs": 0,
                    "results": [],
                    "message": "No open assessment or quiz tabs found."
                }

            semaphore = asyncio.Semaphore(self.max_concurrency)
            tasks = [
                self._process_single_tab(
                    page=tab,
                    tab_index=idx,
                    semaphore=semaphore,
                    answer_generator=answer_generator,
                    auto_submit=auto_submit,
                    expected_url=tab.url
                )
                for idx, tab in enumerate(tabs)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=False)
            
            passed_count = sum(1 for r in results if r.get("passed"))
            # Per-quiz cleanup ONLY: purge each passed quiz's own cache files.
            # (Previously purge_all() fired when ANY tab passed, wiping the
            # memory of tabs still working - a shared-state collision.)
            for r in results:
                if r.get("passed") and r.get("quiz_key"):
                    try:
                        self.attempt_mgr.purge_cache(r["quiz_key"])
                    except Exception:
                        pass
            return {
                "total_tabs": len(tabs),
                "passed_count": passed_count,
                "concurrency": self.max_concurrency,
                "results": results
            }

    async def open_and_solve_parallel(
        self,
        urls: List[str],
        auto_submit: bool = True
    ) -> Dict[str, Any]:
        """
        Opens a list of assessment/course URLs into separate background tabs,
        then processes and solves all of them concurrently.
        """
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
            except Exception as e:
                return {"error": f"Failed to connect to browser on CDP {self.cdp_url}: {e}"}

            context = browser.contexts[0] if browser.contexts else await browser.new_context()

            # Open all tabs
            created_pages = []
            for url in urls:
                page = await context.new_page()
                try:
                    await page.evaluate("(u) => window.location.href = u", url)
                except Exception:
                    await page.goto(url, wait_until="commit")
                created_pages.append(page)

            # Allow pages to mount reactively without blind sleeps
            async def fast_wait_tab(p_tab):
                try:
                    await p_tab.wait_for_selector('div[role="radiogroup"], div[role="group"], [data-testid*="question"], main', timeout=3000)
                except Exception:
                    pass

            await asyncio.gather(*[fast_wait_tab(tab) for tab in created_pages], return_exceptions=True)

            semaphore = asyncio.Semaphore(self.max_concurrency)
            tasks = [
                self._process_single_tab(
                    page=tab,
                    tab_index=idx,
                    semaphore=semaphore,
                    auto_submit=auto_submit,
                    expected_url=urls[idx]
                )
                for idx, tab in enumerate(created_pages)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=False)
            passed_count = sum(1 for r in results if r.get("passed"))
            return {
                "total_tabs": len(created_pages),
                "passed_count": passed_count,
                "concurrency": self.max_concurrency,
                "results": results
            }

    async def smart_multiworker(
        self,
        auto_submit: bool = True,
        prefer_direct_api: bool = True
    ) -> Dict[str, Any]:
        """
        Intelligent Multi-Worker:
        1. Connects to browser over CDP.
        2. Detects open assessment/quiz tabs:
           - If multiple assessment tabs (>= 2) are already open, solves them concurrently.
        3. If only 1 tab is open (or tabs are on course / specialization homepages):
           - If tab URL is a Specialization (/specializations/<slug>):
             Discovers child courses, opens them in separate tabs, and completes them concurrently.
           - If tab URL is a Single Course (/learn/<slug>):
             Crawls the syllabus to extract all incomplete module assignments,
             opens them across multiple browser tabs (up to max_concurrency),
             and solves them concurrently in parallel!
           - If tab is an active quiz:
             Solves the assessment directly.
        """
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
            except Exception as e:
                return {"error": f"Failed to connect to browser on CDP {self.cdp_url}: {e}"}

            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            assessment_tabs = [page for page in context.pages if self.is_assessment_page(page)]

            # Check if multiple actual quiz/submission tabs are already open
            quiz_tabs = [
                page for page in assessment_tabs
                if any(k in page.url.lower() for k in ["/quiz/", "/exam/", "/assignment-submission/", "/attempt", "form"])
            ]

            if len(quiz_tabs) >= 2:
                # Solve existing multi-tabs
                return await self.run_parallel_batch(auto_submit=auto_submit)

            # Determine the target course/specialization page WITHOUT grabbing
            # pages[0]: in multi-tab runs the first page may belong to another
            # worker. Only an unambiguous single course/spec page may route.
            course_pages = [
                pg for pg in context.pages
                if "/specializations/" in pg.url or "/learn/" in pg.url
            ]
            distinct_courses = {pg.url.split("?")[0] for pg in course_pages}
            if len(distinct_courses) > 1:
                return {"error": "Multiple different course/specialization tabs are open; "
                                 "cannot tell which one to run. Keep exactly one course tab open."}
            target_page = course_pages[0] if course_pages else None
            if not target_page:
                if assessment_tabs:
                    return await self.run_parallel_batch(auto_submit=auto_submit)
                return {"error": "No open browser pages found."}

            current_url = target_page.url

            from quiz_pilot.course_orchestrator import CourseOrchestrator
            orch = CourseOrchestrator(cdp_url=self.cdp_url, max_concurrency=self.max_concurrency)

            # Case A: Specialization page
            if "/specializations/" in current_url:
                return await orch.auto_complete_specialization(
                    spec_url=current_url,
                    prefer_direct_api=prefer_direct_api
                )

            # Case B: Single Course page
            if "/learn/" in current_url:
                import re
                m = re.search(r'(https://www\.coursera\.org/learn/[^/?#]+)', current_url)
                course_base_url = m.group(1) if m else current_url
                course_result = await orch.auto_complete_course(
                    course_url=course_base_url,
                    prefer_direct_api=prefer_direct_api
                )
                # A single course inside a Specialization is NOT the whole job:
                # the certificate needs EVERY course in the specialization.
                # If this course page links to a specialization, continue with
                # the remaining courses instead of stopping after one course
                # (previously: completed one course, then wrongly reported
                # "no other courses").
                spec_url = None
                try:
                    spec_url = await target_page.evaluate(
                        "() => { const a = document.querySelector('a[href*=\"/specializations/\"]'); "
                        "return a ? a.href.split('?')[0] : null; }"
                    )
                except Exception:
                    spec_url = None
                if spec_url:
                    spec_result = await orch.auto_complete_specialization(
                        spec_url=spec_url,
                        prefer_direct_api=prefer_direct_api
                    )
                    return {
                        "course_result": course_result,
                        "specialization_result": spec_result,
                        "note": "Course belongs to a specialization; continued "
                                "with its remaining courses.",
                    }
                return course_result

            # Fallback: run on whatever assessment tabs are open
            return await self.run_parallel_batch(auto_submit=auto_submit)


def solve_all_open_quizzes_sync(
    cdp_url: str = "http://127.0.0.1:9222",
    max_concurrency: int = 4,
    answer_generator: Optional[Callable] = None,
    auto_submit: bool = True
) -> Dict[str, Any]:
    """Synchronous wrapper for running the AsyncTabScheduler on already open tabs."""
    scheduler = AsyncTabScheduler(cdp_url=cdp_url, max_concurrency=max_concurrency)
    return asyncio.run(scheduler.run_parallel_batch(
        answer_generator=answer_generator,
        auto_submit=auto_submit
    ))


def open_and_solve_parallel_sync(
    urls: List[str],
    cdp_url: str = "http://127.0.0.1:9222",
    max_concurrency: int = 4,
    auto_submit: bool = True
) -> Dict[str, Any]:
    """Synchronous wrapper to open multiple URLs in tabs and solve them concurrently."""
    scheduler = AsyncTabScheduler(cdp_url=cdp_url, max_concurrency=max_concurrency)
    return asyncio.run(scheduler.open_and_solve_parallel(
        urls=urls,
        auto_submit=auto_submit
    ))


def smart_multiworker_sync(
    cdp_url: str = "http://127.0.0.1:9222",
    max_concurrency: int = 4,
    auto_submit: bool = True
) -> Dict[str, Any]:
    """Synchronous wrapper for smart_multiworker."""
    scheduler = AsyncTabScheduler(cdp_url=cdp_url, max_concurrency=max_concurrency)
    return asyncio.run(scheduler.smart_multiworker(auto_submit=auto_submit))
