# AGENT DIRECTIVE & SPECIFICATION: BRAIN-DRIVEN MULTIWORKER REFACTOR

> **Target Audience**: Next Autonomous Coding Agent / Developer  
> **Repository Path**: `/home/atomic/Projects/quiz-pilot`  
> **Skill Path**: `/home/atomic/.gemini-account2/.gemini/skills/agentic-helper/SKILL.md` (and all skill mirror directories)  
> **Baseline Status**: Clean Git tree, 76/76 pytest tests passing.

---

## 1. Core Problem Statement & User's Vision

### 💡 The User's Philosophy:
> *"See, we just give the tools and skills, and the brain thinks and does the things."*

### What Went Wrong Previously:
1. **Blind Script Execution**: Previously, the AI agent (Antigravity/Gemini) was instructed by `SKILL.md` to run a single monolithic command:
   ```bash
   agentic-helper multiworker "<course_url>" --concurrency 4
   ```
   and then completely step away.
2. **Chaos in Python Background Loop**:
   - `syllabus_crawler.py` had loose scraping logic that captured non-assignment rows (e.g., discussion links, welcome links, unenroll buttons, grade calculation links).
   - It picked the *first* `<a>` tag inside table rows, which was often a random user/course link rather than the actual assignment link (`/exam/`, `/quiz/`, etc.).
   - As a result, the Python script opened 4 tabs, closed 1 tab, and started navigating to random Coursera pages.
   - The AI Brain had zero visibility or control while this was happening.

### What the Architecture MUST Be:
- **The AI Brain is the DRIVER**: The AI agent actively inspects the syllabus, reasons about what is incomplete, filters out invalid/junk links, and instructs the worker to open ONLY the verified assignment links.
- **Tools are the Hands, AI is the Brain**:
  - Hands (CLI/Tools): `crawl-syllabus`, `list-tabs`, `multiworker <url1> <url2>...`, `submit-peer`, `complete-reviews`.
  - Brain (AI Agent): Reasons about the course state, decides the plan, passes exact URLs, and verifies pass/fail results.

---

## 2. Exhaustive Step-by-Step Task List for the New Agent

### Task 1: Fix `quiz_pilot/syllabus_crawler.py` (Eliminate Random Links)
1. **Fix Row Filtering Logic** (around line 136):
   - Change:
     ```javascript
     if (!linkEl && !isAssignmentRow) return;
     ```
     To:
     ```javascript
     if (!linkEl || !isAssignmentRow) return;
     ```
     *(A row MUST have a valid link AND be an assignment row).*
2. **Target Specific Assignment URLs**:
   - Do NOT just grab `r.querySelector('a[href]')` (which grabs author/forum links).
   - Query specifically for assessment links:
     ```javascript
     let targetLink = r.querySelector(
         'a[href*="/exam/"], a[href*="/quiz/"], a[href*="/assignment-submission/"], a[href*="/peer/"], a[href*="/supplement/"], a[href*="/programming/"], a[href*="/item/"]'
     );
     if (!targetLink) {
         targetLink = r.querySelector('a[href*="/learn/"]');
     }
     ```
3. **Filter Out Noise**:
   - Reject URLs containing: `/home/welcome`, `/discussions`, `/announcements`, `/resources`, `/grades/calculator`, `unenroll`, `help`.
4. **Enforce Valid URL in `execution_plan`**:
   - Ensure every item added to `results` and `execution_plan` has a non-empty, valid HTTP/HTTPS URL (`it["url"].startswith("http")`).

---

### Task 2: Enhance `quiz_pilot/cli.py` (`crawl-syllabus` for AI Brain)
1. **Add `--json` Flag**:
   - In `add_parser("crawl-syllabus")`:
     ```python
     p_csyl.add_argument("--json", action="store_true", help="Output execution plan as clean JSON")
     ```
2. **Output Full URLs in Terminal & JSON**:
   - Update `cmd_crawl_syllabus`:
     - If `args.json`: print `json.dumps(res, indent=2)`.
     - In text mode: print the URL so the AI agent can read it directly:
       ```python
       console.print(f" - [{it.get('type')}] [bold white]{it.get('title')}[/] ({it.get('status')}) -> {it.get('url')}")
       ```

---

### Task 3: In-Place Tab Reuse & Multi-URL Handling
1. **Review `quiz_pilot/tab_scheduler.py`**:
   - Ensure `open_and_solve_parallel(urls=[...])` accepts up to 4 exact URLs passed by the AI Brain, mounts them in tabs, solves them concurrently, and returns clean per-tab pass/fail results.
2. **Review `quiz_pilot/course_orchestrator.py`**:
   - Ensure helper tabs are reused efficiently and not prematurely opened and closed when sequential batches run.

---

### Task 4: Rewrite `SKILL.md` to Guide the AI Brain
Update `SKILL.md` (and all 6 copies located across `~/.gemini-account2/.gemini/skills/agentic-helper/`, `~/.agents/skills/`, etc.):
Replace the blind single-command instruction with the **Brain-Guided Multiworker Protocol**:

```markdown
### Phase 3: Brain-Guided Multi-Tab Execution Protocol

The AI Agent acts as the intelligent director, using tools to inspect and execute:

#### Step 1: Syllabus Inspection & Plan Generation
The AI Agent crawls the course assignments to get the clean execution plan:
```bash
agentic-helper crawl-syllabus "<course_url>" --json
```

#### Step 2: AI Brain Review & URL Filtering
The AI Agent reads the output:
- Filters out any non-assessment tasks.
- Identifies the real pending/failed assignments for the active course.
- Groups them into batches of up to 4 URLs (e.g. Week 1 Quiz, Week 2 Quiz, Week 3 Quiz, Week 4 Quiz).

#### Step 3: Targeted Multiworker Execution
The AI Agent passes the EXACT, verified URLs to the parallel solver:
```bash
agentic-helper multiworker "<quiz_url_1>" "<quiz_url_2>" "<quiz_url_3>" "<quiz_url_4>" --concurrency 4
```
*Note: Because exact URLs are provided, the engine will NOT crawl or guess random links. It will open only these 4 tabs, solve them in parallel, and return results.*

#### Step 4: Verification & Progression
- The AI Agent checks the score of each tab from the output.
- If an item is a peer assignment, run:
  ```bash
  agentic-helper submit-peer
  agentic-helper complete-reviews
  ```
- If all modules in the course are passed, proceed to the next course in the specialization.
```

---

## 3. Strict Quality & Safety Guidelines
1. **Zero Scratch Files**: Do NOT write temporary `.py` test scripts in `/tmp` or project root.
2. **Preserve All Existing Tests**:
   - Run `pytest /home/atomic/Projects/quiz-pilot/tests`
   - All 76 tests must pass cleanly.
3. **Keep `README.md` Untouched**: Do NOT edit or overwrite `README.md`.
4. **Editable Install**: Remember `pip install -e /home/atomic/Projects/quiz-pilot` is active. Any changes to the package files reflect immediately.

---

## 4. Quick Verification Commands
```bash
# 1. Run full test suite
pytest /home/atomic/Projects/quiz-pilot/tests

# 2. Verify crawl-syllabus with json
agentic-helper crawl-syllabus "https://www.coursera.org/learn/sample-course" --help
```
