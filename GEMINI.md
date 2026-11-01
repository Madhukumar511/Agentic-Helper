# GEMINI.md — Antigravity IDE & Gemini Assistant Guide

This document defines how **Google Antigravity IDE** and **Gemini Coding Agents** interact with **Agentic-Helper**.

---

## ⚡ Slash Command: `/agentic-helper` (Zero Human Terminal Setup)

When the user types `/agentic-helper [course_url]`, or asks you to *"solve quiz"* / *"complete assessment"*:
1. **Self-Healing Setup (Silent)**: Verify dependencies; if missing, install them automatically (`pip install -e . && python -m playwright install chromium`).
2. **Auto-Launch & Navigate Browser**: Ensure Chrome/Edge is listening on 9222 and navigated to the target URL using `quiz_pilot.browser_launcher.ensure_browser(url)` (which opens and navigates the link automatically across Windows, Linux, and macOS).
3. **Login Gate**: If Coursera shows a login screen, ask the user to log in and say "continue". If already logged in, proceed immediately!
4. **Operate entirely in-memory**: Never write one-off course scripts (e.g., `solve_hw.py`) to disk! Use `CourseraAdapter` or native MCP tools directly.
5. **Mandatory Parallel Multi-Tab Dispatch (Specialization vs Single Course)**:
   - **NEVER run sequentially in a single tab!**
   - **Specialization Course (`/specializations/<slug>`)**: Open **EACH child course in its own browser tab simultaneously** and complete all child courses in parallel concurrently in under 30 minutes!
   - **Single Course (`/learn/<slug>`)**: Open **different module quizzes in separate browser tabs simultaneously** (Week 1, Week 2, Week 3, Week 4 Quizzes) and solve all modules in parallel concurrently!
   - **Universal Execution**: Call `quiz_pilot.tab_scheduler.smart_multiworker_sync(max_concurrency=4)` or MCP tool `smart_multiworker()`.
6. **Mandatory Failure Memory & Option Elimination (`quiz_analysis.md`)**:
   - If an attempt scores $< 100\%$ or fails, immediately create or update `quiz_analysis.md` via `FastAttemptManager().record_attempt(...)` or MCP `record_quiz_analysis`.
   - Record verified correct option texts (`LOCKED_CORRECT`) and eliminate failed option texts (`ELIMINATED`).
   - On retry, inspect `quiz_analysis.md` via `FastAttemptManager().get_retry_answers(...)`: lock in verified choices by text match across shuffled options, focus 100% of compute strictly on wrong questions, and **NEVER select a previously failed option again**!
7. **Mandatory Post-Quiz & Post-Course Purge**: When passed ($\ge 80\%$) or course completes, automatically run `FastAttemptManager().purge_all()` or `agentic-helper clean` to wipe internal temporary caches and bridge files while keeping verified analysis.
8. **Direct REST API Acceleration with Safe DOM Fallback**: Attempt Direct REST API submissions with grade polling and `quiz_analysis.md` syncing first; cleanly fall through to DOM execution if unsupported or on error/HTTP 400.
9. **Unified Async Execution**: Use async tab finders (`await find_assessment_page`) and connection pool multi-tab bridge without blocking event loops.
10. **Mandatory 100% Answer Guarantee**: Never leave any question unanswered. Atomic DOM sweep selects candidate/fallback within milliseconds (<50ms).
11. **Zero Websearch Law**: Never trigger web search for CS/systems questions. Built-in solvers execute in-memory. Search permitted ONLY if unsolvable dynamic current event.
12. **Always Speak Caveman**: Speak terse smart caveman. Drop filler, pleasantries, tokens. High-signal technical accuracy only.
13. **Mandatory Peer-Graded Two-Step Protocol**: Always submit your own assignment first on `/submit` (title, report PDF via Uppy, video URL, honor code checkbox, primary submit + modal dialog confirmation). Only after submission is complete, navigate to `/give-feedback` / `/review-next` and grade 3-4 peers at MAX value: run the peer-review solver, whose one-shot rubric sweep selects the highest-points option for every criterion (never hand-click options one by one - slow). Add brief positive feedback!
14. **Advance**: Move to the next quiz until the entire course or specialization is passed!


---

## 🖥️ Antigravity IDE Configuration (Zero-Config After Clone)

When you clone **Agentic-Helper** into Antigravity IDE, **it works immediately with zero manual configuration**:
- `.gemini/settings.json` is already included to auto-register the native MCP server.
- `.gemini/skills/agentic-helper/SKILL.md` is already in the workspace, so Antigravity automatically activates the `/agentic-helper` skill.

### 1-Click Environment Setup

#### On Windows:
Double-click `setup.bat` (or run in terminal):
```powershell
.\setup.bat
```

#### On Linux / macOS:
Run `setup.sh`:
```bash
./setup.sh
```

*(Or manually: `pip install -e . && playwright install chromium`)*

---

### Global Skill Installation (Optional for all projects)
If you want `/agentic-helper` available in *every* Antigravity project globally:
* **Linux/macOS**: `~/.gemini/skills/agentic-helper/SKILL.md` (or `~/.agents/skills/agentic-helper/SKILL.md`)
* **Windows**: `%USERPROFILE%\.gemini\skills\agentic-helper\SKILL.md` (or `%USERPROFILE%\.agents\skills\agentic-helper\SKILL.md`)

---

### Antigravity MCP Configuration (Included in Workspace)
The workspace `.gemini/settings.json` automatically connects the tools:
```json
{
  "mcpServers": {
    "agentic-helper": {
      "command": "python3",
      "args": ["-m", "quiz_pilot.mcp_server"]
    }
  }
}
```
*(On Windows, Antigravity seamlessly invokes `python`)*

---

## 🚀 Execution Flow in Antigravity IDE

```mermaid
flowchart TD
    User["User in Antigravity Chat: /agentic-helper"] --> Skill["Activate Skill: agentic-helper"]
    Skill --> CDP["Connect over CDP (http://127.0.0.1:9222)"]
    CDP --> Extract["CourseraAdapter / LMS Adapter: Extract Questions"]
    Extract --> AntiTrap["Sanitize Honeypots & Prompt Injections"]
    AntiTrap --> FastAttempt["Fast 3-Attempt Strategy"]
    FastAttempt --> Attempt1["Attempt 1: Direct Reasoning + Diagram Solver (<200ms)"]
    Attempt1 --> Cache["Cache Output in .assessment_cache/<quiz>_attempt_1.md"]
    Cache --> Submit["Submit & Check Grade"]
    Submit --> CheckScore{"Score >= 80%?"}
    CheckScore -->|Yes| Purge["Purge Cache & Report Success"]
    CheckScore -->|No| Diff["Attempt 2/3: Zero-Compute Diff on Missed Questions"]
    Diff --> Submit
```

---

## 🪟 Windows Antigravity IDE Quick Steps

1. **Open PowerShell as Administrator** (or standard user).
2. **Launch Chrome or Edge with debugging**:
   ```powershell
   & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\tmp\agent_browser"
   # Or Microsoft Edge:
   & "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\tmp\agent_browser"
   ```
3. **Log in to your LMS (Coursera, Canvas, Moodle, etc.) and open the quiz.**
4. **In Antigravity IDE Chat, type**:
   ```text
   /agentic-helper
   ```
5. **The agent takes over and solves the assessment automatically!**
