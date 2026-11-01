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
from quiz_pilot.browser_launcher import ensure_browser_visible_once

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


def _unknown_details(questions, unknown_indices):
    """Full prompt + option texts for unknown questions, so the driving
    agent can SOLVE them itself (its job) and complete the quiz in the
    same run - the human never does a quiz, and blind fills stay banned."""
    wanted = set(unknown_indices)
    details = []
    for q in questions:
        idx = q.get("index", 0)
        if idx in wanted:
            opts = []
            for o in q.get("options", []):
                opts.append(o.get("text", "") if isinstance(o, dict) else str(o))
            details.append({"index": idx, "prompt": q.get("prompt", ""), "options": opts})
    return details


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
        expected_url: str = None,
        answer_generator: Optional[Callable[[List[Dict[str, Any]]], Dict[int, Any]]] = None,
        auto_submit: bool = True
    ) -> Dict[str, Any]:
        """
        Isolated worker processing a single tab through the full assessment lifecycle
        with a 90-second timeout ceiling to prevent hanging.
        """
        async with semaphore:
            try:
                return await asyncio.wait_for(
                    self._process_single_tab_core(
                        page=page,
                        tab_index=tab_index,
                        expected_url=expected_url,
                        answer_generator=answer_generator,
                        auto_submit=auto_submit
                    ),
                    timeout=90.0
                )
            except asyncio.TimeoutError:
                logger.error(f"Tab {tab_index} processing timed out after 90 seconds.")
                cur_url = getattr(page, "url", "") or expected_url or ""
                return {
                    "tab_index": tab_index,
                    "title": "",
                    "url": cur_url,
                    "questions_count": 0,
                    "submitted": False,
                    "score_pct": None,
                    "passed": False,
                    "status": "TIMEOUT",
                    "error": "Tab processing timed out after 90 seconds"
                }

    async def _process_single_tab_core(
        self,
        page: Page,
        tab_index: int,
        expected_url: str = None,
        answer_generator: Optional[Callable[[List[Dict[str, Any]]], Dict[int, Any]]] = None,
        auto_submit: bool = True
    ) -> Dict[str, Any]:
        """
        Core implementation of isolated single tab processing lifecycle:
        DETECTION -> EXTRACTION -> ANSWERING -> SUBMISSION -> FEEDBACK.
        """
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

            # NO GUESSING: questions without a known answer stay
            # UNANSWERED and are reported (previously default-filled
            # with option 0 - a silent coin flip on a real attempt).
            _known = {
                q.get("index", 0) for q in questions
                if q.get("index", 0) in answers or str(q.get("index", 0)) in answers
            }
            unknown_indices = [q.get("index", 0) for q in questions if q.get("index", 0) not in _known]
            coverage = (len(_known) / len(questions)) if questions else 0.0
            result["coverage_pct"] = round(coverage * 100, 1)
            result["unknown_questions"] = unknown_indices
            result["unknown_questions_detail"] = _unknown_details(questions, unknown_indices)

            # 3. Fill Answers via LMS Adapter (fill only)
            if hasattr(adapter, "batch_fill_answers_async"):
                await adapter.batch_fill_answers_async(answers, auto_submit=False)
            elif hasattr(adapter, "batch_fill_answers"):
                adapter.batch_fill_answers(answers, auto_submit=False)
            else:
                for q_idx, val in answers.items():
                    await adapter.fill_answer_async(int(q_idx), val)

            # 4. Handle Submission & Feedback - 80% FLOOR + SINGLE ATTEMPT:
            # the floor only stops a wasted submission; it is NOT a score
            # target. The target is the maximum grade: every question the
            # agent can genuinely answer must be answered before this.
            # Submit only when known answers cover >= 80% of questions.
            # Below the gate the known answers stay filled, NOTHING is
            # submitted (zero attempts burned), and the run reports the
            # uncertain questions instead of gambling an attempt on them.
            if auto_submit and coverage < 0.80:
                result["status"] = "NEEDS_REVIEW_NOT_SUBMITTED"
                result["submitted"] = False
            elif auto_submit:
                await adapter.submit_assessment_async()
                result["submitted"] = True
                result["attempts_used"] = 1
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
                        attempt_num=self.attempt_mgr.next_attempt_num(quiz_key),
                        questions=questions,
                        answers=answers,
                        feedback=fb_map,
                        score_pct=fb.get("score_pct")
                    )
                except Exception:
                    pass
                # FAIL-RETRY UNTIL PASS (user policy): a PASS is final
                # and is never retaken to improve the score, but a FAILED
                # quiz means NO certificate - so after a fail the agent
                # keeps re-attempting, each time using the latest feedback
                # (correct answers locked, wrong options eliminated,
                # failed questions re-solved), UNTIL THE QUIZ PASSES.
                # Rounds stop early only when there is nothing new to
                # submit (no questions extractable, or known answers
                # under the 80% floor) or after 9 retries (loop guard).
                _retry_rounds = 0
                while result.get("passed") is False and _retry_rounds < 9:
                    _retry_rounds += 1
                    try:
                        retry_questions = await adapter.extract_questions_async()
                    except Exception:
                        retry_questions = []
                    if not retry_questions:
                        break
                    r_answers = self.attempt_mgr.get_retry_answers(retry_questions, quiz_id=quiz_key)
                    if answer_generator:
                        try:
                            _gen2 = answer_generator(retry_questions)
                            if _gen2:
                                r_answers.update(_gen2)
                        except Exception:
                            pass
                    _r_known = {
                        q.get("index", 0) for q in retry_questions
                        if q.get("index", 0) in r_answers or str(q.get("index", 0)) in r_answers
                    }
                    if (len(_r_known) / len(retry_questions)) < 0.80:
                        break
                    if hasattr(adapter, "batch_fill_answers_async"):
                        await adapter.batch_fill_answers_async(r_answers, auto_submit=False)
                    elif hasattr(adapter, "batch_fill_answers"):
                        adapter.batch_fill_answers(r_answers, auto_submit=False)
                    else:
                        for _qi, _qv in r_answers.items():
                            await adapter.fill_answer_async(int(_qi), _qv)
                    await adapter.submit_assessment_async()
                    result["attempts_used"] = result.get("attempts_used", 1) + 1
                    await asyncio.sleep(0.5)
                    try:
                        fb2 = await adapter.extract_feedback_async()
                    except Exception:
                        fb2 = {}
                    result["score_pct"] = fb2.get("score_pct")
                    result["passed"] = fb2.get("passed", False)
                    result["status"] = "PASSED" if result["passed"] else "COMPLETED"
                    try:
                        fb_map2 = fb2.get("feedback")
                        if fb_map2 is None:
                            fb_map2 = {q["index"]: fb2.get("passed", False) for q in retry_questions} if fb2.get("passed") else {}
                        self.attempt_mgr.record_attempt(
                            quiz_id=quiz_key,
                            attempt_num=self.attempt_mgr.next_attempt_num(quiz_key),
                            questions=retry_questions,
                            answers=r_answers,
                            feedback=fb_map2,
                            score_pct=fb2.get("score_pct")
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
        ensure_browser_visible_once()
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

            async def _run_worker_tab(tab, idx):
                try:
                    return await asyncio.wait_for(
                        self._process_single_tab(
                            page=tab,
                            tab_index=idx,
                            semaphore=semaphore,
                            answer_generator=answer_generator,
                            auto_submit=auto_submit,
                            expected_url=tab.url
                        ),
                        timeout=90.0
                    )
                except asyncio.TimeoutError:
                    return {
                        "tab_index": idx,
                        "title": "",
                        "url": getattr(tab, "url", ""),
                        "questions_count": 0,
                        "submitted": False,
                        "score_pct": None,
                        "passed": False,
                        "status": "TIMEOUT",
                        "error": "Tab processing timed out after 90 seconds"
                    }

            tasks = [_run_worker_tab(tab, idx) for idx, tab in enumerate(tabs)]
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
        ensure_browser_visible_once()
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
            except Exception as e:
                return {"error": f"Failed to connect to browser on CDP {self.cdp_url}: {e}"}

            context = browser.contexts[0] if browser.contexts else await browser.new_context()

            course_urls = [u for u in urls if "/learn/" in u or "/specializations/" in u]
            if course_urls and len(course_urls) == len(urls):
                from quiz_pilot.course_orchestrator import CourseOrchestrator
                orch = CourseOrchestrator(cdp_url=self.cdp_url, max_concurrency=self.max_concurrency)

                course_results = []
                all_items = []
                total_passed = 0
                for u in urls:
                    c_pg = await context.new_page()
                    try:
                        if "/specializations/" in u:
                            r = await orch.auto_complete_specialization(u)
                        else:
                            r = await orch.auto_complete_course(u, page=c_pg, context=context, concurrency=self.max_concurrency)
                    except Exception as exc:
                        r = {"error": str(exc), "url": u}
                    finally:
                        try:
                            await c_pg.close()
                        except Exception:
                            pass
                    course_results.append(r)
                    if isinstance(r, dict):
                        items = r.get("items", []) or r.get("results", []) or r.get("details", [])
                        all_items.extend(items)
                        total_passed += sum(1 for it in items if isinstance(it, dict) and (it.get("passed") or it.get("status") == "completed"))

                return {
                    "total_tabs": len(urls),
                    "passed_count": total_passed,
                    "concurrency": self.max_concurrency,
                    "results": all_items,
                    "course_results": course_results
                }

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
        ensure_browser_visible_once()
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

            # 2. Determine target URL and target page
            if target_url:
                current_url = target_url
                target_page = next((pg for pg in context.pages if target_url.split("?")[0] in pg.url), None)
            else:
                # Determine the target course/specialization page WITHOUT grabbing
                # pages[0]: in multi-tab runs the first page may belong to another
                # worker. Only an unambiguous single course/spec page may route.
                course_pages = [
                    pg for pg in context.pages
                    if "/specializations/" in pg.url or "/learn/" in pg.url
                ]
                distinct_courses = {pg.url.split("?")[0] for pg in course_pages}
                if len(distinct_courses) > 1:
                    spec_pages = [pg for pg in course_pages if "/specializations/" in pg.url]
                    if len(spec_pages) == 1:
                        target_page = spec_pages[0]
                    else:
                        from quiz_pilot.course_orchestrator import CourseOrchestrator
                        orch = CourseOrchestrator(cdp_url=self.cdp_url, max_concurrency=self.max_concurrency)

                        batch_res = []
                        all_items = []
                        total_passed = 0
                        for pg in course_pages:
                            import re
                            m = re.search(r'(https://www\.coursera\.org/(?:organizations/[^/]+/)?learn/[^/?#]+)', pg.url)
                            c_url = m.group(1) if m else pg.url
                            try:
                                r = await orch.auto_complete_course(
                                    course_url=c_url,
                                    prefer_direct_api=prefer_direct_api,
                                    page=pg,
                                    context=context,
                                    concurrency=self.max_concurrency
                                )
                            except Exception as exc:
                                r = {"error": str(exc), "url": pg.url}
                            batch_res.append(r)
                            if isinstance(r, dict):
                                items = r.get("items", []) or r.get("results", [])
                                all_items.extend(items)
                                total_passed += sum(1 for it in items if isinstance(it, dict) and (it.get("passed") or it.get("status") == "completed"))
                        return {
                            "status": "completed",
                            "courses_completed": len(course_pages),
                            "total_tabs": len(course_pages),
                            "passed_count": total_passed,
                            "results": all_items,
                            "details": batch_res
                        }
                else:
                    target_page = course_pages[0] if course_pages else None

                if not target_page:
                    if quiz_tabs:
                        return await self.run_parallel_batch(auto_submit=auto_submit)
                    return {"error": "No open browser pages found."}
                current_url = target_page.url

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
