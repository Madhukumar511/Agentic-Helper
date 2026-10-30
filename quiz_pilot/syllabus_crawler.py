"""
Autonomous Course Syllabus Crawler & Assessment Pipeline Planner.
Automatically discovers every quiz, programming assignment, and peer review in a course,
extracting status, grade weights, and URLs to generate a zero-touch execution plan.
"""

import re
import time
from typing import List, Dict, Any, Optional

class SyllabusCrawler:
    """Crawls Coursera and LMS syllabi to extract complete assessment queues."""

    def __init__(self, page=None):
        self.page = page

    def set_page(self, page):
        self.page = page

    def crawl_course_assignments(self, course_slug_or_url: str) -> Dict[str, Any]:
        """
        Navigates to the course assignments table and extracts all items with status.
        """
        if not self.page:
            raise ValueError("No active browser page attached.")

        # Normalize URL to assignments view
        if "coursera.org" in course_slug_or_url:
            match = re.search(r"/learn/([^/?#]+)", course_slug_or_url)
            course_slug = match.group(1) if match else "course"
        else:
            course_slug = course_slug_or_url.strip("/ ")

        target_url = f"https://www.coursera.org/learn/{course_slug}/home/assignments"
        current_url = getattr(self.page, "url", "")

        if target_url not in current_url:
            self.page.evaluate("(u) => window.location.href = u", target_url)
            time.sleep(4)

        # Wait for assignments table to render
        try:
            self.page.wait_for_selector("table, div[role=\"table\"], [data-testid=\"grade-item\"], main", timeout=12000)
            time.sleep(1)
        except Exception:
            pass

        items = self.page.evaluate('''() => {
            const results = [];
            const rows = Array.from(document.querySelectorAll('tr, div[role="row"], div[data-testid*="assignment"]'));
            
            rows.forEach(r => {
                const text = r.innerText || '';
                const linkEl = r.querySelector('a[href*="/learn/"]');
                if (!linkEl && !text.includes("Quiz") && !text.includes("Assignment") && !text.includes("Submission") && !text.includes("Review")) {
                    return;
                }
                
                const titleEl = r.querySelector('h3, h4, strong, a') || r;
                const title = titleEl ? titleEl.innerText.split('\\n')[0].trim() : '';
                const href = linkEl ? linkEl.href : '';
                
                let itemType = 'quiz';
                if (/programming/i.test(text) || /programming/i.test(href)) {
                    itemType = 'programming';
                } else if (/peer/i.test(text) || /peer/i.test(href) || /feedback/i.test(href)) {
                    itemType = 'peer';
                } else if (/review/i.test(text)) {
                    itemType = 'peer_review';
                }
                
                let status = 'not_attempted';
                if (/passed/i.test(text) || /success/i.test(text) || /100%/i.test(text)) {
                    status = 'passed';
                } else if (/submitted/i.test(text)) {
                    status = 'submitted';
                }
                
                let weight = '';
                const weightMatch = text.match(/(\\d+)%/);
                if (weightMatch) {
                    weight = weightMatch[1] + '%';
                }

                if (title && (href || text.includes("%") || text.includes("Due"))) {
                    results.push({
                        title: title,
                        type: itemType,
                        status: status,
                        weight: weight,
                        url: href,
                        raw_text: text.replace(/\\s+/g, ' ').trim()
                    });
                }
            });
            return results;
        }''')

        # Deduplicate items by title
        deduped = []
        seen_titles = set()
        for it in items:
            t = it.get("title", "").strip()
            if t and t not in seen_titles:
                seen_titles.add(t)
                deduped.append(it)

        incomplete = [it for it in deduped if it["status"] not in ("passed", "submitted")]

        return {
            "course_slug": course_slug,
            "total_items": len(deduped),
            "completed_count": len(deduped) - len(incomplete),
            "pending_count": len(incomplete),
            "all_items": deduped,
            "execution_plan": incomplete
        }
