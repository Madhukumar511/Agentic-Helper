"""
CDP Client for Quiz-Pilot.
Attaches to live running Brave or Chromium instance via Chrome DevTools Protocol.
"""

import time
import logging
from typing import List, Dict, Any, Optional
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
from quiz_pilot.dom_detector import (
    DETECTION_SCRIPT,
    SELECT_OPTION_SCRIPT,
    NAVIGATE_NEXT_SCRIPT,
    IS_SUBMIT_SCREEN_SCRIPT
)

logger = logging.getLogger("quiz_pilot.cdp_client")


class CDPQuizClient:
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    def connect(self) -> bool:
        """Connects over CDP to the running browser."""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
            logger.info(f"Connected to CDP at {self.cdp_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to CDP at {self.cdp_url}: {e}")
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
            return False

    def list_tabs(self) -> List[Dict[str, Any]]:
        """Returns list of open pages with index, title, and url."""
        if not self.browser:
            return []

        tabs = []
        tab_idx = 0
        for ctx in self.browser.contexts:
            for p in ctx.pages:
                try:
                    title = p.title()
                    url = p.url
                    tabs.append({
                        "index": tab_idx,
                        "title": title,
                        "url": url,
                        "page_obj": p
                    })
                    tab_idx += 1
                except Exception as e:
                    logger.debug(f"Error reading page {tab_idx}: {e}")
        return tabs

    def select_tab(self, index_or_keyword: Any = None) -> Optional[Page]:
        """
        Selects target page. If index_or_keyword is None, automatically
        picks the best candidate matching LMS keywords.
        """
        tabs = self.list_tabs()
        if not tabs:
            logger.warning("No open tabs found in the browser.")
            return None

        # 1. Match by integer index
        if isinstance(index_or_keyword, int) and 0 <= index_or_keyword < len(tabs):
            self.page = tabs[index_or_keyword]["page_obj"]
            return self.page

        # 2. Match by string keyword in URL or Title
        if isinstance(index_or_keyword, str) and index_or_keyword:
            kw = index_or_keyword.lower()
            for t in tabs:
                if kw in t["title"].lower() or kw in t["url"].lower():
                    self.page = t["page_obj"]
                    return self.page

        # 3. Auto-detect LMS tabs
        lms_keywords = ["canvas", "moodle", "blackboard", "coursera", "quiz", "exam", "assessment", "forms"]
        for kw in lms_keywords:
            for t in tabs:
                if kw in t["url"].lower() or kw in t["title"].lower():
                    logger.info(f"Auto-selected tab [{t['index']}]: '{t['title']}' ({t['url']})")
                    self.page = t["page_obj"]
                    return self.page

        # Fallback to the first available tab
        self.page = tabs[0]["page_obj"]
        logger.info(f"Selected default tab [0]: '{tabs[0]['title']}'")
        return self.page

    def scan_questions(self) -> List[Dict[str, Any]]:
        """Scans the active page for questions and choices."""
        if not self.page:
            raise RuntimeError("No active tab selected.")

        try:
            # Inject and run detector script
            questions = self.page.evaluate(DETECTION_SCRIPT)
            return questions or []
        except Exception as e:
            logger.error(f"Error scanning questions: {e}")
            return []

    def click_option(self, q_idx: int, opt_idx: int) -> bool:
        """Clicks an option safely with verification."""
        if not self.page:
            return False

        try:
            res = self.page.evaluate(f"({SELECT_OPTION_SCRIPT})({q_idx}, {opt_idx})")
            if res.get("success"):
                logger.debug(f"Successfully selected question {q_idx}, option {opt_idx}")
                return True
            else:
                logger.warning(f"Failed to select: {res.get('error')}")
                return False
        except Exception as e:
            logger.error(f"Exception during option click: {e}")
            return False

    def click_next(self) -> Dict[str, Any]:
        """Clicks the Next Question or Next Page button."""
        if not self.page:
            return {"success": False, "error": "No page"}

        try:
            res = self.page.evaluate(NAVIGATE_NEXT_SCRIPT)
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_submit_screen(self) -> Dict[str, Any]:
        """Checks if page reached final submit exam state."""
        if not self.page:
            return {"isSubmit": False}

        try:
            return self.page.evaluate(IS_SUBMIT_SCREEN_SCRIPT)
        except Exception as e:
            return {"isSubmit": False, "error": str(e)}

    def wait_for_dom_settle(self, timeout_sec: float = 2.0):
        """Waits for page navigation or dynamic content update."""
        time.sleep(timeout_sec)

    def close(self):
        """Cleanly releases CDP connection without closing user's browser."""
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
