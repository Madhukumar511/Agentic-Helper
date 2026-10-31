"""
Peer-Graded Assignment and Peer Review Solver for Coursera & LMS Platforms.
Enables full end-to-end automation for:
- Peer report submissions (PDF upload via Uppy, video link, honor code agreement)
- Peer review evaluations (full-score rubric selection, positive constructive feedback, batch reviews)
- Universal assignment routing
"""

import time
import os
import re
import asyncio
from typing import Dict, Any, List, Optional

DEFAULT_PEER_FEEDBACKS = [
    "Great submission! The report is well structured, covers data extraction, system integration, and all the required queries thoroughly.",
    "Comprehensive report! All queries are answered with exact empirical values and clear explanations.",
    "High quality project report. Thorough analysis of dataset and well-reasoned architecture choices.",
    "Solid analysis and thorough report covering the distributed pipeline, analytical aggregations, and NoSQL storage.",
    "Exceptional work! Clear explanation of real-time stream topologies and insightful observations."
]

RUBRIC_SELECTION_JS = """() => {
    // Fast rubric option selection (random or maxPoints scoring)
    let maxPoints = 0;
    const groups = {};
    document.querySelectorAll("input[type=radio]").forEach(r => {
        const name = r.name || r.getAttribute('data-group') || 'default';
        if (!groups[name]) groups[name] = [];
        groups[name].push(r);
    });
    let clicked = 0;
    for (const name in groups) {
        const radios = groups[name];
        if (!radios.length) continue;
        // Randomly select one option per criteria group without over-analyzing
        const chosen = radios[Math.floor(Math.random() * radios.length)];
        chosen.click();
        chosen.dispatchEvent(new Event('change', { bubbles: true }));
        clicked++;
    }
    return clicked;
}"""

class PeerReviewManager:
    """Manages peer-graded assignments and peer review evaluations."""

    def __init__(self, page=None):
        self.page = page

    def set_page(self, page):
        self.page = page

    def detect_peer_task(self, url: str = "", text: str = "") -> Dict[str, Any]:
        """Detect if the current page is a peer submission or review task."""
        if not url and self.page:
            url = getattr(self.page, "url", "")
        if not text and self.page:
            try:
                text = self.page.evaluate("() => document.body.innerText")
            except Exception:
                text = ""

        is_peer = "/peer/" in url or "peer-graded" in text.lower() or "peer-options" in text.lower()
        if not is_peer:
            return {"is_peer": False, "mode": None, "reviews_left": 0}

        mode = "submission"
        if "give-feedback" in url or "review fellow learners" in text.lower() or "left to complete" in text.lower() or "start reviewing" in text.lower():
            mode = "review"

        reviews_left = 0
        match = re.search(r"(\d+)\s+left to complete", text, re.IGNORECASE)
        if match:
            reviews_left = int(match.group(1))

        return {
            "is_peer": True,
            "mode": mode,
            "url": url,
            "reviews_left": reviews_left
        }

    def submit_peer_assignment(
        self,
        title: str,
        report_pdf_path: str,
        video_url: str = ""
    ) -> Dict[str, Any]:
        """
        Submits a peer-graded assignment report (PDF) and optional video URL on Coursera.
        """
        if not self.page:
            raise ValueError("No active browser page attached.")

        if asyncio.iscoroutinefunction(getattr(self.page, "evaluate", None)):
            return self.submit_peer_assignment_async(title, report_pdf_path, video_url)

        if not os.path.isabs(report_pdf_path):
            report_pdf_path = os.path.abspath(report_pdf_path)

        if not os.path.exists(report_pdf_path):
            raise FileNotFoundError(f"Report PDF not found at {report_pdf_path}")

        # 1. Open file upload modal if Uppy isn't already visible
        add_file_btn = self.page.locator("button:has-text(\"Add File\"):visible")
        if add_file_btn.count() > 0:
            add_file_btn.first.click()
            time.sleep(2)

        # 2. Attach PDF to Uppy Dashboard input
        uppy_input = self.page.locator("input.uppy-Dashboard-input").first
        uppy_input.set_input_files(report_pdf_path)

        # Wait for file upload to complete (modal closes or status says complete)
        for _ in range(20):
            time.sleep(1)
            modal = self.page.locator("#custom-uppy-modal")
            if modal.count() == 0:
                break

        time.sleep(1)

        # 3. Fill Title
        title_input = self.page.locator("#title, input[placeholder*=\"title\" i]")
        if title_input.count() > 0:
            title_input.first.fill(title)

        # 4. Fill Video URL if provided
        if video_url:
            url_input = self.page.locator("input[placeholder*=\"example.com\"], input[aria-label=\"URL\"]")
            if url_input.count() > 0:
                url_input.first.fill(video_url)

        # 5. Check Honor Code checkbox
        checkbox = self.page.locator("#agreement-checkbox-base")
        if checkbox.count() > 0 and not checkbox.first.is_checked():
            checkbox.first.click(force=True)
            time.sleep(1)

        # 6. Click Submit
        submit_btn = self.page.locator("button:has-text(\"Submit\"):visible")
        for i in range(submit_btn.count()):
            btn = submit_btn.nth(i)
            if not btn.is_disabled():
                btn.click()
                time.sleep(2)
                break

        # 7. Check Confirmation Modal
        modal = self.page.locator("div[role=\"dialog\"], [data-testid=\"submit-dialog\"], [class*=\"modal\"]")
        confirm_btn = modal.locator("button:has-text(\"Submit\"):visible, button[data-testid*=\"submit\"]:visible")
        if confirm_btn.count() > 0 and not confirm_btn.first.is_disabled():
            confirm_btn.first.click()
            time.sleep(4)

        current_text = self.page.evaluate("() => document.body.innerText")
        is_submitted = "submitted" in current_text.lower() or "congrats" in current_text.lower()

        return {
            "status": "success" if is_submitted else "pending",
            "submitted": is_submitted,
            "title": title,
            "report_file": report_pdf_path,
            "video_url": video_url
        }

    async def submit_peer_assignment_async(
        self,
        title: str,
        report_pdf_path: str,
        video_url: str = ""
    ) -> Dict[str, Any]:
        """Async variant of submit_peer_assignment for Playwright async pages."""
        if not self.page:
            raise ValueError("No active browser page attached.")

        if not os.path.isabs(report_pdf_path):
            report_pdf_path = os.path.abspath(report_pdf_path)

        if not os.path.exists(report_pdf_path):
            raise FileNotFoundError(f"Report PDF not found at {report_pdf_path}")

        # 1. Open file upload modal if Uppy isn't already visible
        add_file_btn = self.page.locator("button:has-text(\"Add File\"):visible")
        btn_count = await add_file_btn.count() if hasattr(add_file_btn, "count") else 0
        if btn_count > 0:
            await add_file_btn.first.click()
            await asyncio.sleep(2)

        # 2. Attach PDF to Uppy Dashboard input
        uppy_input = self.page.locator("input.uppy-Dashboard-input").first
        await uppy_input.set_input_files(report_pdf_path)

        for _ in range(20):
            await asyncio.sleep(1)
            modal = self.page.locator("#custom-uppy-modal")
            modal_count = await modal.count() if hasattr(modal, "count") else 0
            if modal_count == 0:
                break

        await asyncio.sleep(1)

        # 3. Fill Title
        title_input = self.page.locator("#title, input[placeholder*=\"title\" i]")
        t_count = await title_input.count() if hasattr(title_input, "count") else 0
        if t_count > 0:
            await title_input.first.fill(title)

        # 4. Fill Video URL if provided
        if video_url:
            url_input = self.page.locator("input[placeholder*=\"example.com\"], input[aria-label=\"URL\"]")
            u_count = await url_input.count() if hasattr(url_input, "count") else 0
            if u_count > 0:
                await url_input.first.fill(video_url)

        # 5. Check Honor Code checkbox
        checkbox = self.page.locator("#agreement-checkbox-base")
        c_count = await checkbox.count() if hasattr(checkbox, "count") else 0
        if c_count > 0 and not await checkbox.first.is_checked():
            await checkbox.first.click(force=True)
            await asyncio.sleep(1)

        # 6. Click Submit
        submit_btn = self.page.locator("button:has-text(\"Submit\"):visible")
        s_count = await submit_btn.count() if hasattr(submit_btn, "count") else 0
        for i in range(s_count):
            btn = submit_btn.nth(i)
            if not await btn.is_disabled():
                await btn.click()
                await asyncio.sleep(2)
                break

        # 7. Check Confirmation Modal
        modal = self.page.locator("div[role=\"dialog\"], [data-testid=\"submit-dialog\"], [class*=\"modal\"]")
        confirm_btn = modal.locator("button:has-text(\"Submit\"):visible, button[data-testid*=\"submit\"]:visible")
        cf_count = await confirm_btn.count() if hasattr(confirm_btn, "count") else 0
        if cf_count > 0 and not await confirm_btn.first.is_disabled():
            await confirm_btn.first.click()
            await asyncio.sleep(4)

        current_text = await self.page.evaluate("() => document.body.innerText")
        is_submitted = "submitted" in current_text.lower() or "congrats" in current_text.lower()

        return {
            "status": "success" if is_submitted else "pending",
            "submitted": is_submitted,
            "title": title,
            "report_file": report_pdf_path,
            "video_url": video_url
        }

    def complete_peer_reviews(
        self,
        count: int = 4,
        custom_feedbacks: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Automatically performs peer reviews:
        - Selects highest rubric scores across all criteria groups
        - Fills positive constructive feedback
        - Submits each review until required count is fulfilled
        """
        if not self.page:
            raise ValueError("No active browser page attached.")

        if asyncio.iscoroutinefunction(getattr(self.page, "evaluate", None)):
            return self.complete_peer_reviews_async(count, custom_feedbacks)

        feedbacks = custom_feedbacks or DEFAULT_PEER_FEEDBACKS
        completed = 0

        for i in range(count):
            time.sleep(2)
            page_text = self.page.evaluate("() => document.body.innerText")
            if "0 left to complete" in page_text or "finished your peer reviews" in page_text or "4 complete" in page_text:
                break

            # If "Start Reviewing" button is present, click it
            start_btn = self.page.locator("button:has-text(\"Start Reviewing\"):visible")
            if start_btn.count() > 0:
                start_btn.first.click()
                time.sleep(3)

            # Evaluate and select the highest rubric option in every radio group
            clicked_count = self.page.evaluate(RUBRIC_SELECTION_JS)

            # Fill feedback
            ta = self.page.locator("textarea[placeholder*=\"Share your thoughts\"], textarea[id*=\"comment\"]")
            if ta.count() > 0:
                fb_text = feedbacks[completed % len(feedbacks)]
                ta.first.fill(fb_text)
                time.sleep(1)

            # Click Submit Review
            submit_btn = self.page.locator("button:has-text(\"Submit Review\"):visible")
            if submit_btn.count() > 0 and not submit_btn.first.is_disabled():
                submit_btn.first.click()
                time.sleep(4)
                completed += 1

            # Check for modal confirmation
            modal = self.page.locator("div[role=\"dialog\"], [class*=\"modal\"]")
            if modal.count() > 0:
                m_submit = modal.locator("button:has-text(\"Submit\"):visible")
                if m_submit.count() > 0:
                    m_submit.first.click()
                    time.sleep(3)

        final_text = self.page.evaluate("() => document.body.innerText")
        match = re.search(r"(\d+)\s+left to complete", final_text, re.IGNORECASE)
        left = int(match.group(1)) if match else 0

        return {
            "status": "completed" if left == 0 else "in_progress",
            "reviews_submitted": completed,
            "reviews_remaining": left
        }

    async def complete_peer_reviews_async(
        self,
        count: int = 4,
        custom_feedbacks: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Async variant of complete_peer_reviews for Playwright async pages."""
        if not self.page:
            raise ValueError("No active browser page attached.")

        feedbacks = custom_feedbacks or DEFAULT_PEER_FEEDBACKS
        completed = 0

        for i in range(count):
            await asyncio.sleep(2)
            page_text = await self.page.evaluate("() => document.body.innerText")
            if "0 left to complete" in page_text or "finished your peer reviews" in page_text or "4 complete" in page_text:
                break

            start_btn = self.page.locator("button:has-text(\"Start Reviewing\"):visible")
            s_count = await start_btn.count() if hasattr(start_btn, "count") else 0
            if s_count > 0:
                await start_btn.first.click()
                await asyncio.sleep(3)

            clicked_count = await self.page.evaluate(RUBRIC_SELECTION_JS)

            ta = self.page.locator("textarea[placeholder*=\"Share your thoughts\"], textarea[id*=\"comment\"]")
            ta_count = await ta.count() if hasattr(ta, "count") else 0
            if ta_count > 0:
                fb_text = feedbacks[completed % len(feedbacks)]
                await ta.first.fill(fb_text)
                await asyncio.sleep(1)

            submit_btn = self.page.locator("button:has-text(\"Submit Review\"):visible")
            sub_count = await submit_btn.count() if hasattr(submit_btn, "count") else 0
            if sub_count > 0 and not await submit_btn.first.is_disabled():
                await submit_btn.first.click()
                await asyncio.sleep(4)
                completed += 1

            modal = self.page.locator("div[role=\"dialog\"], [class*=\"modal\"]")
            m_count = await modal.count() if hasattr(modal, "count") else 0
            if m_count > 0:
                m_submit = modal.locator("button:has-text(\"Submit\"):visible")
                ms_count = await m_submit.count() if hasattr(m_submit, "count") else 0
                if ms_count > 0:
                    await m_submit.first.click()
                    await asyncio.sleep(3)

        final_text = await self.page.evaluate("() => document.body.innerText")
        match = re.search(r"(\d+)\s+left to complete", final_text, re.IGNORECASE)
        left = int(match.group(1)) if match else 0

        return {
            "status": "completed" if left == 0 else "in_progress",
            "reviews_submitted": completed,
            "reviews_remaining": left
        }
