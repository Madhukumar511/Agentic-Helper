"""
Autonomous Course Syllabus Crawler & Assessment Pipeline Planner.
Automatically discovers every quiz, programming assignment, and peer review in a course,
extracting status, grade weights, and URLs to generate a zero-touch execution plan.
"""

import re
import asyncio
from typing import List, Dict, Any, Optional

class SyllabusCrawler:
    """Crawls Coursera and LMS syllabi to extract complete assessment queues."""

    def __init__(self, page=None):
        self.page = page

    def set_page(self, page):
        self.page = page

    async def _auto_enroll_if_needed(self) -> bool:
        """
        Detects if current page is an unenrolled course landing page,
        clicks Enroll / Go to course, confirms modal, and returns True if enrollment triggered.
        """
        if not self.page:
            return False

        try:
            enrolled = await self.page.evaluate('''() => {
                const btns = Array.from(document.querySelectorAll('button, a'));
                const isEnrollBtn = (b) => {
                    const t = (b.innerText || '').trim().toLowerCase();
                    return (
                        t.includes("enroll for free") ||
                        t === "enroll" ||
                        t.startsWith("enroll") ||
                        t.includes("go to course") ||
                        t === "resume course" ||
                        t.includes("start learning")
                    ) && b.offsetParent !== null;
                };

                const enrollBtn = btns.find(isEnrollBtn);
                if (!enrollBtn) return false;

                enrollBtn.click();
                return true;
            }''')

            if not enrolled:
                return False

            await asyncio.sleep(1.5)

            # Handle any confirmation modal dialog (Audit, Continue, Start, Go to course)
            await self.page.evaluate('''() => {
                const modal = document.querySelector('div[role="dialog"], .cds-Modal-container, .rc-EnrollmentModal');
                if (modal) {
                    const modalBtns = Array.from(modal.querySelectorAll('button, a'));
                    const confirmBtn = modalBtns.find(b => {
                        const t = (b.innerText || '').trim().toLowerCase();
                        return t.includes("continue") || t.includes("audit") || t.includes("start") || t.includes("go to course");
                    });
                    if (confirmBtn) confirmBtn.click();
                }
            }''')

            await asyncio.sleep(2.0)
            return True
        except Exception:
            return False

    async def crawl_course_assignments(self, course_slug_or_url: str) -> Dict[str, Any]:
        """
        Navigates to the course assignments table and extracts all items with status.
        Preserves organization/campus URLs (e.g. /organizations/<org>/learn/<slug>).
        """
        if not self.page:
            raise ValueError("No active browser page attached.")

        # Preserve organization prefix (e.g. /organizations/vvce)
        org_prefix = ""
        org_match = re.search(r"(/organizations/[^/?#]+)", course_slug_or_url)
        if org_match:
            org_prefix = org_match.group(1)
        elif self.page:
            cur_p_url = getattr(self.page, "url", "")
            cur_org_match = re.search(r"(/organizations/[^/?#]+)", cur_p_url)
            if cur_org_match:
                org_prefix = cur_org_match.group(1)

        # Normalize URL to assignments view
        if "coursera.org" in course_slug_or_url:
            match = re.search(r"/learn/([^/?#]+)", course_slug_or_url)
            course_slug = match.group(1) if match else "course"
        else:
            course_slug = course_slug_or_url.strip("/ ")

        target_url = f"https://www.coursera.org{org_prefix}/learn/{course_slug}/home/assignments"
        current_url = getattr(self.page, "url", "")

        # Avoid redundant reloads if page is already on assignments view for this course
        already_on_assignments = f"/learn/{course_slug}" in current_url and "/home/assignments" in current_url
        if not already_on_assignments:
            try:
                await self.page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                await self.page.evaluate("(u) => window.location.href = u", target_url)

        # Wait reactively for assignments table to render without blind sleeps
        try:
            await self.page.wait_for_selector("table, div[role='table'], div[role='row'], [data-testid='grade-item'], tr", timeout=8000)
        except Exception:
            await asyncio.sleep(1.5)

        extract_js = r'''() => {
            const results = [];
            const rows = Array.from(document.querySelectorAll('tr, div[role="row"], div[data-testid*="assignment"], div[data-testid="rc-ItemRow"]'));
            
            rows.forEach(r => {
                const text = r.innerText || '';
                const linkEl = r.querySelector('a[href]');
                const lowerText = text.toLowerCase();
                const isAssignmentRow = (
                    lowerText.includes("assignment") ||
                    lowerText.includes("quiz") ||
                    lowerText.includes("exam") ||
                    lowerText.includes("homework") ||
                    lowerText.includes("submission") ||
                    lowerText.includes("review") ||
                    lowerText.includes("graded") ||
                    lowerText.includes("plugin") ||
                    lowerText.includes("widget")
                );

                if (!linkEl && !isAssignmentRow) {
                    return;
                }
                
                const titleEl = r.querySelector('h3, h4, strong, a') || r;
                const title = titleEl ? titleEl.innerText.split('\\n')[0].trim() : '';
                const href = linkEl ? linkEl.href : '';
                
                let itemType = 'quiz';
                if (/programming/i.test(text) || /programming/i.test(href)) {
                    itemType = 'programming';
                } else if (/peer|assignment-submission|peer-assignment/i.test(text) || /peer|assignment-submission|peer-assignment/i.test(href)) {
                    itemType = 'peer';
                } else if (/review/i.test(text) || /review/i.test(href)) {
                    itemType = 'peer_review';
                } else if (/ungraded|plugin|widget/i.test(text) || /ungradedWidget/i.test(href)) {
                    itemType = 'ungraded';
                }
                
                let status = 'not_attempted';
                if (/passed/i.test(text) || /success/i.test(text) || /100%/i.test(text)) {
                    status = 'passed';
                } else if (itemType === 'peer' || itemType === 'peer_review') {
                    const selfSubmitted = /submitted/i.test(text);
                    const reviewsDone = (/4\/4|3\/3/i.test(text) || /reviewed/i.test(text)) && !/0\/4|1\/4|2\/4|0\/3|1\/3/i.test(text);
                    if (selfSubmitted && reviewsDone) {
                        status = 'submitted';
                    } else if (selfSubmitted && !reviewsDone) {
                        status = 'peer_reviews_pending';
                    } else {
                        status = 'not_attempted';
                    }
                } else if (/submitted/i.test(text) || /grading in progress/i.test(text)) {
                    status = 'submitted';
                } else if (/didn't pass|failed|error/i.test(text)) {
                    status = 'failed';
                }
                
                let weight = '';
                const weightMatch = text.match(/(\\d+)%/);
                if (weightMatch) {
                    weight = weightMatch[1] + '%';
                }

                if (title && (href || isAssignmentRow || text.includes("%") || text.includes("Due"))) {
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
        }'''

        items = await self.page.evaluate(extract_js)

        # Auto-enroll fallback if landing page intercepted assignments view
        if len(items) == 0:
            enrolled = await self._auto_enroll_if_needed()
            if enrolled:
                if "/home/assignments" not in getattr(self.page, "url", ""):
                    try:
                        await self.page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                    except Exception:
                        await self.page.evaluate("(u) => window.location.href = u", target_url)
                try:
                    await self.page.wait_for_selector("table, div[role='table'], div[role='row'], [data-testid='grade-item'], tr", timeout=8000)
                except Exception:
                    await asyncio.sleep(1.5)
                items = await self.page.evaluate(extract_js)

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
            "assignments": deduped,
            "execution_plan": incomplete
        }

    async def crawl_specialization_courses(self, spec_slug_or_url: str) -> List[Dict[str, str]]:
        """
        Crawls a Coursera Specialization page and extracts all child courses in sequence.
        Returns a list of dicts: [{"title": "Course Name", "slug": "course-slug", "url": "https://..."}]
        """
        if not self.page:
            raise ValueError("No active browser page attached.")

        # Preserve organization prefix (e.g. /organizations/vvce)
        org_prefix = ""
        org_match = re.search(r"(/organizations/[^/?#]+)", spec_slug_or_url)
        if org_match:
            org_prefix = org_match.group(1)
        elif self.page:
            cur_p_url = getattr(self.page, "url", "")
            cur_org_match = re.search(r"(/organizations/[^/?#]+)", cur_p_url)
            if cur_org_match:
                org_prefix = cur_org_match.group(1)

        if "coursera.org" in spec_slug_or_url:
            target_url = spec_slug_or_url
        else:
            clean_slug = spec_slug_or_url.strip("/ ")
            target_url = f"https://www.coursera.org{org_prefix}/specializations/{clean_slug}"

        current_url = getattr(self.page, "url", "")
        if target_url not in current_url:
            await self.page.evaluate("(u) => window.location.href = u", target_url)

        try:
            await self.page.wait_for_selector("a[href*=\"/learn/\"], h3", timeout=6000)
        except Exception:
            await asyncio.sleep(1.0)

        courses = await self.page.evaluate('''([defaultOrg]) => {
            const courseLinks = Array.from(document.querySelectorAll('a[href*="/learn/"]'));
            const results = [];
            const seen = new Set();
            
            courseLinks.forEach(a => {
                const match = a.href.match(/\\/learn\\/([a-zA-Z0-9_-]+)/);
                if (match) {
                    const slug = match[1];
                    const orgMatch = a.href.match(/(\\/organizations\\/[^/?#]+)/);
                    let prefix = orgMatch ? orgMatch[1] : (defaultOrg || "");
                    const cleanHref = "https://www.coursera.org" + prefix + "/learn/" + slug;
                    if (!seen.has(cleanHref) && !slug.includes("home") && !slug.includes("welcome")) {
                        seen.add(cleanHref);
                        const heading = a.querySelector('h3, h4, strong') || a;
                        const title = heading ? heading.innerText.trim().split('\\n')[0] : slug;
                        results.push({
                            title: title,
                            slug: slug,
                            url: cleanHref
                        });
                    }
                }
            });
            return results;
        }''', [org_prefix])
        return courses
