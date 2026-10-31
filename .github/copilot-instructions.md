# GitHub Copilot Instructions for Agentic-Helper

- **Zero-Scratch File Directive**: Never generate one-off scripts like `solve_*.py` or `check.py`. Execute all operations in-memory using `quiz_pilot.lms_adapters`, `quiz_pilot.attempt_protector`, or native MCP tools.
- **Windows Browser Launch & Navigation**: Call `quiz_pilot.browser_launcher.ensure_browser(url, port=9222)`. It automatically opens the browser and navigates to the URL even if the browser is already listening on port 9222.
- **Mandatory Failure Memory & Option Elimination (`quiz_analysis.md`)**:
  - If a quiz attempt does not score 100%, immediately create or update `quiz_analysis.md` using `FastAttemptManager().record_attempt(...)`.
  - Lock in verified correct options as `LOCKED_CORRECT`.
  - Mark wrong options as `ELIMINATED`.
  - On subsequent retries, inspect `quiz_analysis.md` via `FastAttemptManager().get_retry_answers(...)`: match by text (handling LMS option shuffling), keep verified correct options, and NEVER select an eliminated option again. Focus only on unresolved questions.
- **Cleanup**: Clean `.assessment_cache/` using `FastAttemptManager().purge_all()` when quizzes are completed.
