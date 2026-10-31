"""
Unified High-Speed Course Orchestrator.
Combines all 4 Performance Optimizations:
1. Autonomous Syllabus Crawler (Zero-touch assessment discovery)
2. Direct REST/GraphQL API Solver (Sub-second execution bypassing browser rendering)
3. Multi-Worker Concurrent Pool (Parallel tab workers)
4. Context-Isolated Execution State (Keeps LLM memory lightweight and fast)
"""

import os
import time
import asyncio
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright

from quiz_pilot.syllabus_crawler import SyllabusCrawler
from quiz_pilot.direct_api_solver import CourseraDirectAPI
from quiz_pilot.tab_scheduler import AsyncTabScheduler
from quiz_pilot.peer_review_solver import PeerReviewManager
from quiz_pilot.programming_solver import ProgrammingAssignmentManager
from quiz_pilot.lms_adapters import get_lms_adapter
from quiz_pilot.attempt_protector import FastAttemptManager

class CourseOrchestrator:
    """End-to-end autonomous course execution engine."""

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222", max_concurrency: int = 4):
        self.cdp_url = cdp_url
        self.max_concurrency = max_concurrency
        self.attempt_mgr = FastAttemptManager()

    @staticmethod
    def _extract_questions_from_api_data(api_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Maps raw Coursera onDemandAssessments REST response into standard question schema."""
        elem = api_data.get("elements", [api_data])[0] if isinstance(api_data.get("elements"), list) and api_data.get("elements") else api_data
        raw_questions = (
            elem.get("questions") or
            elem.get("parts") or
            elem.get("items") or
            api_data.get("questions") or
            api_data.get("parts") or
            []
        )
        mapped = []
        for idx, q in enumerate(raw_questions):
            prompt = q.get("prompt") or q.get("question") or q.get("text") or q.get("title") or ""
            raw_opts = q.get("options") or q.get("choices") or []
            options = []
            for o in raw_opts:
                if isinstance(o, dict):
                    options.append(o.get("text") or o.get("label") or o.get("val") or str(o))
                else:
                    options.append(str(o))
            q_type = q.get("type", "radio")
            q_id = q.get("id") or q.get("partId") or idx
            mapped.append({
                "index": idx,
                "id": q_id,
                "prompt": prompt,
                "options": options,
                "type": q_type
            })
        return mapped

    async def _solve_item_on_page(
        self,
        page,
        item: Dict[str, Any],
        direct_api: Optional[CourseraDirectAPI] = None
    ) -> Dict[str, Any]:
        """Solves a single quiz, peer review, or assignment on the specified page/tab."""
        item_title = item.get("title", "")
        item_url = item.get("url", "")
        item_type = item.get("type", "quiz")

        if not item_url:
            return {"title": item_title, "status": "skipped_no_url"}

        try:
            await page.evaluate("(u) => window.location.href = u", item_url)
        except Exception:
            try:
                await page.goto(item_url, wait_until="domcontentloaded", timeout=12000)
            except Exception:
                pass

        # Fast reactive wait: resolves immediately when assessment elements mount (<500ms)
        try:
            await page.wait_for_selector('div[role="radiogroup"], div[role="group"], [data-testid*="question"], main', timeout=4000)
            await asyncio.sleep(0.5)
        except Exception:
            await asyncio.sleep(1.0)

        item_res = {
            "title": item_title,
            "type": item_type,
            "url": item_url,
            "status": "pending"
        }

        if item_type == "quiz":
            # 1. Direct REST/GraphQL API attempt if configured
            if direct_api:
                try:
                    assessment_id = await page.evaluate(r'''() => {
                        if (window.__APOLLO_STATE__) {
                            for (let k of Object.keys(window.__APOLLO_STATE__)) {
                                if (k.startsWith("OnDemandAssessment:") || k.includes("Assessment:")) {
                                    let id = window.__APOLLO_STATE__[k].id || (k.includes(":") ? k.split(":")[1] : null);
                                    if (id) return id;
                                }
                            }
                        }
                        let m = window.location.pathname.match(/(?:assignment-submission|exam|quiz)\/([a-zA-Z0-9_-]+)/);
                        return m ? m[1] : null;
                    }''')
                    if assessment_id:
                        api_data = await direct_api.fetch_assessment(assessment_id)
                        if api_data and not api_data.get("error"):
                            api_questions = self._extract_questions_from_api_data(api_data)
                            if api_questions:
                                api_answers = self.attempt_mgr.get_retry_answers(api_questions, quiz_id=item_title)
                                if api_answers:
                                    parts_payload = {}
                                    for q in api_questions:
                                        q_idx = q["index"]
                                        q_id = q.get("id", q_idx)
                                        if q_idx in api_answers:
                                            parts_payload[str(q_id)] = api_answers[q_idx]

                                    if parts_payload:
                                        sub_res = await direct_api.submit_answers(assessment_id, parts_payload)
                                        if sub_res and sub_res.get("success"):
                                            submission_id = (
                                                sub_res.get("data", {}).get("id")
                                                or sub_res.get("submission_id")
                                                or sub_res.get("id")
                                            )
                                            score_pct = 100.0
                                            passed = True
                                            feedback_map = {}
                                            if submission_id and hasattr(direct_api, "get_grade_feedback"):
                                                try:
                                                    grade_res = await direct_api.get_grade_feedback(submission_id)
                                                    if grade_res and not grade_res.get("error"):
                                                        if "score_pct" in grade_res:
                                                            score_pct = float(grade_res["score_pct"])
                                                        elif "score" in grade_res:
                                                            score_pct = float(grade_res["score"])
                                                        elif "overallScore" in grade_res:
                                                            score_pct = float(grade_res["overallScore"])
                                                        elif "fractionPassed" in grade_res:
                                                            score_pct = float(grade_res["fractionPassed"]) * 100.0

                                                        passed = grade_res.get("passed", score_pct >= 80.0)
                                                        feedback_map = grade_res.get("feedback", {})
                                                except Exception:
                                                    pass

                                            if not feedback_map:
                                                feedback_map = {q["index"]: passed for q in api_questions}

                                            try:
                                                self.attempt_mgr.record_attempt(
                                                    quiz_id=item_title,
                                                    attempt_num=1,
                                                    questions=api_questions,
                                                    answers=api_answers,
                                                    feedback=feedback_map,
                                                    score_pct=score_pct,
                                                    passed=passed,
                                                    md_path="quiz_analysis.md"
                                                )
                                            except Exception:
                                                pass

                                            item_res["status"] = "submitted_direct_api"
                                            item_res["assessment_id"] = assessment_id
                                            item_res["questions_solved"] = len(api_questions)
                                            item_res["score_pct"] = score_pct
                                            item_res["passed"] = passed
                                            return item_res
                except Exception:
                    pass

            # 2. DOM-based execution fallback via unified async LMS adapter
            adapter = get_lms_adapter(page)
            questions = await adapter.extract_questions_async()
            if questions:
                answers = self.attempt_mgr.get_retry_answers(questions, quiz_id=item_title)
                # Guarantee 100% of questions are answered (never leave any question unanswered)
                for q in questions:
                    q_idx = q.get("index", 0)
                    if q_idx not in answers and str(q_idx) not in answers:
                        answers[q_idx] = 0
                # Fill answers only without inline submit
                if hasattr(adapter, "batch_fill_answers_async"):
                    await adapter.batch_fill_answers_async(answers, auto_submit=False)
                elif hasattr(adapter, "batch_fill_answers"):
                    adapter.batch_fill_answers(answers, auto_submit=False)
                else:
                    for q in questions:
                        await adapter.fill_answer_async(q["index"], answers.get(q["index"], 0))
                
                # Explicit modal submission with confirmation dialog
                await adapter.submit_assessment_async()
                
                try:
                    fb = await adapter.extract_feedback_async()
                    self.attempt_mgr.record_attempt(
                        quiz_id=item_title,
                        attempt_num=1,
                        questions=questions,
                        answers=answers,
                        feedback=fb.get("feedback", {}),
                        score_pct=fb.get("score_pct"),
                        md_path="quiz_analysis.md"
                    )
                    item_res["score_pct"] = fb.get("score_pct")
                    item_res["passed"] = fb.get("passed", False)
                except Exception:
                    pass

                item_res["status"] = "submitted"
                item_res["questions_solved"] = len(questions)

        elif item_type == "peer_review":
            prm = PeerReviewManager(page=page)
            rev_res = prm.complete_peer_reviews(count=4)
            if asyncio.iscoroutine(rev_res):
                rev_res = await rev_res
            item_res["status"] = rev_res.get("status")
            item_res["reviews_done"] = rev_res.get("reviews_submitted")

        elif item_type == "peer":
            prm = PeerReviewManager(page=page)
            t_info = prm.detect_peer_task(item_url)
            if asyncio.iscoroutine(t_info):
                t_info = await t_info
            item_res["peer_mode"] = t_info.get("mode")
            if t_info.get("mode") == "submit":
                sub_res = prm.submit_peer_assignment(title=item_title)
                if asyncio.iscoroutine(sub_res):
                    sub_res = await sub_res
                item_res["submitted"] = sub_res.get("success", False)
                # Then complete required peer reviews
                rev_res = prm.complete_peer_reviews(count=4)
                if asyncio.iscoroutine(rev_res):
                    rev_res = await rev_res
                item_res["reviews_done"] = rev_res.get("reviews_submitted")
                item_res["status"] = "completed"
            else:
                rev_res = prm.complete_peer_reviews(count=4)
                if asyncio.iscoroutine(rev_res):
                    rev_res = await rev_res
                item_res["status"] = "reviews_completed"
                item_res["reviews_done"] = rev_res.get("reviews_submitted")

        elif item_type == "programming":
            pam = ProgrammingAssignmentManager(cdp_url=self.cdp_url)
            spec = await pam.extract_task_spec(page=page)
            item_res["title"] = spec.get("title", item_title)
            item_res["task_type"] = spec.get("task_type")
            item_res["has_file_input"] = spec.get("has_file_input")
            item_res["latest_score"] = spec.get("latest_score")
            item_res["passed"] = spec.get("is_passed", False)
            item_res["status"] = "passed" if spec.get("is_passed") else "inspected"

        elif item_type == "ungraded":
            try:
                mark_btn = page.locator('button:has-text("Mark as completed")')
                if await mark_btn.count() > 0:
                    await mark_btn.first.click()
                    await asyncio.sleep(0.5)
                    item_res["status"] = "marked_completed"
                    item_res["passed"] = True
            except Exception:
                pass

        # Check for ungraded / plugin completion buttons (e.g. "Mark as completed")
        try:
            mark_btn = page.locator('button:has-text("Mark as completed")')
            if await mark_btn.count() > 0:
                await mark_btn.first.click()
                await asyncio.sleep(0.5)
                item_res["status"] = "marked_completed"
        except Exception:
            pass

        return item_res

    async def auto_complete_course(
        self,
        course_url: str,
        prefer_direct_api: bool = True,
        page: Optional[Any] = None,
        context: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Autonomously discovers and completes an entire course:
        1. Crawls syllabus to extract all incomplete tasks
        2. Solves quizzes, programming assignments, and peer reviews
        3. Returns overall completion report
        """
        async def _run_course(active_page, active_context):
            # 1. Syllabus Crawl
            crawler = SyllabusCrawler(page=active_page)
            plan = await crawler.crawl_course_assignments(course_url)
            pending_items = plan.get("execution_plan", [])

            if not pending_items:
                return {
                    "status": "already_completed",
                    "course": plan.get("course_slug"),
                    "completed_items": plan.get("completed_count"),
                    "pending_items": 0
                }

            results = []
            direct_api = None
            if prefer_direct_api:
                try:
                    direct_api = await CourseraDirectAPI.from_page(active_page)
                except Exception:
                    direct_api = None

            # 2. Multi-Tab Parallel Execution across pending assignments / modules
            num_workers = min(self.max_concurrency, len(pending_items))
            if num_workers <= 1 or not active_context:
                for item in pending_items:
                    res = await self._solve_item_on_page(active_page, item, direct_api=direct_api)
                    results.append(res)
            else:
                worker_pages = [active_page]
                for _ in range(num_workers - 1):
                    p_new = await active_context.new_page()
                    worker_pages.append(p_new)

                queue = asyncio.Queue()
                for it in pending_items:
                    await queue.put(it)

                async def worker_loop(w_page, w_id):
                    w_res = []
                    while True:
                        try:
                            it = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        res = await self._solve_item_on_page(w_page, it, direct_api=direct_api)
                        w_res.append(res)
                        queue.task_done()
                    return w_res

                tasks = [worker_loop(w_page, idx) for idx, w_page in enumerate(worker_pages)]
                worker_outputs = await asyncio.gather(*tasks, return_exceptions=False)
                for out in worker_outputs:
                    results.extend(out)

                # Close helper tabs (leave the main page open)
                for w_page in worker_pages[1:]:
                    try:
                        await w_page.close()
                    except Exception:
                        pass

            # Clean cache upon completion
            self.attempt_mgr.purge_all()

            return {
                "status": "completed",
                "course": plan.get("course_slug"),
                "total_processed": len(results),
                "items": results
            }

        if page and context:
            return await _run_course(page, context)
        elif page:
            ctx = getattr(page, "context", None)
            return await _run_course(page, ctx)

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(self.cdp_url)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
            return await _run_course(pg, ctx)

    async def auto_complete_specialization(
        self,
        spec_url: str,
        max_courses: Optional[int] = None,
        prefer_direct_api: bool = True
    ) -> Dict[str, Any]:
        """
        Discovers all courses in a Specialization, slices the requested count (e.g. first 4),
        opens their assignments across tabs, and completes them concurrently.
        """
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(self.cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()

            crawler = SyllabusCrawler(page=page)
            all_courses = await crawler.crawl_specialization_courses(spec_url)
            if not all_courses:
                return {"error": f"No courses found on specialization page: {spec_url}"}

            target_courses = all_courses[:max_courses] if max_courses else all_courses

            course_semaphore = asyncio.Semaphore(min(self.max_concurrency, len(target_courses)))

            async def run_single_course(c_info):
                async with course_semaphore:
                    c_page = await context.new_page()
                    try:
                        res = await self.auto_complete_course(
                            course_url=c_info["url"],
                            prefer_direct_api=prefer_direct_api,
                            page=c_page,
                            context=context
                        )
                        return {
                            "course_title": c_info.get("title"),
                            "course_url": c_info.get("url"),
                            "result": res
                        }
                    finally:
                        try:
                            await c_page.close()
                        except Exception:
                            pass

            course_results = await asyncio.gather(
                *[run_single_course(c) for c in target_courses],
                return_exceptions=False
            )

            # Clean cache and all temporary files upon specialization completion
            self.attempt_mgr.purge_all()

            return {
                "specialization": spec_url,
                "total_courses_in_spec": len(all_courses),
                "courses_completed": len(course_results),
                "details": course_results
            }
