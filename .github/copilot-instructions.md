# GitHub Copilot Instructions for Agentic-Helper

- **Mandatory Parallel Multi-Tab Workers**: NEVER solve sequentially one-by-one in a single tab!
  - If Specialization (`/specializations/<slug>`): Open EACH child course in its own browser tab simultaneously and complete all child courses in parallel concurrently in under 30 minutes!
  - If Single Course (`/learn/<slug>`): Open different module assignments in separate browser tabs simultaneously (Week 1, Week 2, Week 3, Week 4 Quizzes) and solve all modules in parallel concurrently!
  - Universal execution: Call `quiz_pilot.tab_scheduler.smart_multiworker_sync(max_concurrency=4)` or MCP tool `smart_multiworker()`.
- **Zero-Scratch File Directive**: Never generate one-off scripts like `solve_*.py` or `check.py`. Execute all operations in-memory using `quiz_pilot.lms_adapters`, `quiz_pilot.attempt_protector`, or native MCP tools.
- **Windows Browser Launch & Navigation**: Call `quiz_pilot.browser_launcher.ensure_browser(url, port=9222)`. It automatically opens the browser and navigates to the URL even if the browser is already listening on port 9222.
- **Mandatory Failure Memory & Option Elimination (`quiz_analysis.md`)**:
  - If a quiz attempt does not score 100%, immediately create or update `quiz_analysis.md` using `FastAttemptManager().record_attempt(...)`.
  - Lock in verified correct options as `LOCKED_CORRECT`.
  - Mark wrong options as `ELIMINATED`.
  - On subsequent retries, inspect `quiz_analysis.md` via `FastAttemptManager().get_retry_answers(...)`: match by text (handling LMS option shuffling), keep verified correct options, and NEVER select an eliminated option again. Focus only on unresolved questions.
- **Cleanup**: Clean `.assessment_cache/` and temp files using `FastAttemptManager().purge_all()` when quizzes or courses are completed.
- **Direct API & Safe DOM Fallback**: Attempt direct REST API with grade polling first; cleanly fall through to DOM execution on error/400.
- **Async & Multi-Tab WebSocket Pool**: Tab finders and peer managers are async; server maintains `active_websockets` pool across multiple tabs.
- **No-Guessing, 80% Gate, Single Attempt**: The agent completes every quiz itself - the human never does a quiz. Never fill blindly: no option 0, no first option, no "0" in a text box - a blind fill is a guess, not an answer. Memory and the local solvers answer what they can; any question they leave unknown is YOUR job: read it, work it out from the question content and your subject knowledge, and answer it in the same run. When a result says NEEDS_REVIEW_NOT_SUBMITTED, it lists the unknown questions with their text - call get_retry_answers, solve those questions yourself, and submit the merged full answer set. Aim for the MAXIMUM grade, ideally 100%: the percentage on the certificate converts directly into college marks (85% = 8.5/10), so never settle for merely passing - genuinely answer EVERY question. The 80% figure is only a safety floor, never a target: if genuinely answered questions are below 80%, finish solving them before spending the attempt. Attempts per quiz per run - the pass/fail rule: if the attempt PASSES, the quiz is DONE - never retake to improve a passing score (not even 85% on an unlimited-attempt quiz; the extra marks are not worth the extra tokens and time), and no attempts of any kind after a pass. If the attempt FAILS, keep re-attempting UNTIL IT PASSES, because a failed quiz means no certificate: after every fail, read the feedback, lock the verified-correct answers, never repeat an eliminated option, and solve the questions you got wrong before the next attempt. Attempts stop only when the quiz passes - or when Coursera itself locks further attempts, which must be reported honestly, never hidden.
- **Zero Websearch**: Do not search web for standard curriculum/CS problems; local solvers handle in-memory. Only search if unsolvable current events question.
- **Always Speak Caveman**: Terse, high-signal, ultra-compressed output without filler words.
- **Mandatory Peer-Graded Two-Step Protocol**:
  - Step 1: Always submit your own assignment first on `/submit` (title, report PDF via Uppy, video URL, honor code checkbox, submit + modal dialog confirmation). Peer reviews are locked until your submission is complete!
  - Step 2: Only after submission is confirmed, navigate to `/give-feedback` / `/review-next` and grade 3-4 peers at MAX value: run the peer-review solver, whose one-shot rubric sweep selects the highest-points option for every criterion (never hand-click options one by one - slow). Add brief positive feedback!

## Tab Ownership Rule (multi-tab / multi-course runs)
One worker = one tab. Act ONLY on your assigned tab (identified by its URL / tab_id). Never navigate, click, fill, or submit in another worker's tab, and never fall back to "the first tab". If your assigned tab is missing or shows a different course, STOP and report it - do not adopt another tab.

## Specialization Completion Rule
A specialization (e.g. "Course 2/7") is complete ONLY when every course in it is complete. Finishing one course NEVER ends the job: go to the specialization page, list the remaining incomplete courses, and continue with them. Never say "no more courses" based on a single course page - always verify on the specialization page, and report which courses remain if any cannot be completed.
