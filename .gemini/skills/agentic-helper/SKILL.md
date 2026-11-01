---
name: agentic-helper
description: Universal LMS and Web Assessment Automation Engine. Automatically bootstraps dependencies, launches browser with remote debugging port 9222, connects to Coursera/Canvas, waits for login if needed, extracts questions, solves domain/graph/theory problems, and submits quizzes across Coursera, Canvas, Moodle, Blackboard, Google Forms, and custom web assessments. Supports multi-tab parallel workers. Use whenever the user types /agentic-helper, /agentic-helper multiworker, "solve quiz", "complete assessment", "do coursera quiz", "automate exam", or asks the agent to autonomously complete an online assessment.
---

# Agentic-Helper: Autonomous LMS Assessment Engine

When invoked (via `/agentic-helper`, course URLs, or assessment requests), take **100% autonomous end-to-end responsibility**. 
The human user does **NOT** need to run any terminal commands or install anything manually.

> [!CAUTION]
> **IMMUTABLE ENGINE LAW: ZERO SCRATCH PYTHON FILES**
> Agents must **NEVER** write one-off Python scripts (e.g. `solve_hw1.py`, `quiz.py`, `check.py`, `dump.py`) to disk!
> The entire engine is already pre-built in `quiz_pilot`. All operations must execute **in-memory** directly via Playwright CDP, `CourseraAdapter`, `FastAttemptManager`, or native MCP tools. The repository must remain completely pristine.

> [!IMPORTANT]
> **MANDATORY PARALLEL MULTI-TAB DISPATCH DIRECTIVE (ALL AGENTS & PLATFORMS)**
> Whenever `/agentic-helper` is invoked on Windows, macOS, or Linux, **NEVER solve sequentially one-by-one in a single tab!**
> Agents **MUST** inspect the course type and immediately execute multi-tab parallel workers:
> - **Specialization Course (`/specializations/<slug>`)**: Open **EACH child course in its own browser tab simultaneously** and complete all child courses in parallel concurrently!
> - **Single Course (`/learn/<slug>`)**: Open **different module assignments in separate browser tabs simultaneously** (Week 1, Week 2, Week 3, Week 4 Quizzes) and complete all modules in parallel concurrently!
> - **Universal 1-Line Execution**: `smart_multiworker_sync(max_concurrency=4)` (or MCP `smart_multiworker()`, or CLI `agentic-helper multiworker --concurrency 4`). Specializations must finish in under 30 minutes!

---

## ⚡ Zero-Touch Autonomous Execution Protocol

### Phase 0: Self-Healing Environment Setup (Run Silently)
Before anything else, verify that required dependencies exist. If not, install them in the background without asking the user:
```bash
python3 -c "import playwright" 2>/dev/null || (pip install -e . && python3 -m playwright install chromium)
# On Windows:
python -c "import playwright" 2>nul || (pip install -e . && python -m playwright install chromium)
```

---

### Phase 1: Autonomous Browser Launch & URL Navigation
Check if the debugging browser is running. If not, **launch it automatically**:
```python
from quiz_pilot.browser_launcher import ensure_browser, is_browser_running

# Launch Chrome/Edge with port 9222 and open target URL (or default Coursera)
# Cross-platform: Windows, Linux, and macOS. Automatically navigates if browser is already open!
course_url = "<URL_PROVIDED_BY_USER_OR_COURSERA>"
ensure_browser(url=course_url, port=9222)
```
*(Or use native MCP tool `launch_browser(url=course_url)` if MCP is active, or run `launch_browser_windows.bat "<course_url>"` on Windows).*

---

### Phase 2: Login Gate & User Check
Connect to the browser over CDP:
1. Inspect the active tab:
   - **If page shows a login screen** (e.g. "Sign In", "Log In", email/password inputs):
     Output a friendly message to the user:
     > *"🌐 I launched the browser and opened Coursera for you! Please log in with your credentials. Once you are logged in and on the course page, reply with **'continue'** or **'logged in'**, and I will take over autonomously!"*
     Stop and wait for the user's confirmation.
   - **If already logged in** (user profile, dashboard, or course content visible):
     Proceed immediately to Phase 3 without stopping!

---

### Phase 3: The Parallel Multi-Tab Execution Engine (Specialization vs Single Course)
Once logged in, **NEVER solve sequentially one-by-one in a single tab!**
Agents **MUST** immediately inspect the course type and parallelize across browser tabs:

#### 🌟 Case A: If it is a Specialization (`/specializations/<spec-slug>` or multi-course track)
- Discover all child courses in the specialization via `SyllabusCrawler`.
- **Open EACH child course in its own browser tab simultaneously** (up to 4 parallel tabs).
- Execute all child courses **in parallel concurrently** until the entire specialization is completed!
- Finish specializations in under 30 minutes!

#### 📚 Case B: If it is a Single Course (`/learn/<course-slug>`)
- Crawl the syllabus to extract all incomplete modules and assignments (Week 1, Week 2, Week 3, Week 4...).
- **Open EACH module assignment in its own browser tab simultaneously** (up to `max_concurrency: 4`).
- Execute all module quizzes **in parallel concurrently** so all weeks finish at once!

#### 🌐 Case C: If Multiple Assessment Tabs are Already Open
- Immediately process and solve all open tabs in parallel!

#### 🚀 1-Line Universal Execution (Auto-Detects Specialization vs Single Course):
In Python / Direct script:
```python
from quiz_pilot.tab_scheduler import smart_multiworker_sync

# Automatically inspects active page:
# - If Specialization -> opens child courses in parallel tabs & completes concurrently
# - If Single Course -> opens module quizzes in parallel tabs & completes concurrently
# - If multiple tabs already open -> completes all open tabs concurrently
results = smart_multiworker_sync(max_concurrency=4, auto_submit=True)
print(f"Passed {results.get('passed_count', 0)} tasks concurrently across tabs!")
```
*(Or via MCP: `smart_multiworker(concurrency=4, auto_submit=True)`, or CLI: `agentic-helper multiworker --concurrency 4`)*

---

### Phase 4: Tab Worker Solving & Option Elimination Protocol
Inside each parallel worker tab:
1. **Auto-Detect Platform & Extract Questions**:
   ```python
   adapter = get_lms_adapter(page)
   questions = adapter.extract_questions()
   ```

2. **Fast Diagram & Batch Answering (<150ms)**:
   - When questions contain diagrams, figures, or network topologies:
     - Check `q['diagram_meta']` or prompt `[Figure: ...]` text for immediate topology/spacetime descriptions.
     - Call `solve_diagram(image_path=img_url, question_prompt=prompt, options=options)` to get the analytical solution in `<100ms`.
     - NEVER stall, run slow OCR, download images sequentially, or spend minutes analyzing images manually.
   - Fill all answers in a single atomic batch via `adapter.batch_fill_answers(answers, auto_submit=True)` or `solve_batch(answers, auto_submit=True)`.
   - Immediately verify grade via `adapter.extract_feedback()`.

3. **Pass & Zero-Artifact Purge**:
   - When passed ($\ge 80\%$ or green pass banner), run `FastAttemptManager().purge_all()`.
   - Never leave any `solve_*.py`, JSON dumps, or temporary files on disk.

4. **Mandatory Failure Memory & Option Elimination (`quiz_analysis.md`)**:
   - If an attempt scores $< 100\%$ or fails, agents **MUST** immediately create or update `quiz_analysis.md`:
     ```python
     attempt_mgr.record_attempt(
         quiz_id=quiz_title,
         attempt_num=attempt_num,
         questions=questions,
         answers=answers,
         feedback=feedback.get("feedback", {}),
         score_pct=feedback.get("score_pct")
     )
     ```
     *(Or via MCP: `record_quiz_analysis(quiz_id=..., questions=..., answers=..., feedback=..., score_pct=...)`)*
   - **`LOCKED_CORRECT`**: Questions scored correctly are permanently locked in with their exact verified option text.
   - **`ELIMINATED`**: Questions scored incorrectly have the submitted option marked as permanently eliminated.
   - **Option Shuffling Resilience**: LMS platforms randomly shuffle option order on each attempt. Always match options by **exact text string**, NOT by old index number!
   - **On Retry Execution**:
     ```python
     retry_answers = attempt_mgr.get_retry_answers(questions, quiz_id=quiz_title)
     ```
     *(Or via MCP: `get_retry_answers(questions=...)`)*
     - Verified answers are locked in automatically by text matching with zero compute.
     - Failed questions automatically exclude previously chosen options. **NEVER select a failed option again!**
     - Select from remaining uneliminated candidate options.
   - Re-attempt and submit with corrected choices until 100% passed!

6. **Advance to Next Quiz**:
   - Automatically navigate to the next incomplete assignment in the course syllabus until the entire course or specialization is passed!

---

### Phase 3B: Intelligent Multi-Tab Concurrent Execution (`/agentic-helper multiworker`)
When the user types `/agentic-helper multiworker`:
- **Single Course Handling**: If the active browser tab or provided URL is a single course (`/learn/<course-slug>`):
  - Do NOT complete sequentially in a single tab!
  - Automatically crawl all incomplete module assignments (e.g., Week 1, Week 2, Week 3, Week 4 Quizzes).
  - Automatically open them concurrently across separate browser tabs (up to `max_concurrency: 4`).
  - Workers run in each tab in parallel simultaneously to solve all module quizzes at once!
- **Specialization Handling**: If on a specialization page (`/specializations/<spec-slug>`), discover child courses, open each course in its own background tab simultaneously, and complete them concurrently.
- **Already Open Tabs**: If multiple assessment tabs are already open in the browser, process and solve all of them concurrently.

```bash
# Direct CLI invocation with smart multiworker (auto-detects course modules or open tabs)
agentic-helper multiworker --concurrency 4
```
In Python / Native MCP:
```python
from quiz_pilot.tab_scheduler import smart_multiworker_sync

# Automatically detects course modules or open tabs, opens parallel tabs, and completes them
results = smart_multiworker_sync(max_concurrency=4, auto_submit=True)
print(f"Passed {results.get('passed_count', 0)} tasks concurrently across tabs!")
```
*(Or use native MCP tool `solve_parallel_quizzes(max_concurrency=4)`).*

---

### Phase 3C: Specialization Multi-Course Parallel Execution (`/agentic-helper multiworker complete first X courses`)
When the user requests completing the first N courses in a Specialization:
1. Discover child courses via `SyllabusCrawler.crawl_specialization_courses(spec_url)`.
2. Take the first N courses (`courses[:N]`, e.g. first 4 courses).
3. Open each course in its own background tab simultaneously.
4. Launch the parallel orchestrator via MCP tool `auto_complete_specialization(specialization_url=..., max_courses=N)` or CLI:
   ```bash
   agentic-helper multiworker <course1_url> <course2_url> <course3_url> <course4_url> --concurrency 4
   ```
5. All 4 courses execute concurrently until completion!

---

### Phase 3D: Direct REST API Acceleration with Safe DOM Fallback
- `CourseOrchestrator` automatically queries Coursera REST/GraphQL state (`__APOLLO_STATE__`) for `assessmentId`.
- Maps questions from REST payload, generates retry answers from memory, and submits directly without UI delays.
- Automatically polls `get_grade_feedback(submission_id)` and records score to `quiz_analysis.md`.
- **Safe Fallback**: If Direct API submission is unsupported, returns HTTP 400, or fails, the orchestrator cleanly falls through to the DOM adapter without crashing.

---

### Phase 3E: Unified Async & Multi-Tab WebSocket Connection Pool
- All browser interactions, tab finders (`await find_assessment_page`), and peer managers use non-blocking coroutines.
- Bridge server maintains connection pool (`active_websockets` in `quiz_pilot/server.py`), allowing multiple tabs to stay connected and isolated.

---

### Phase 3F: 100% Answer Guarantee (Never Skip Questions)
- **Zero Blank Questions**: In-memory mapping ensures every question has an answer. The DOM adapter executes an atomic sub-millisecond failsafe sweep across all input types (radios, checkboxes, selects, numbers, text) before submission.
- Fast execution: Completes check and submits within milliseconds (<50ms).

---

### Phase 3G: Zero Websearch Directive
- **NO WEB SEARCH**: Never perform web search for standard curriculum, computer science, math, or cloud architecture quizzes. Local solvers and heuristic analyzers handle everything in-memory.
- Web search is strictly forbidden unless an explicit dynamic, real-time news question is encountered that cannot be resolved locally.

---

### Phase 3H: Always Speak Caveman (Token Efficiency)
- Communicate terse like smart caveman. Drop filler, pleasantries, decorative tables.
- Save ~65% output tokens while preserving 100% technical accuracy, commands, and code.

---

### Phase 3I: Mandatory Peer-Graded Two-Step Protocol
- **Step 1: Always Submit Your Own Assignment First**:
  For any peer-graded assignment, peer reviews (`/give-feedback` or `/review-next`) are locked until your own project is submitted. Always navigate to `/submit`, fill the title, attach the report PDF via Uppy (`uppy-Dashboard-input`), provide video/demo URL, check the Honor Code agreement checkbox (`#agreement-checkbox-base`), click primary Submit, and confirm in `[data-testid="submit-dialog"]` or modal dialog.
- **Step 2: Grade Peers at Max Value (One-Shot Rubric Sweep)**:
  Once submission is confirmed, navigate to `/give-feedback` and click "Start Reviewing". In peer grading, do NOT hand-click rubric options one by one (slow, many steps). Run the peer-review solver ONCE per review: its rubric sweep reads each criterion's point values and selects the HIGHEST-points option for every criterion, so every peer gets max marks. Then insert brief positive feedback ("Great work, solid pipeline and architecture"), click "Submit Review", and repeat for 3-4 peers until reviews are 100% complete!

---

## 🧠 Built-In Algorithmic & Diagram Solvers

For Computer Science, Distributed Systems, and Graph Quizzes:

### 1. Space-Time & Distributed Execution Diagrams:
```python
from quiz_pilot.diagram_parser import LocalDiagramParser
parser = LocalDiagramParser()
parsed = parser.parse_spacetime_diagram(image_path)
solution = parser.solve_fast_lamport(parsed)
```

### 2. Vector Clocks & Event Concurrency:
```python
from quiz_pilot.graph_solvers import LamportVectorClockSolver
solver = LamportVectorClockSolver(num_processes=4)
solver.add_message('M1', src=0, dst=1)
solver.add_process_trace(0, [('send', 'M1')])
solver.add_process_trace(1, [('recv', 'M1')])
res = solver.solve()
```

### 3. Multicast FIFO & Causal Buffering:
```python
from quiz_pilot.graph_solvers import MulticastSimulator
sim = MulticastSimulator(num_processes=4)
fifo_res = sim.simulate_fifo(num_processes=4, multicasts=mcasts, arrivals=arrs)
causal_res = sim.simulate_causal(num_processes=4, multicasts=mcasts, arrivals=arrs)
```

## Tab Ownership Rule (multi-tab / multi-course runs)
One worker = one tab. Act ONLY on your assigned tab (identified by its URL / tab_id). Never navigate, click, fill, or submit in another worker's tab, and never fall back to "the first tab". If your assigned tab is missing or shows a different course, STOP and report it - do not adopt another tab.
