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

ASSESSMENT_PATH_KEYWORDS = [
    "/quiz/", "/exam/", "/assignment-submission/", "/programming/",
    "/peer/", "/supplement/", "/attempt", "/ungradedwidget/",
    "forms.gle", "docs.google.com/forms", "quizzes/"
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
    def is_assessment_tab(page: Page) -> bool:
        """Determines if a page is an active assessment/quiz/programming/peer submission tab."""
        try:
            url_lower = page.url.lower()
            return any(k in url_lower for k in ASSESSMENT_PATH_KEYWORDS)
        except Exception:
            return False

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
                if self.is_assessment_tab(p) or self.is_assessment_page(p):
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
                    answers = self.attempt_mgr.get_retry_answers(questions, quiz_id=title)

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
                            quiz_id=title,
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
                    auto_submit=auto_submit
                )
                for idx, tab in enumerate(tabs)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=False)
            
            passed_count = sum(1 for r in results if r.get("passed"))
            if passed_count > 0:
                self.attempt_mgr.purge_all()
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
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    try:
                        await page.goto(url, wait_until="commit", timeout=10000)
                    except Exception:
                        pass
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
                    auto_submit=auto_submit
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
        target_url: Optional[str] = None,
        auto_submit: bool = True,
        prefer_direct_api: bool = True
    ) -> Dict[str, Any]:
        """
        Intelligent Multi-Worker:
        1. Connects to browser over CDP.
        2. Detects open assessment/quiz/submission tabs:
           - If multiple assessment tabs (>= 2) are already open, solves them concurrently in parallel!
        3. If tabs are on course / specialization / my-learning homepages, or target_url is specified:
           - Specialization (/specializations/<slug>): Discovers child courses, opens them in separate isolated tabs, and completes them concurrently in parallel!
           - Single Course (/learn/<slug>): Crawls syllabus, opens incomplete module assignments across multiple tabs (up to max_concurrency), and solves concurrently!
           - My-Learning (/my-learning): Extracts current active course and auto-completes.
        """
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
            except Exception as e:
                return {"error": f"Failed to connect to browser on CDP {self.cdp_url}: {e}"}

            context = browser.contexts[0] if browser.contexts else await browser.new_context()

            # 1. Check if multiple actual quiz/submission tabs are already open
            quiz_tabs = [
                page for page in context.pages
                if self.is_assessment_tab(page)
            ]

            if len(quiz_tabs) >= 2 and not target_url:
                # Solve existing multi-tabs concurrently
                return await self.run_parallel_batch(auto_submit=auto_submit)

            # 2. Determine target URL
            current_url = target_url or ""
            if not current_url:
                # Search all open tabs for a specialization or course URL
                for pg in context.pages:
                    u = pg.url.lower()
                    if "/specializations/" in u:
                        current_url = pg.url
                        break
                    elif "/learn/" in u and not any(k in u for k in ["/lecture/", "/discussionprompt/"]):
                        current_url = pg.url
                        break

            # Fallback to active/first page URL
            if not current_url and context.pages:
                current_url = context.pages[0].url

            from quiz_pilot.course_orchestrator import CourseOrchestrator
            orch = CourseOrchestrator(cdp_url=self.cdp_url, max_concurrency=self.max_concurrency)

            # Handle my-learning dashboard: find the first in-progress course
            if "my-learning" in current_url:
                try:
                    course_links = await context.pages[0].evaluate('''() => {
                        return Array.from(document.querySelectorAll('a[href*="/learn/"]'))
                            .map(a => a.href)
                            .filter(h => !h.includes('/home') && !h.includes('/welcome'));
                    }''')
                    if course_links:
                        current_url = course_links[0]
                except Exception:
                    pass

            active_page = context.pages[0] if context.pages else None

            # Case A: Specialization page
            if "/specializations/" in current_url:
                return await orch.auto_complete_specialization(
                    spec_url=current_url,
                    prefer_direct_api=prefer_direct_api
                )

            # Case B: Single Course page
            if "/learn/" in current_url:
                import re
                m = re.search(r'(https://www\.coursera\.org/(?:organizations/[^/]+/)?learn/[^/?#]+)', current_url)
                course_base_url = m.group(1) if m else current_url
                return await orch.auto_complete_course(
                    course_url=course_base_url,
                    prefer_direct_api=prefer_direct_api,
                    page=active_page,
                    context=context
                )

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
    auto_submit: bool = True,
    target_url: Optional[str] = None
) -> Dict[str, Any]:
    """Synchronous wrapper for smart_multiworker."""
    scheduler = AsyncTabScheduler(cdp_url=cdp_url, max_concurrency=max_concurrency)
    return asyncio.run(scheduler.smart_multiworker(target_url=target_url, auto_submit=auto_submit))
