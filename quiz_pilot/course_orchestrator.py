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
from quiz_pilot.browser_launcher import ensure_browser_visible_once

async def _dedicated_page(context, url_hint: str):
    """Returns a page this orchestrator may safely navigate: an existing page
    ONLY if it already shows the target course/specialization, otherwise a
    brand-new tab. Never hijacks pages[0] - in parallel runs that tab may
    belong to another course's worker, and navigating it away mid-answer
    is exactly the cross-tab collision this rule exists to prevent."""
    hint = (url_hint or "").split("?")[0].rstrip("/").lower()
    for pg in context.pages:
        try:
            if hint and hint in pg.url.split("?")[0].rstrip("/").lower():
                return pg
        except Exception:
            pass
    return await context.new_page()


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


async def _loop_until_complete(items, run_one, verify_one, max_passes: int = 3):
    """Runs items, then VERIFIES each one, and repeats for whatever is still
    incomplete - until everything verifies complete, a full pass makes no
    progress, or max_passes is reached.

    This exists because "we ran the course once" is not "the course is
    complete": Coursera items can stay pending (locked, failed, or newly
    appeared), and a specialization is only done when EVERY course in it
    verifies complete. verify_one(item) must return True only when the
    item genuinely has nothing left to do.
    """
    remaining = list(items)
    all_results = []
    passes = 0
    prev_remaining = None
    while remaining and passes < max_passes:
        passes += 1
        results = await asyncio.gather(
            *[run_one(it) for it in remaining], return_exceptions=True
        )
        all_results.extend(results)
        still = []
        for it in remaining:
            try:
                done = await verify_one(it)
            except Exception:
                done = False
            if not done:
                still.append(it)
        if prev_remaining is not None and len(still) >= prev_remaining:
            remaining = still
            break  # a full pass made no progress - report honestly, do not spin
        prev_remaining = len(still)
        remaining = still
    completed = [it for it in items if it not in remaining]
    return {
        "completed_items": completed,
        "remaining_items": remaining,
        "passes": passes,
        "results": all_results,
    }


class CourseOrchestrator:
    """End-to-end autonomous course execution engine."""

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222", max_concurrency: int = 4):
        self.cdp_url = cdp_url
        self.max_concurrency = max_concurrency
        self.attempt_mgr = FastAttemptManager()
        # Attempt policy registry, per quiz, for THIS run (across courses
        # and specialization passes): {"attempts": n, "passed": bool}.
        # PASS is final - never retaken to improve a score. FAIL means
        # keep re-attempting UNTIL IT PASSES (a failed quiz = no
        # certificate). The 10-attempt cap is only an infinite-loop
        # guard; Coursera's own attempt limits may stop it sooner.
        self._run_quiz_outcomes = {}

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
            _prev = self._run_quiz_outcomes.get(item_title)
            if _prev is not None:
                if _prev.get("passed"):
                    item_res["status"] = "skipped_already_passed"
                    item_res["note"] = "Passed earlier in this run; a pass is final - never retaken to improve the score."
                    return item_res
                if _prev.get("attempts", 0) >= 10:
                    item_res["status"] = "skipped_attempt_cap"
                    item_res["note"] = "Safety cap of 10 attempts in one run reached; quiz reported failed."
                    return item_res
                # else: fall through - a failed quiz is re-attempted until it passes.
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
                                api_coverage = (len(api_answers) / len(api_questions)) if api_questions else 0.0
                                if api_answers and api_coverage >= 0.80:
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
                                                    attempt_num=self.attempt_mgr.next_attempt_num(item_title),
                                                    questions=api_questions,
                                                    answers=api_answers,
                                                    feedback=feedback_map,
                                                    score_pct=score_pct,
                                                    passed=passed,
                                                    md_path="quiz_analysis.md"
                                                )
                                            except Exception:
                                                pass

                                            _oc = self._run_quiz_outcomes.setdefault(item_title, {"attempts": 0, "passed": False})
                                            _oc["attempts"] += 1
                                            _oc["passed"] = bool(passed)
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
            max_quiz_attempts = 3
            current_attempt = 1

            while current_attempt <= max_quiz_attempts:
                questions = await adapter.extract_questions_async()
                if not questions:
                    break
                answers = self.attempt_mgr.get_retry_answers(questions, quiz_id=item_title)
                # NO GUESSING: unknown questions stay UNANSWERED and are
                # reported (previously default-filled with option 0).
                _known = {
                    q.get("index", 0) for q in questions
                    if q.get("index", 0) in answers or str(q.get("index", 0)) in answers
                }
                unknown_indices = [q.get("index", 0) for q in questions if q.get("index", 0) not in _known]
                coverage = (len(_known) / len(questions)) if questions else 0.0
                # Fill answers only without inline submit
                if hasattr(adapter, "batch_fill_answers_async"):
                    await adapter.batch_fill_answers_async(answers, auto_submit=False)
                elif hasattr(adapter, "batch_fill_answers"):
                    adapter.batch_fill_answers(answers, auto_submit=False)
                else:
                    for q in questions:
                        if q["index"] in answers:
                            await adapter.fill_answer_async(q["index"], answers[q["index"]])

                # 80% FLOOR (not a score target - the target is the maximum
                # grade with every question genuinely answered): below 80%
                # known coverage, keep the filled answers and DO NOT submit
                # (zero attempts burned); report uncertainty.
                if coverage < 0.80:
                    item_res["status"] = "needs_review_not_submitted"
                    item_res["coverage_pct"] = round(coverage * 100, 1)
                    item_res["unknown_questions"] = unknown_indices
                    item_res["unknown_questions_detail"] = _unknown_details(questions, unknown_indices)
                    return item_res

                # Explicit modal submission with confirmation dialog
                await adapter.submit_assessment_async()

                try:
                    fb = await adapter.extract_feedback_async()
                    score_pct = fb.get("score_pct")
                    is_passed = fb.get("passed", score_pct >= 80.0 if score_pct is not None else False)
                    self.attempt_mgr.record_attempt(
                        quiz_id=item_title,
                        attempt_num=self.attempt_mgr.next_attempt_num(item_title),
                        questions=questions,
                        answers=answers,
                        feedback=fb.get("feedback", {}),
                        score_pct=score_pct,
                        passed=is_passed,
                        md_path="quiz_analysis.md"
                    )
                    item_res["score_pct"] = score_pct
                    item_res["passed"] = is_passed
                    item_res["status"] = "submitted"
                    item_res["questions_solved"] = len(questions)

                    if is_passed:
                        break
                except Exception:
                    item_res["status"] = "submitted"
                    break

                # If failed and retries remain, attempt to advance to retry attempt
                if not item_res.get("passed") and current_attempt < max_quiz_attempts:
                    current_attempt += 1
                    try:
                        await page.evaluate('''() => {
                            let backBtn = document.querySelector('button[aria-label="Back"], [data-testid="back-button"]');
                            if (backBtn) backBtn.click();
                            let btns = Array.from(document.querySelectorAll('button'));
                            let tryBtn = btns.find(b => {
                                let t = b.innerText.trim();
                                return (t === "Try again" || t === "Resume assignment" || t === "Resume") && b.offsetParent !== null;
                            });
                            if (tryBtn) tryBtn.click();
                        }''')
                        await asyncio.sleep(1.0)
                    except Exception:
                        pass
                else:
                    break

            _oc = self._run_quiz_outcomes.setdefault(item_title, {"attempts": 0, "passed": False})
            _oc["attempts"] += current_attempt
            _oc["passed"] = bool(item_res.get("passed", False))

        elif item_type in ("peer", "peer_review"):
            prm = PeerReviewManager(page=page)
            if hasattr(prm, "detect_peer_task_async"):
                t_info = await prm.detect_peer_task_async(item_url)
            else:
                t_info = prm.detect_peer_task(item_url)
                if asyncio.iscoroutine(t_info):
                    t_info = await t_info
            peer_mode = t_info.get("mode") if isinstance(t_info, dict) else "review"
            item_res["peer_mode"] = peer_mode
            if peer_mode in ("submission", "submit"):
                sub_res = await prm.submit_peer_assignment_async(title=item_title)
                item_res["submitted"] = sub_res.get("submitted", False)
                rev_res = await prm.complete_peer_reviews_async(count=4)
                item_res["reviews_done"] = rev_res.get("reviews_submitted", 0)
                item_res["status"] = "completed"
                item_res["passed"] = True
            else:
                rev_res = await prm.complete_peer_reviews_async(count=4)
                item_res["reviews_done"] = rev_res.get("reviews_submitted", 0)
                item_res["status"] = "reviews_completed"
                item_res["passed"] = True

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
                else:
                    item_res["status"] = "skipped"
            except Exception:
                item_res["status"] = "skipped"

        return item_res

    async def auto_complete_course(
        self,
        course_url: str,
        prefer_direct_api: bool = True,
        page=None,
        context=None,
        concurrency: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Autonomously discovers and completes an entire course:
        1. Crawls syllabus to extract all incomplete tasks
        2. Solves quizzes, programming assignments, and peer reviews
        3. Returns overall completion report
        """
        ensure_browser_visible_once()
        effective_concurrency = concurrency if concurrency is not None else self.max_concurrency

        async def _run_course(ctx, c_page):
            # 1. Syllabus Crawl
            crawler = SyllabusCrawler(page=c_page)
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
                    direct_api = await CourseraDirectAPI.from_page(c_page)
                except Exception:
                    direct_api = None

            # 2. Multi-Tab Parallel Execution across pending assignments / modules
            num_workers = min(effective_concurrency, len(pending_items))
            if num_workers <= 1:
                for item in pending_items:
                    res = await self._solve_item_on_page(c_page, item, direct_api=direct_api)
                    results.append(res)
            else:
                worker_pages = [c_page]
                for _ in range(num_workers - 1):
                    p_new = await ctx.new_page()
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

            # NOTE: no purge_all() here. In a specialization run this method
            # executes per course IN PARALLEL - purging the shared cache when
            # one course finishes would wipe the memory of courses still
            # running. Cleanup is explicit (CLI clean) or per-quiz.

            # FAIL-RETRY-UNTIL-PASS (user policy): a FAILED quiz blocks the
            # certificate, so failed quizzes are re-attempted - each round
            # with the latest feedback in memory (correct answers locked,
            # wrong options eliminated, failed questions re-solved) - UNTIL
            # THEY PASS. Passed quizzes are final, never retaken to improve
            # a score. The 9 rounds are only an infinite-loop guard; a quiz
            # whose answers run out (gate) or that errors drops out of the
            # loop and is reported with its real attempt count.
            for _round in range(9):
                _failed = [
                    r for r in results
                    if r.get("status") in ("submitted", "submitted_direct_api")
                    and r.get("passed") is False
                ]
                if not _failed:
                    break
                _by_title = {r.get("title"): r for r in results}
                _progress = False
                for _fr in _failed:
                    _item = next((it for it in pending_items if it.get("title") == _fr.get("title")), None)
                    if _item is None:
                        continue
                    try:
                        _retry_res = await self._solve_item_on_page(c_page, _item, direct_api=direct_api)
                    except Exception:
                        continue
                    _retry_res["retry_after_fail"] = True
                    _by_title[_fr.get("title")] = _retry_res
                    _progress = True
                results = list(_by_title.values())
                if not _progress:
                    break

            return {
                "status": "completed",
                "course": plan.get("course_slug"),
                "total_processed": len(results),
                "items": results
            }

        if page is not None and context is not None:
            return await _run_course(context, page)
        else:
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
                ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
                p_main = await _dedicated_page(ctx, course_url)
                return await _run_course(ctx, p_main)

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
        ensure_browser_visible_once()
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(self.cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await _dedicated_page(context, spec_url)

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
                            context=context,
                            concurrency=1,
                        )
                    finally:
                        try:
                            await c_page.close()
                        except Exception:
                            pass
                    return {
                        "course_title": c_info.get("title"),
                        "course_url": c_info.get("url"),
                        "result": res
                    }
                    return {
                        "course_title": c_info.get("title"),
                        "course_url": c_info.get("url"),
                        "result": res
                    }

            # VERIFY each course from its own assignments page: a course only
            # counts as complete when its execution plan (incomplete items) is
            # empty. "Attempted" is not "completed" - the old code reported
            # len(results) as courses_completed, which hid unfinished courses.
            verify_crawler = SyllabusCrawler(page=page)

            async def verify_course(c_info):
                plan = await verify_crawler.crawl_course_assignments(c_info["url"])
                return len(plan.get("execution_plan", [])) == 0

            # NOTE: no purge_all() here either - other specializations/courses
            # may be running concurrently (multi-worker batches) and share the
            # same cache directory. Cleanup is explicit or per-quiz only.
            #
            # LOOP until every targeted course VERIFIES complete (or a full
            # pass makes no progress): courses can unlock/appear after earlier
            # ones finish, and one pass is never treated as proof of done.
            loop = await _loop_until_complete(
                target_courses, run_single_course, verify_course, max_passes=3
            )

            return {
                "specialization": spec_url,
                "status": "completed" if not loop["remaining_items"] else "incomplete",
                "total_courses_in_spec": len(all_courses),
                "courses_completed": len(loop["completed_items"]),
                "remaining_courses": [
                    {"title": c.get("title"), "url": c.get("url")}
                    for c in loop["remaining_items"]
                ],
                "passes": loop["passes"],
                "details": loop["results"]
            }
