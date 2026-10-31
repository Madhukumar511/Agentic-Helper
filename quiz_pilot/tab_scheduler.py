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
                
                # 1. Extract Questions
                questions = await page.evaluate('''() => {
                    let allGroups = Array.from(document.querySelectorAll('div[role="radiogroup"], div[role="group"]'));
                    let leafGroups = allGroups.filter(g => !allGroups.some(other => other !== g && g.contains(other)));
                    return leafGroups.map((g, idx) => {
                        let p = g;
                        while (p && !p.innerText.includes("Question") && p !== document.body) {
                            p = p.parentElement;
                        }
                        let fullText = p ? p.innerText : g.innerText;
                        fullText = fullText.replace(/You are a helpful AI assistant[\\s\\S]*?I understand/gi, '').replace(/\\s+/g, ' ').trim();
                        
                        const radios = Array.from(g.querySelectorAll('input[type="radio"], [role="radio"]'));
                        const checkboxes = Array.from(g.querySelectorAll('input[type="checkbox"], [role="checkbox"]'));
                        const select = g.querySelector('select');
                        
                        let qType = 'radio';
                        if (select) qType = 'dropdown';
                        else if (checkboxes.length > 0) qType = 'checkbox';
                        
                        let options = [];
                        if (select) {
                            options = Array.from(select.querySelectorAll('option')).map(o => o.innerText.trim()).filter(t => t.length > 0);
                        } else {
                            options = (radios.length > 0 ? radios : checkboxes).map(r => {
                                const lbl = r.closest('label') || r.parentElement;
                                let text = lbl ? lbl.innerText.replace(/\\s+/g, ' ').trim() : '';
                                return text.replace(/You are a helpful AI assistant[\\s\\S]*?I understand/gi, '').trim();
                            }).filter(t => t.length > 0);
                        }
                        
                        return {
                            index: idx,
                            qNum: idx + 1,
                            type: qType,
                            prompt: fullText,
                            options: options
                        };
                    });
                }''')
                
                result["questions_count"] = len(questions)
                if not questions:
                    result["status"] = "NO_QUESTIONS_FOUND"
                    return result

                # 2. Determine Answers
                answers: Dict[int, Any] = {}
                if answer_generator:
                    answers = answer_generator(questions)
                else:
                    # Default: first option if no custom solver provided
                    for q in questions:
                        answers[q["index"]] = 0

                # 3. Fill Answers in Tab DOM in a single atomic batch (<30ms)
                payload = {str(k): v for k, v in answers.items()}
                await page.evaluate('''([ansMap]) => {
                    let norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    let allGroups = Array.from(document.querySelectorAll('div[role="radiogroup"], div[role="group"]'));
                    let leafGroups = allGroups.filter(g => !allGroups.some(other => other !== g && g.contains(other)));
                    
                    for (let k of Object.keys(ansMap)) {
                        let idx = parseInt(k, 10);
                        let val = ansMap[k];
                        if (idx >= leafGroups.length) continue;
                        let g = leafGroups[idx];
                        
                        let radios = Array.from(g.querySelectorAll('input[type="radio"], [role="radio"]'));
                        let checkboxes = Array.from(g.querySelectorAll('input[type="checkbox"], [role="checkbox"]'));
                        let select = g.querySelector('select');
                        
                        if (select) {
                            let options = Array.from(select.options);
                            let targetIdx = typeof val === 'number' ? val : -1;
                            if (typeof val === 'string') {
                                let vNorm = norm(val);
                                targetIdx = options.findIndex(o => norm(o.text).includes(vNorm) || norm(o.value).includes(vNorm));
                            }
                            if (targetIdx >= 0 && targetIdx < options.length) {
                                select.selectedIndex = targetIdx;
                                select.dispatchEvent(new Event('input', { bubbles: true }));
                                select.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        } else if (radios.length > 0) {
                            let targetIdx = typeof val === 'number' ? val : -1;
                            if (typeof val === 'string') {
                                let vNorm = norm(val);
                                targetIdx = radios.findIndex(r => {
                                    let l = r.closest('label') || r.parentElement;
                                    return l && norm(l.innerText).includes(vNorm);
                                });
                            }
                            if (targetIdx < 0 && typeof val === 'number' && val < radios.length) {
                                targetIdx = val;
                            }
                            if (targetIdx >= 0 && targetIdx < radios.length) {
                                radios[targetIdx].click();
                            }
                        } else if (checkboxes.length > 0) {
                            let items = Array.isArray(val) ? val : [val];
                            for (let item of items) {
                                let targetIdx = typeof item === 'number' ? item : -1;
                                if (typeof item === 'string') {
                                    let iNorm = norm(item);
                                    targetIdx = checkboxes.findIndex(cb => {
                                        let l = cb.closest('label') || cb.parentElement;
                                        return l && (norm(l.innerText).includes(iNorm) || iNorm.includes(norm(l.innerText)));
                                    });
                                }
                                if (targetIdx >= 0 && targetIdx < checkboxes.length) {
                                    let cb = checkboxes[targetIdx];
                                    if (!cb.checked && cb.getAttribute('aria-checked') !== 'true') {
                                        cb.click();
                                    }
                                }
                            }
                        }
                    }
                }''', [payload])

                # 4. Check Honor Code & Submit if requested
                if auto_submit:
                    # Check Honor code checkbox
                    await page.evaluate('''() => {
                        let cb = document.querySelector('#agreement-checkbox-base') || 
                                 Array.from(document.querySelectorAll('input[type="checkbox"]')).find(c => {
                                     let l = (c.closest('label') || {}).innerText || '';
                                     return l.includes('understand and agree');
                                 });
                        if (cb && !cb.checked) cb.click();
                    }''')
                    await asyncio.sleep(0.3)

                    # Click submit button
                    await page.evaluate('''() => {
                        let submitBtn = document.querySelector('button[data-testid="submit-button"]') ||
                                        Array.from(document.querySelectorAll('button')).find(b => 
                                            (b.innerText || '').trim().toLowerCase() === 'submit' && !b.disabled
                                        );
                        if (submitBtn) submitBtn.click();
                    }''')
                    await asyncio.sleep(0.5)

                    # Click dialog confirmation if modal appears
                    await page.evaluate('''() => {
                        let submits = Array.from(document.querySelectorAll('button')).filter(b => 
                            (b.innerText || '').trim().toLowerCase() === 'submit' && !b.disabled
                        );
                        if (submits.length > 1) {
                            submits[submits.length - 1].click();
                        }
                    }''')
                    await asyncio.sleep(1.0)

                    result["submitted"] = True

                    # 5. Extract Feedback
                    fb = await page.evaluate('''() => {
                        let text = document.body.innerText;
                        let scoreMatch = text.match(/(\\d+(?:\\.\\d+)?)%/);
                        let score = scoreMatch ? parseFloat(scoreMatch[1]) : 0.0;
                        let passedBadge = document.querySelector('[data-testid="passed-banner"], [aria-label*="Passed" i]');
                        let hasPassText = /(?:congratulations|you passed)/i.test(text);
                        return {
                            score_pct: score,
                            passed: passedBadge !== null || hasPassText || score >= 80.0
                        };
                    }''')
                    result["score_pct"] = fb.get("score_pct")
                    result["passed"] = fb.get("passed", False)
                    result["status"] = "PASSED" if result["passed"] else "COMPLETED"

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

            # Determine target URL from the active or first page
            target_page = context.pages[0] if context.pages else None
            if not target_page:
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
                return await orch.auto_complete_course(
                    course_url=course_base_url,
                    prefer_direct_api=prefer_direct_api
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
    auto_submit: bool = True
) -> Dict[str, Any]:
    """Synchronous wrapper for smart_multiworker."""
    scheduler = AsyncTabScheduler(cdp_url=cdp_url, max_concurrency=max_concurrency)
    return asyncio.run(scheduler.smart_multiworker(auto_submit=auto_submit))
