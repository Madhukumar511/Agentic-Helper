"""
Programming Assignment Automation Engine for Quiz-Pilot / Agentic-Helper.

Handles:
- Problem specification & starter code extraction (zip, tar.gz, py, ipynb).
- Automated solution archive upload & honor code submission.
- Remote autograder result polling, score verification, and error traceback extraction.
- In-browser Jupyter / Lab assignment detection.
"""

import os
import re
import time
import asyncio
import logging
import urllib.request
from typing import Dict, List, Any, Optional
from playwright.async_api import async_playwright, Page, Browser

logger = logging.getLogger("quiz_pilot.programming_solver")


class ProgrammingAssignmentManager:
    """
    Automates LMS programming assignment workflows across Coursera, Canvas, and edX.
    """
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url

    @staticmethod
    def is_programming_page(url: str, text: str) -> bool:
        """Determines if the active page is a programming assignment or lab."""
        u_lower = url.lower()
        t_lower = text.lower()
        url_match = any(kw in u_lower for kw in [
            "/programming/", "/peer/", "/assignment-submission/",
            "/supplement/", "lab", "notebook", "workspace"
        ])
        text_match = any(kw in t_lower for kw in [
            "programming assignment", "autograder", "starter code",
            "upload your file", "submit your assignment", "grader output",
            "submit code", "test cases"
        ])
        return url_match or text_match

    @staticmethod
    async def find_target_page(browser: Browser, target_keyword: Optional[str] = None) -> Optional[Page]:
        """Locates the active programming assignment tab."""
        all_pages = []
        for ctx in browser.contexts:
            for p in ctx.pages:
                all_pages.append(p)

        if not all_pages:
            return None

        if target_keyword:
            kw = target_keyword.lower()
            for p in all_pages:
                try:
                    title = p.title()
                    if asyncio.iscoroutine(title):
                        title = await title
                    title_str = (str(title) if title else "").lower()
                    url_str = getattr(p, "url", "").lower()
                    if kw in url_str or kw in title_str:
                        return p
                except Exception:
                    pass

        # Match programming/assignment keywords
        prog_keywords = ["programming", "peer", "assignment-submission", "lab", "coursera", "canvas"]
        for kw in prog_keywords:
            for p in all_pages:
                try:
                    url_str = getattr(p, "url", "").lower()
                    if kw in url_str:
                        return p
                except Exception:
                    pass

        # Tab-ownership rule: same as mcp_server - never fall back to the
        # first tab when several are open; it may be another worker's tab.
        if len(all_pages) == 1:
            return all_pages[0]
        return None

    async def extract_task_spec(
        self,
        page: Optional[Page] = None,
        tab_keyword: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Scrapes programming assignment instructions, starter code links, and upload requirements.
        """
        async def _extract(p: Page) -> Dict[str, Any]:
            url = p.url
            title = await p.title()

            spec = await p.evaluate('''() => {
                let h1 = document.querySelector('h1[data-testid="header-title"], h1.cds-119, h1');
                let taskTitle = h1 ? h1.innerText.trim() : document.title;

                // 1. Extract Instructions and Description
                let instructEls = Array.from(document.querySelectorAll(
                    'div[data-testid="assignment-instructions"], div.rc-AssignmentInstructions, div.c-assignment-instructions, div[role="main"], article'
                ));
                let instructionText = instructEls.map(el => el.innerText).join('\\n\\n').trim();
                if (!instructionText) {
                    instructionText = document.body.innerText.substring(0, 3000);
                }

                // 2. Discover Downloadable Starter Code Files
                let starterFiles = [];
                let links = Array.from(document.querySelectorAll('a[href]'));
                links.forEach(a => {
                    let href = a.href || '';
                    let text = a.innerText.trim();
                    let lowerHref = href.toLowerCase();
                    let isCodeFile = [
                        '.zip', '.tar.gz', '.tgz', '.tar', '.py',
                        '.ipynb', '.java', '.cpp', '.c', '.go',
                        '.sh', '.r', '.sql', 'download'
                    ].some(ext => lowerHref.includes(ext) || text.toLowerCase().includes(ext));

                    if (isCodeFile && !starterFiles.some(f => f.url === href)) {
                        starterFiles.push({
                            name: text || href.split('/').pop().split('?')[0],
                            url: href
                        });
                    }
                });

                // 3. Inspect Submission Inputs
                let fileInputs = Array.from(document.querySelectorAll('input[type="file"]'));
                let hasFileInput = fileInputs.length > 0;
                let acceptedTypes = [];
                fileInputs.forEach(fi => {
                    if (fi.accept) {
                        acceptedTypes.push(fi.accept);
                    }
                });

                let textAreas = Array.from(document.querySelectorAll('textarea, div[contenteditable="true"]')).map(t => ({
                    placeholder: t.getAttribute('placeholder') || '',
                    name: t.getAttribute('name') || ''
                }));

                // 4. Detect In-Browser Lab / Jupyter Launch Button
                let labBtn = Array.from(document.querySelectorAll('a, button')).find(el => {
                    let t = (el.innerText || '').toLowerCase();
                    return t.includes('open tool') || t.includes('launch lab') || t.includes('open lab') || t.includes('open notebook');
                });
                let labUrl = labBtn ? (labBtn.href || labBtn.getAttribute('data-url') || 'detected') : null;

                // 5. Detect Autograder / Submission Status
                let bodyText = document.body.innerText;
                let scoreMatch = bodyText.match(/(\\d+(?:\\.\\d+)?)%/);
                let latestScore = scoreMatch ? parseFloat(scoreMatch[1]) : null;

                let isPassed = bodyText.includes('Passed') || bodyText.includes('Congratulations') || (latestScore !== null && latestScore >= 80.0);

                let taskType = 'file_upload';
                if (labUrl) taskType = 'in_browser_lab';
                else if (window.location.href.includes('/peer/')) taskType = 'peer_review';
                else if (!hasFileInput && textAreas.length > 0) taskType = 'text_submission';

                return {
                    title: taskTitle,
                    task_type: taskType,
                    has_file_input: hasFileInput,
                    accepted_types: acceptedTypes,
                    starter_files: starterFiles,
                    text_inputs_count: textAreas.length,
                    lab_launch_url: labUrl,
                    latest_score: latestScore,
                    is_passed: isPassed,
                    instructions_snippet: instructionText.substring(0, 2000)
                };
            }''')

            spec["url"] = url
            return spec

        if page:
            return await _extract(page)

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(self.cdp_url)
            target = await self.find_target_page(browser, tab_keyword)
            if not target:
                return {"error": "No matching programming assignment page found."}
            return await _extract(target)

    async def upload_and_submit(
        self,
        file_path: str,
        page: Optional[Page] = None,
        tab_keyword: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Attaches the local solution file/archive to the LMS input[type='file'],
        signs the honor code agreement, and clicks Submit.
        """
        abs_path = os.path.abspath(file_path)
        if not os.path.exists(abs_path):
            return {"success": False, "error": f"Solution file not found on disk: {abs_path}"}

        async def _upload(p: Page) -> Dict[str, Any]:
            # 1. Locate file input element
            file_input = p.locator('input[type="file"]')
            count = await file_input.count()
            if count == 0:
                # Check for hidden or lazy-loaded dropzone
                dropzone = p.locator('div[data-testid="dropzone"], div.dropzone, div[role="button"]:has-text("Upload")')
                if await dropzone.count() > 0:
                    try:
                        await dropzone.first.click()
                        await asyncio.sleep(0.5)
                        file_input = p.locator('input[type="file"]')
                        count = await file_input.count()
                    except Exception:
                        pass

            if count == 0:
                return {
                    "success": False,
                    "error": "No input[type='file'] element found on this assignment page. Verify this is a file upload assignment."
                }

            # 2. Attach the local file
            logger.info(f"Attaching solution archive: {abs_path}")
            await file_input.first.set_input_files(abs_path)
            await asyncio.sleep(1.0)

            # 3. Check Honor Code agreement checkbox (#agreement-checkbox-base)
            await p.evaluate('''() => {
                let cb = document.querySelector('#agreement-checkbox-base, input[name*="agreement" i]') ||
                         Array.from(document.querySelectorAll('input[type="checkbox"], [role="checkbox"]')).find(c => {
                             let l = (c.closest('label') || c.parentElement || {}).innerText || '';
                             return l.toLowerCase().includes('understand and agree') || l.toLowerCase().includes('honor code');
                         });
                if (cb && !cb.checked && cb.getAttribute('aria-checked') !== 'true') {
                    cb.click();
                }
            }''')
            await asyncio.sleep(0.5)

            # 4. Click Submit Button
            submitted = await p.evaluate('''() => {
                let submitBtn = document.querySelector('button[data-testid="submit-button"]') ||
                                Array.from(document.querySelectorAll('button')).find(b => {
                                    let t = (b.innerText || '').trim().toLowerCase();
                                    return (t === 'submit' || t === 'submit assignment') && !b.disabled;
                                });
                if (submitBtn) {
                    submitBtn.click();
                    return true;
                }
                return false;
            }''')

            if not submitted:
                return {
                    "success": False,
                    "error": "Submit button was not clickable or was disabled. Check required fields or file validation."
                }

            await asyncio.sleep(1.0)

            # 5. Handle submission confirmation modal if present
            await p.evaluate('''() => {
                let dialog = document.querySelector('div[role="dialog"], [data-testid="assignment-view-tunnel-vision"]');
                if (dialog) {
                    let confirmBtn = Array.from(dialog.querySelectorAll('button')).find(b => {
                        let t = (b.innerText || '').trim().toLowerCase();
                        return t === 'submit' || t === 'continue' || t === 'yes';
                    });
                    if (confirmBtn) confirmBtn.click();
                }
            }''')

            return {
                "success": True,
                "file_path": abs_path,
                "file_name": os.path.basename(abs_path),
                "file_size_bytes": os.path.getsize(abs_path),
                "timestamp": time.time(),
                "message": "Solution file successfully uploaded and submitted to LMS autograder."
            }

        if page:
            return await _upload(page)

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(self.cdp_url)
            target = await self.find_target_page(browser, tab_keyword)
            if not target:
                return {"success": False, "error": "No matching programming assignment page found."}
            return await _upload(target)

    async def poll_autograder_results(
        self,
        page: Optional[Page] = None,
        tab_keyword: Optional[str] = None,
        timeout_sec: int = 120,
        poll_interval: int = 3
    ) -> Dict[str, Any]:
        """
        Polls the LMS autograder feedback view until grading finishes or timeout is reached.
        Extracts test breakdown, score, and error logs.
        """
        start_time = time.time()

        async def _poll_loop(p: Page) -> Dict[str, Any]:
            while (time.time() - start_time) < timeout_sec:
                # Refresh feedback section or inspect DOM
                res = await p.evaluate('''() => {
                    let text = document.body.innerText;
                    let isGrading = /(?:grading in progress|evaluating|queued|running tests|processing submission)/i.test(text);
                    let scoreMatch = text.match(/(\\d+(?:\\.\\d+)?)%/);
                    let ptsMatch = text.match(/(\\d+)\\s*\\/\\s*(\\d+)\\s*points?/i);
                    let score = scoreMatch ? parseFloat(scoreMatch[1]) : null;
                    if (score === null && ptsMatch) {
                        let earned = parseFloat(ptsMatch[1]);
                        let total = parseFloat(ptsMatch[2]);
                        if (total > 0) score = Math.round((earned / total) * 100);
                    }

                    // Extract Autograder Log Blocks
                    let logBlocks = Array.from(document.querySelectorAll(
                        'pre, code, div[data-testid="autograder-output"], div.rc-SubmissionFeedback pre'
                    )).map(el => el.innerText.trim()).filter(t => t.length > 0);

                    // Extract Individual Test Case Items
                    let testItems = [];
                    let testEls = Array.from(document.querySelectorAll('div[data-testid="part-submission-container"], tr, div.rc-TestResult'));
                    testEls.forEach(el => {
                        let t = el.innerText || '';
                        if (t.includes('Test') || t.includes('Part') || t.includes('points')) {
                            let pass = t.includes('Pass') || t.includes('Correct') || el.querySelector('svg[aria-label="Correct"]');
                            let fail = t.includes('Fail') || t.includes('Incorrect') || el.querySelector('svg[aria-label="Incorrect"]');
                            if (pass || fail) {
                                testItems.push({
                                    summary: t.substring(0, 100).replace(/\\s+/g, ' ').trim(),
                                    passed: pass ? true : false
                                });
                            }
                        }
                    });

                    let passBadge = document.querySelector('[data-testid="passed-banner"], [aria-label*="Passed" i]');
                    let isPassed = passBadge !== null || (score !== null && score >= 80.0);

                    return {
                        is_grading: isGrading,
                        score_pct: score,
                        passed: isPassed,
                        test_cases: testItems,
                        grader_output: logBlocks.join('\\n---\\n').substring(0, 4000)
                    };
                }''')

                if not res["is_grading"] and res["score_pct"] is not None:
                    res["status"] = "PASSED" if res["passed"] else "COMPLETED"
                    res["elapsed_sec"] = int(time.time() - start_time)
                    return res

                await asyncio.sleep(poll_interval)

            return {
                "status": "TIMEOUT",
                "message": f"Autograder did not finish within {timeout_sec} seconds. Check browser tab manually.",
                "elapsed_sec": int(time.time() - start_time)
            }

        if page:
            return await _poll_loop(page)

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(self.cdp_url)
            target = await self.find_target_page(browser, tab_keyword)
            if not target:
                return {"error": "No matching programming assignment page found."}
            return await _poll_loop(target)

    def download_starter_file(self, download_url: str, dest_dir: str = ".") -> str:
        """
        Downloads a starter code archive directly into the local workspace.
        """
        os.makedirs(dest_dir, exist_ok=True)
        filename = download_url.split("?")[0].split("/")[-1]
        if not filename or "." not in filename:
            filename = "starter_assignment.zip"

        dest_file = os.path.join(dest_dir, filename)
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "Mozilla/5.0 AgenticHelper/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15.0) as resp, open(dest_file, "wb") as f:
            f.write(resp.read())

        return os.path.abspath(dest_file)


# Synchronous convenience functions
def inspect_programming_task_sync(cdp_url: str = "http://127.0.0.1:9222", tab_keyword: Optional[str] = None) -> Dict[str, Any]:
    mgr = ProgrammingAssignmentManager(cdp_url=cdp_url)
    return asyncio.run(mgr.extract_task_spec(tab_keyword=tab_keyword))

def submit_code_file_sync(file_path: str, cdp_url: str = "http://127.0.0.1:9222", tab_keyword: Optional[str] = None) -> Dict[str, Any]:
    mgr = ProgrammingAssignmentManager(cdp_url=cdp_url)
    return asyncio.run(mgr.upload_and_submit(file_path=file_path, tab_keyword=tab_keyword))

def poll_autograder_results_sync(cdp_url: str = "http://127.0.0.1:9222", tab_keyword: Optional[str] = None, timeout_sec: int = 120) -> Dict[str, Any]:
    mgr = ProgrammingAssignmentManager(cdp_url=cdp_url)
    return asyncio.run(mgr.poll_autograder_results(tab_keyword=tab_keyword, timeout_sec=timeout_sec))
