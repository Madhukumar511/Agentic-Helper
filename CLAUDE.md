# CLAUDE.md — Agent Guidelines & Immutable Laws for Agentic-Helper

## 🚀 Primary Objective
Autonomous LMS and Web Assessment Automation Engine for Coursera, Canvas, Moodle, Blackboard, and Google Forms.
Enforces zero human terminal setup, multi-tab parallel workers, and self-healing execution.

---

## ⚡ Immutable Agent Laws (NEVER VIOLATE)

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
- Once passed, clean internal cache via `FastAttemptManager().purge_all()`.

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
