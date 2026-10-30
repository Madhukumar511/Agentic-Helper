# Agentic-Helper 🚀

> **The Universal LMS & Online Assessment Automation Engine for Autonomous AI Agents**  
> Connect any AI coding agent (**Google Antigravity IDE**, **Cursor**, **Claude Code**, **OpenAI Codex**) to your live browser session to reliably inspect, solve, and submit assessments across **Coursera**, **Canvas**, **Moodle**, **Blackboard**, and **Google Forms** with sub-second speed and zero human effort.

[![GitHub License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-orange.svg)](https://playwright.dev)
[![Antigravity IDE](https://img.shields.io/badge/Antigravity-Zero--Touch%20Skill-purple.svg)](GEMINI.md)
[![Tests Passing](https://img.shields.io/badge/Tests-14%2F14%20Passing-success.svg)](tests/)

---

## ⚡ Why Agentic-Helper?

Unlike generic vision-based AI browser tools that simulate slow mouse movements and burn thousands of vision tokens:

1. **⚡ Sub-Second Speed**: Injects answers directly into the browser's DOM and React state via Chrome DevTools Protocol (CDP) in **~50 ms per question**.
2. **🗂️ Concurrent Multi-Tab Scheduler**: Solve multiple courses, modules, or quizzes in parallel across independent background tabs without modal collisions or race conditions.
3. **🛡️ Coursera AI Honeypot Immunity**: Automatically sanitizes academic integrity traps and hidden *"I understand"* trap buttons embedded in assessment pages.
4. **🧠 Deterministic Graph & Diagram Solvers**: Built-in computer vision (<200ms OpenCV) and algorithmic solvers for distributed systems (Lamport clocks, Vector Clocks, FIFO/Causal Multicast, Chandy-Lamport Snapshots).
5. **🧹 Strict Zero-Artifact Law**: Operates 100% in-memory. Never leaves one-off `.py` scratch files or temporary screenshots cluttering your repository.

---

## 🚀 Quick Start (Zero-Terminal Setup)

### Option 1: In Google Antigravity IDE (Recommended)
1. Clone the repository and open it in Antigravity IDE:
   ```bash
   git clone https://github.com/Madhukumar511/Agentic-Helper.git
   ```
2. Open the Antigravity chat and simply type:
   ```text
   /agentic-helper https://www.coursera.org/learn/your-course-name
   ```
   *The AI agent automatically checks dependencies, launches Chrome on port 9222, opens the course, and solves the assessments for you!*

---

### Option 2: 1-Click Environment Setup (Manual / Standalone)

#### 🪟 Windows (1-Click)
1. Double-click `setup.bat` (or run in PowerShell: `.\setup.bat`).
2. Double-click `launch_browser_windows.bat` to launch Chrome on debug port 9222.
3. Open your assessment in that browser.

#### 🐧 Linux / 🍎 macOS (1-Click)
1. Run setup:
   ```bash
   chmod +x setup.sh && ./setup.sh
   ```
2. Launch Chrome or Chromium with debugging:
   ```bash
   google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/agent_browser &
   ```

---

## 🗂️ Concurrent Multi-Tab Architecture

Agentic-Helper features an **Async Multi-Tab Queue Scheduler** (`AsyncTabScheduler`). You can open 3, 4, or 5 course quizzes in separate browser tabs and solve them simultaneously:

```mermaid
flowchart TD
    Browser["Chromium Browser (CDP Port 9222)"] --> Tab1["Tab 1: Course A Quiz"]
    Browser --> Tab2["Tab 2: Course B Quiz"]
    Browser --> Tab3["Tab 3: Course C Quiz"]

    Scheduler["AsyncTabScheduler (Bounded Concurrency Pool)"]
    Scheduler --> Worker1["Tab Worker 1"]
    Scheduler --> Worker2["Tab Worker 2"]
    Scheduler --> Worker3["Tab Worker 3"]

    Worker1 -.->|DOM Lifecycle & Modal Isolation| Tab1
    Worker2 -.->|DOM Lifecycle & Modal Isolation| Tab2
    Worker3 -.->|DOM Lifecycle & Modal Isolation| Tab3

    Worker1 --> Res["Consolidated Scorecard & Auto-Purge"]
    Worker2 --> Res
    Worker3 --> Res
```

### Run Multi-Tab Solving via CLI:
```bash
# Solve all open assessment tabs simultaneously (up to 4 in parallel)
agentic-helper multiworker --concurrency 4
# or:
agentic-helper solve-all --concurrency 4
```

### Run Multi-Tab Solving via Python API:
```python
from quiz_pilot.tab_scheduler import solve_all_open_quizzes_sync

results = solve_all_open_quizzes_sync(max_concurrency=4, auto_submit=True)
print(f"Passed {results['passed_count']} of {results['total_tabs']} quizzes concurrently!")
```

---

## 🔌 AI Agent Integration (MCP Protocol)

Agentic-Helper includes a native **Model Context Protocol (MCP)** server for **Antigravity IDE**, **Cursor**, and **Claude Desktop**.

### Native MCP Tools Included:
| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `launch_browser` | `url, port` | Auto-detects Chrome/Edge/Brave and launches on CDP port 9222. |
| `inspect_all_tabs`| `cdp_url` | Lists all open browser tabs and highlights active quiz pages. |
| `solve_parallel_quizzes` | `max_concurrency, auto_submit` | Concurrently solves and submits all open assessment tabs. |
| `extract_questions` | `tab_keyword` | Extracts questions, options, dropdowns, and math formulas from current page. |
| `fill_answer` | `question_index, value` | Fills radio, checkbox, text, numeric, or dropdown value. |
| `solve_batch` | `answers` | Batch-fills multiple answers in a single call (<100ms). |
| `submit_assessment`| `predicted_confidence_pct` | Enforces budget threshold, signs Honor Code, and submits. |
| `get_feedback` | — | Extracts final score percentage and pass/fail badges. |
| `solve_diagram` | `image_path` | Sub-second OpenCV/NumPy spacetime diagram parser (<200ms). |
| `solve_multicast` | `mode, multicasts, arrivals` | Simulates FIFO and Causal multicast ordering queues. |

### Configuration:
* **Antigravity IDE**: Included out-of-the-box via workspace `.gemini/settings.json`.
* **Cursor (`~/.cursor/mcp.json`)**:
  ```json
  {
    "mcpServers": {
      "agentic-helper": {
        "command": "python",
        "args": ["-m", "quiz_pilot.mcp_server"]
      }
    }
  }
  ```

---

## 🎯 Supported Learning Management Systems (LMS)

| Platform | Features Supported |
| :--- | :--- |
| **Coursera** | Leaf radiogroups, honor code checkboxes, tunnel-vision dialogs, anti-AI honeypot sanitization. |
| **Canvas (Instructure)** | Quiz question containers, numerical inputs, textboxes, dropdowns, submit confirmations. |
| **Moodle** | Multi-choice questions, pagination traversal, review screens. |
| **Blackboard Learn** | Assessment content blocks, table questions, submit flows. |
| **Google Forms** | List items, radio options, checkboxes, short answers. |

---

## 🧠 Algorithmic & Diagram Solvers

For Computer Science, Distributed Systems, and Graph Theory courses:

```python
from quiz_pilot.diagram_parser import LocalDiagramParser
from quiz_pilot.graph_solvers import MulticastSimulator, LamportVectorClockSolver

# 1. Fast sub-second space-time diagram parser
parser = LocalDiagramParser()
diagram = parser.parse_spacetime_diagram("diagram.png")
solution = parser.solve_fast_lamport(diagram)

# 2. Multicast FIFO & Causal Ordering Simulation
sim = MulticastSimulator(num_processes=4)
causal = sim.simulate_causal(
    num_processes=4,
    multicasts=[{"id": "M1", "src": 1}],
    arrivals=[{"msg": "M1", "dst": 0}]
)
```

---

## 🛡️ Attempt Budget Protector & Zero-Artifact Law

1. **Attempt Budget Protector**: Prevents burning limited attempts (e.g. 3 attempts per 8 hours) by blocking submissions if confidence score is below threshold (default 80%).
2. **Zero-Compute Diff Caching**: On Attempt 2, verified correct answers are locked in with **0 extra compute**, recalculating only missed questions.
3. **Mandatory Post-Quiz Purge**: When an assessment is passed, all temporary caches and screenshots are automatically wiped to keep the workspace 100% clean:
   ```bash
   agentic-helper clean
   ```

---

## 🧪 Testing

All 14 unit tests pass in under 1 second:
```bash
pytest
# OR
python -m unittest discover -s tests
```

---

## 📚 Dedicated Guides
* **[AGENTS.md](AGENTS.md)** — Operating manual and directives for autonomous AI agents.
* **[GEMINI.md](GEMINI.md)** — Antigravity IDE configuration & `/agentic-helper` guide.
* **[WINDOWS_GUIDE.md](WINDOWS_GUIDE.md)** — Windows 10/11 PowerShell guide and troubleshooting.

---

## 📜 License

MIT License. Designed for academic research, education automation, and AI agent experimentation.
