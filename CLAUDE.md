# CLAUDE.md — Agent Guidelines & Immutable Laws for Agentic-Helper

## 🚀 Primary Objective
Autonomous LMS and Web Assessment Automation Engine for Coursera, Canvas, Moodle, Blackboard, and Google Forms.
Enforces zero human terminal setup, multi-tab parallel workers, and self-healing execution.

---

## ⚡ Immutable Agent Laws (NEVER VIOLATE)

### 0. ⚡ Mandatory Parallel Multi-Tab Mandate (Specialization vs Single Course)
- **NEVER solve sequentially one-by-one in a single tab!**
- **Specialization Course (`/specializations/<slug>`)**: Open **EACH child course in its own browser tab simultaneously** and complete all child courses in parallel concurrently in under 30 minutes!
- **Single Course (`/learn/<slug>`)**: Open **different module assignments in separate browser tabs simultaneously** (Week 1, Week 2, Week 3, Week 4 Quizzes) and solve all modules in parallel concurrently!
- **Universal Execution**: Call `quiz_pilot.tab_scheduler.smart_multiworker_sync(max_concurrency=4)` or MCP tool `smart_multiworker()`.

### 1. 🚫 Zero Scratch File Law
- **NEVER** write one-off Python scripts (e.g. `solve_hw1.py`, `quiz.py`, `check.py`, `dump.py`) to disk!
- The entire engine is pre-built in `quiz_pilot`. Execute all operations **in-memory** directly via Playwright CDP, `CourseraAdapter`, `FastAttemptManager`, or native MCP tools.
- The repository must remain completely pristine.

### 2. 🪟 Windows Browser Launch & URL Navigation
- Use `ensure_browser(url=course_url, port=9222)` or run `launch_browser_windows.bat "<URL>"`.
- **Auto-Navigation Guarantee**: Even if Chrome or Edge is already running on port 9222, `ensure_browser(url)` automatically opens and activates the target URL tab over CDP!
- Cross-platform: Automatically discovers Edge/Chrome on Windows, Linux, and macOS without `cmd.exe` quoting bugs.

### 3. 🧠 Mandatory `quiz_analysis.md` Failure Memory & Option Elimination Protocol
Whenever a quiz attempt fails or scores $< 100\%$, you **MUST** execute the following protocol:
1. **Create or Update `quiz_analysis.md` Immediately**:
   - For correct questions ($\ge 1/1$ pt): Lock in verified option text as `LOCKED_CORRECT`.
   - For wrong questions ($0/1$ pt): Mark submitted option as `ELIMINATED`.
   - Call `FastAttemptManager().record_attempt(quiz_id, attempt_num, questions, answers, feedback, score_pct)` or MCP tool `record_quiz_analysis`.
2. **On Quiz Retry**:
   - **Inspect `quiz_analysis.md` first** via `FastAttemptManager().get_retry_answers(questions, quiz_id)` or MCP tool `get_retry_answers`.
   - **Semantic Option Matching**: LMS platforms randomly shuffle option order between attempts. Always match options by **exact text string**, NOT old numeric indices!
   - **Zero Compute on Correct Answers**: Keep locked verified correct options.
   - **Zero Repetition on Failed Answers**: **NEVER SELECT A PREVIOUSLY FAILED OPTION AGAIN!** Eliminate all previously failed options and pick the next candidate from uneliminated options.
   - Only focus reasoning compute strictly on the questions that were wrong.
3. **Upon Reaching 100% Pass**:
   - Update `quiz_analysis.md` to status `🎉 PASSED (100%)`.

### 4. 📸 Isolated Screenshots & Cleanup
- All screenshots must strictly live in `.assessment_cache/screenshots/`.
- Once passed or course completes, clean internal cache and temp files via `FastAttemptManager().purge_all()`.

### 5. ⚡ Direct REST API Acceleration with Safe DOM Fallback
- Attempt Direct REST API solving first; poll grade feedback via `get_grade_feedback(submission_id)` and sync to `quiz_analysis.md`.
- If unsupported, returns HTTP 400, or fails, cleanly fall through to DOM execution without crashing.

### 6. 🌐 Unified Async & Multi-Tab WebSocket Connection Pool
- Tab finders (`await find_assessment_page`) and peer managers are fully asynchronous.
- Bridge server maintains connection pool (`active_websockets`); closing one tab does not drop remaining tabs.

### 7. 🚫 No-Guessing, 80% Gate, Single Attempt
- The agent completes every quiz itself - the human never does a quiz. Never fill blindly: no option 0, no first option, no "0" in a text box - a blind fill is a guess, not an answer. Memory and the local solvers answer what they can; any question they leave unknown is YOUR job: read it, work it out from the question content and your subject knowledge, and answer it in the same run. When a result says NEEDS_REVIEW_NOT_SUBMITTED, it lists the unknown questions with their text - call get_retry_answers, solve those questions yourself, and submit the merged full answer set. Aim for the MAXIMUM grade, ideally 100%: the percentage on the certificate converts directly into college marks (85% = 8.5/10), so never settle for merely passing - genuinely answer EVERY question. The 80% figure is only a safety floor, never a target: if genuinely answered questions are below 80%, finish solving them before spending the attempt. Attempts per quiz per run - the pass/fail rule: if the attempt PASSES, the quiz is DONE - never retake to improve a passing score (not even 85% on an unlimited-attempt quiz; the extra marks are not worth the extra tokens and time), and no attempts of any kind after a pass. If the attempt FAILS, keep re-attempting UNTIL IT PASSES, because a failed quiz means no certificate: after every fail, read the feedback, lock the verified-correct answers, never repeat an eliminated option, and solve the questions you got wrong before the next attempt. Attempts stop only when the quiz passes - or when Coursera itself locks further attempts, which must be reported honestly, never hidden.
- Fast atomic execution: finishes and submits in milliseconds (<50ms).

### 8. 🚫 Zero Websearch Rule
- NEVER websearch standard computer science, cloud computing, programming, or syllabus problems. Built-in solvers execute in-memory. Search strictly reserved for dynamic real-time news questions.

### 9. 🗣️ Always Speak Caveman
- Ultra-compressed communication. Drop filler, pleasantries, articles. Save ~65% tokens. Keep code, error strings, and technical terms exact.

### 10. 📝 Mandatory Peer-Graded Two-Step Protocol
- Step 1: Always submit your own assignment first on `/submit` (title, report PDF via Uppy, video URL, honor code checkbox, primary submit + modal dialog confirmation). Peer reviews are locked until your own project is submitted!
- Step 2: Only after submission is confirmed, navigate to `/give-feedback` / `/review-next` and grade 3-4 peers at MAX value: run the peer-review solver, whose one-shot rubric sweep selects the highest-points option for every criterion (never hand-click options one by one - slow). Add brief positive feedback!

---

## 🛠️ Quick Commands & APIs
- **Run Tests**: `.venv/bin/pytest tests`
- **CLI Multiworker**: `agentic-helper multiworker --concurrency 4`
- **Python Solver**:
  ```python
  from quiz_pilot.lms_adapters import get_lms_adapter
  from quiz_pilot.attempt_protector import FastAttemptManager
  from quiz_pilot.browser_launcher import ensure_browser

  ensure_browser(url=course_url, port=9222)
  # adapter.extract_questions() -> attempt_mgr.get_retry_answers() -> adapter.batch_fill_answers() -> attempt_mgr.record_attempt()
  ```

## Tab Ownership Rule (multi-tab / multi-course runs)
One worker = one tab. Act ONLY on your assigned tab (identified by its URL / tab_id). Never navigate, click, fill, or submit in another worker's tab, and never fall back to "the first tab". If your assigned tab is missing or shows a different course, STOP and report it - do not adopt another tab.

## Specialization Completion Rule
A specialization (e.g. "Course 2/7") is complete ONLY when every course in it is complete. Finishing one course NEVER ends the job: go to the specialization page, list the remaining incomplete courses, and continue with them. Never say "no more courses" based on a single course page - always verify on the specialization page, and report which courses remain if any cannot be completed.
