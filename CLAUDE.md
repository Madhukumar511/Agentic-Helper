# CLAUDE.md — Agent Guidelines & Immutable Laws for Agentic-Helper

## 🚀 Primary Objective
Autonomous LMS and Web Assessment Automation Engine for Coursera, Canvas, Moodle, Blackboard, and Google Forms.
Enforces zero human terminal setup, multi-tab parallel workers, and self-healing execution.

---

## ⚡ Immutable Agent Laws (NEVER VIOLATE)

### 1. 🚫 Pure In-Memory Engine Law (ZERO Scratch or Temp Files)
- Strictly prohibited to create one-off scripts (`solve_*.py`, `quiz.py`, `check.py`, `dump.py`), unpack zips into `/tmp`, or compile manually via shell.
- All operations must execute **in-memory** directly via Playwright CDP, `CourseraAdapter`, `ProgrammingAssignmentManager`, `PeerReviewManager`, or `FastAttemptManager`.

### 2. 🚫 ZERO External Git Cloning Law (No Third-Party Repos)
- Strictly prohibited to execute `git clone` to pull third-party student repositories from GitHub for course assignments.
- Implement assignment code cleanly in-memory or using standard patterns directly.

### 3. 🚀 Mandatory Parallel Multi-Tab Workers (Specialization vs Single Course)
- **NEVER solve sequentially one-by-one in a single tab!**
- **Specialization (`/specializations/<slug>`)**: Open EACH child course in its own browser tab simultaneously and complete all child courses concurrently in parallel in under 30 minutes!
- **Single Course (`/learn/<slug>`)**: Crawl syllabus, open incomplete module assignments across separate browser tabs simultaneously (Week 1, Week 2, Week 3, Week 4 Quizzes), and complete all modules concurrently in parallel!
- Universal execution: `quiz_pilot.tab_scheduler.smart_multiworker_sync(max_concurrency=4)` or MCP tool `smart_multiworker()`.

### 4. 🗂️ Multi-Tab & Specialization Tab Isolation (Zero Tab Collisions)
- Never share or collide on Tab 0 (`context.pages[0]`).
- When running a Specialization, each child course must run in its own dedicated, isolated tab (`await context.new_page()`) so syllabus crawls and submissions never collide or abort each other.
- Automatically close helper tabs when the course finishes.

### 5. 🏆 Mandatory 100% Comprehensive Assignment Completion Law (Zero Left Behind)
- **NON-BYPASSABLE MANDATE**: Complete every single item labeled or categorized as an assignment:
  1. **Graded Assignments (Quizzes, Exams, Homework)**: Scraped, solved, submitted, and checked. If failed, recorded in `quiz_analysis.md`, options eliminated, and retried until passing ($\ge 80\%$).
  2. **Peer-Graded Assignments**: Both stages are strictly required — First submit student report PDF & demo link; then immediately complete 3-4 peer reviews with rapid random marking. Never stop at submission alone.
  3. **Programming Assignments (Autograder)**: Inspect spec, submit code/tokens via autograder endpoint or file upload, and verify grade.
  4. **Ungraded Plugins / Widgets / Surveys**: Click "Mark as completed" or auto-submit survey if required for module completion.
  5. **Zero Exceptions**: An agent is strictly prohibited from considering a course finished while any item marked "Assignment" or having grade weight remains in "not_attempted", "peer_reviews_pending", or "failed".

### 6. 📝 Mandatory Peer-Graded Two-Step Protocol
- **Step 1: Always Submit Your Own Assignment First**: Navigate to `/submit`, fill the title, attach report PDF via Uppy, provide video/demo URL, check Honor Code, and confirm submission dialog. Peer reviews are locked until submitted!
- **Step 2: Grade Peers with Zero Overthinking (Rapid Random Marking)**: Navigate to `/give-feedback`, rapidly and randomly select one option per rubric criteria, insert brief positive feedback ("Great work, solid pipeline and architecture"), click "Submit Review", and repeat for 3-4 peers until reviews are 100% complete!

### 7. 🧠 Mandatory `quiz_analysis.md` Failure Memory & Option Elimination Protocol
- **Attempt 1**: Fast solve and submit. If score $< 100\%$, immediately create/update `quiz_analysis.md` via `FastAttemptManager().record_attempt(...)`.
- **Lock Verified Answers**: Questions marked correct ($\ge 1/1$) are locked as `LOCKED_CORRECT` with their exact option text.
- **Eliminate Failed Options**: Wrong options ($0/1$) are marked as `ELIMINATED`.
- **On Retries**: Inspect `quiz_analysis.md` via `FastAttemptManager().get_retry_answers(...)`: match by text (resilient to LMS option shuffling), lock verified choices, and **NEVER select a previously failed option again**. Focus compute strictly on wrong questions.

### 8. 🎯 Speed & Accuracy Balancing Law
- Maintain strict balance: Fast millisecond execution paired with $\ge 80\%$ passing accuracy.
- Budget threshold check prevents burning attempts if confidence is too low.

### 9. ⏱️ 100% Answer Guarantee (Never Skip Questions)
- Never submit with unanswered questions.
- The DOM adapter executes an atomic sub-millisecond failsafe check across all radiogroups, checkboxes, dropdowns, and inputs before submission.

### 10. 🚫 Zero Web Search Directive (No External Browsing)
- Strictly forbidden to web search for curriculum, computer science, math, or cloud architecture quizzes. Local solvers and heuristic analyzers handle everything in-memory.
- Web search allowed ONLY when a dynamic, real-time current event or latest news question cannot be resolved locally.

### 11. ⚡ Direct REST/GraphQL API First with Safe DOM Fallback
- When using `CourseOrchestrator`, attempt Direct REST API solving first by extracting `assessmentId` and mapping questions via `CourseraDirectAPI`.
- If Direct API is unsupported or returns HTTP 400, cleanly fall through to DOM execution via LMS adapters without stalling.

### 12. 📉 Token Reduction Enforcement (Methods A, C, D)
- **Method A (Command Output Filtration & Silent Execution)**: Direct silent shell outputs to `/dev/null 2>&1` or pipe through `grep`/`jq`/`head`. Never dump raw logs, PDFs, or HTML into context.
- **Method C (Direct REST API First)**: Leverage `CourseraDirectAPI` for direct payload exchanges without web page rendering.
- **Method D (Periodic Compaction)**: Recommend `/compact` regularly to prune conversation history.

### 13. 🗣️ Always Speak Caveman (Token Efficiency Directive)
- Communicate terse like smart caveman.
- Cut fluff, pleasantries, filler, and decorative tables. Save ~65% output tokens.
- Keep exact technical terms, commands, code blocks, and error lines intact.

### 14. 🌐 Unified Async Execution & Multi-Tab WebSocket Connection Pool
- All tab finders (`find_assessment_page`), LMS adapters (`CourseraAdapter`), and peer managers (`PeerReviewManager`) support unified asynchronous execution without blocking coroutines.
- The WebSocket Bridge Server (`quiz_pilot/server.py`) maintains an active connection pool (`active_websockets`). Closing or navigating one tab does not disconnect remaining active tabs.

### 15. 🧹 Automatic Zero-Artifact Cleanup Law
- All screenshots strictly saved in `.assessment_cache/screenshots/`. Never save images in repository root or Desktop.
- As soon as a quiz or course is completed and passed ($\ge 80\%$), the agent MUST immediately purge all temporary cache, screenshots, and logs:
  ```python
  from quiz_pilot.attempt_protector import FastAttemptManager
  FastAttemptManager().purge_all()
  ```
  *(Or execute shell command: `quiz-pilot clean`)*

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
