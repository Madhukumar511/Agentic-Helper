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
course_url = "<URL_PROVIDED_BY_USER_OR_COURSERA>"
ensure_browser(url=course_url, port=9222)
```
*(Or use native MCP tool `launch_browser(url=course_url)` if MCP is active).*

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

### Phase 3: Autonomous Course Crawl & Quiz Execution
Once logged in:
1. **Find Active Assessment Tab**:
   ```python
   from playwright.sync_api import sync_playwright
   from quiz_pilot.lms_adapters import get_lms_adapter
   from quiz_pilot.attempt_protector import FastAttemptManager

   with sync_playwright() as p:
       browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
       
       page = None
       lms_keywords = ["coursera", "canvas", "moodle", "blackboard", "exam", "quiz", "assessment", "forms"]
       for ctx in browser.contexts:
           for p_tab in ctx.pages:
               try:
                   if any(k in p_tab.url.lower() or k in p_tab.title().lower() for k in lms_keywords):
                       page = p_tab
                       break
               except Exception:
                   pass
           if page:
               break
       if not page and browser.contexts and browser.contexts[0].pages:
           page = browser.contexts[0].pages[0]
   ```

2. **Auto-Detect Platform & Extract Questions**:
   ```python
   adapter = get_lms_adapter(page)
   questions = adapter.extract_questions()
   ```

3. **Fast 3-Attempt Heuristic**:
   - Solve with direct reasoning + local graph/diagram algorithms (`<200ms`).
   - Fill answers using `adapter.fill_answer(idx, val)` or `solve_batch()`.
   - Submit via `adapter.submit_assessment()`.
   - Check grade via `adapter.extract_feedback()`.

4. **Pass & Zero-Artifact Purge**:
   - When passed ($\ge 80\%$ or green pass banner), run `FastAttemptManager().purge_all()`.
   - Never leave any `solve_*.py`, JSON dumps, or temporary files on disk.

5. **Advance to Next Quiz**:
   - Automatically navigate to the next incomplete assignment in the course syllabus until the entire course or specialization is passed!

---

### Phase 3B: Multi-Tab Concurrent Execution (`/agentic-helper multiworker`)
When the user types `/agentic-helper multiworker` or has multiple courses/quizzes open in tabs:
```bash
# Direct CLI invocation with bounded workers (default concurrency: 4)
agentic-helper multiworker --concurrency 4
# or: agentic-helper solve-all --concurrency 4
```
In Python / Native MCP:
```python
from quiz_pilot.tab_scheduler import solve_all_open_quizzes_sync

# Executes bounded concurrent workers across all open tabs in parallel
results = solve_all_open_quizzes_sync(max_concurrency=4, auto_submit=True)
print(f"Passed {results['passed_count']} of {results['total_tabs']} tabs concurrently!")
```
*(Or use native MCP tool `solve_parallel_quizzes(max_concurrency=4)`).*

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
