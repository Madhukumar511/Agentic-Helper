# Agentic-Helper 🚀

> **Universal LMS & Web Assessment Automation Engine for Autonomous AI Agents**  
> Connect any AI coding agent (Claude Code, Cursor, Antigravity, OpenAI Codex, custom LLM agents) to your live browser session to reliably inspect, reason, and solve quizzes across Coursera, Canvas, Moodle, Blackboard, Google Forms, and custom web assessments.

[![Agent Guide](https://img.shields.io/badge/Guide-AGENTS.md-blue.svg)](AGENTS.md)
[![Antigravity IDE](https://img.shields.io/badge/Antigravity-GEMINI.md-purple.svg)](GEMINI.md)
[![Windows Setup](https://img.shields.io/badge/Windows-WINDOWS__GUIDE.md-teal.svg)](WINDOWS_GUIDE.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

### 📚 Dedicated Documentation
* **[AGENTS.md](AGENTS.md)** — Universal instructions for autonomous AI agents (Antigravity, Cursor, Claude Code, Windsurf).
* **[GEMINI.md](GEMINI.md)** — Google Antigravity IDE configuration & `/agentic-helper` slash command usage.
* **[WINDOWS_GUIDE.md](WINDOWS_GUIDE.md)** — Windows 10/11 setup guide, PowerShell commands, and one-click browser launcher.


---

## 🌟 Key Features

- **🌐 Zero-API Browser Session Pairing**: No external API keys needed. Connects directly to your everyday browser session via Chrome DevTools Protocol (CDP).
- **🛡️ Anti-Prompt-Injection DOM Extractor**: Automatically strips hidden prompt injection honeypots and integrity watermarks embedded in assessment HTML.
- **⚡ Super-Fast Local Diagram Parser**: Sub-second computer vision pipeline using OpenCV & NumPy to parse space-time message diagrams and state transitions into graph adjacency matrices without burning vision tokens.
- **🧠 Deterministic Graph & Distributed Solvers**:
  - **Lamport & Vector Clocks**: Computes logical timestamps and detects event concurrency in $O(V + E)$ time.
  - **Multicast Ordering**: Simulates FIFO and Causal multicast message buffering and sequence vectors.
  - **Chandy-Lamport Snapshots**: Evaluates process snapshots and in-flight channel states.
- **🎯 Multi-LMS Modular Adapters**: Built-in drivers with automatic platform detection for:
  - **Coursera**: Leaf radiogroups, honor code checkboxes, tunnel-vision dialog handling.
  - **Canvas (Instructure)**: Question holders, numeric and essay inputs, submit dialogs.
  - **Moodle**: Question containers (`.que`), pagination, attempt finalization.
  - **Blackboard Learn**: Content boxes, assessment tables, submission flows.
  - **Google Forms**: List items, radio options, checkboxes, short answers.
- **🔒 Attempt Budget Protector & Fast-Attempt Strategy**:
  - **3-Attempt Speed Law**: Solves rapidly without endless verification loops.
  - **Temporary Answer Memory**: Caches questions, submitted answers, and grade feedback to `.assessment_cache/<quiz_id>_attempt_*.md`.
  - **0-Compute Next Attempts**: Attempts 2 & 3 instantly lock in verified 100% correct answers and compute only the remaining diffs.
  - **Dedicated Screenshot Isolation**: Enforces all screenshots strictly inside `.assessment_cache/screenshots/`.
  - **Budget Protector**: Prevents burning limited attempts (e.g. 3 attempts / 8-hour window) if confidence score is below threshold (default 80%).
  - **Auto-Purge**: Automatically deletes temporary memory files when the quiz is passed.
- **🔌 Model Context Protocol (MCP) Server**: Exposes native agent tools (`extract_questions`, `fill_answer`, `solve_batch`, `submit_assessment`, `solve_diagram`) for Cursor, Claude Desktop, and Antigravity.

---

## 💻 OS-Specific Installation & Setup

### Prerequisites
- Python 3.10 or higher
- Any Chromium-based browser (Google Chrome, Chromium, Brave, Microsoft Edge)

---

### 🐧 Linux (Ubuntu / Debian / Arch / Fedora)

1. **Clone repository**:
   ```bash
   git clone https://github.com/Madhukumar511/Agentic-Helper.git
   cd Agentic-Helper
   ```

2. **1-Click Setup**:
   ```bash
   ./setup.sh
   # (Or: pip install -e . && playwright install chromium)
   ```

3. **Launch Chrome/Chromium with Remote Debugging**:
   ```bash
   google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/agent_browser
   # OR on Chromium:
   chromium --remote-debugging-port=9222 --user-data-dir=/tmp/agent_browser
   ```

---

### 🍎 macOS (Apple Silicon / Intel)

1. **Clone and setup**:
   ```bash
   git clone https://github.com/Madhukumar511/Agentic-Helper.git
   cd Agentic-Helper
   ./setup.sh
   ```

2. **Launch Google Chrome with Remote Debugging**:
   ```bash
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/agent_browser
   ```

---

### 🪟 Windows (PowerShell / Command Prompt)

1. **Clone and 1-Click Setup**:
   ```powershell
   git clone https://github.com/Madhukumar511/Agentic-Helper.git
   cd Agentic-Helper
   .\setup.bat
   ```

2. **1-Click Browser Launch**:
   Double-click `launch_browser_windows.bat`, or run:
   ```powershell
   # Using Google Chrome:
   & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:TEMP\agent_browser"

   # OR using Microsoft Edge:
   & "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="$env:TEMP\agent_browser"
   ```

---

## 🤖 Connecting AI Agents

### 1. Model Context Protocol (MCP) Setup
Agentic-Helper includes a native MCP server (`agentic-helper-mcp`).

#### For Cursor (`~/.cursor/mcp.json` or Workspace `.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "agentic-helper": {
      "command": "agentic-helper-mcp",
      "args": []
    }
  }
}
```

#### For Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "agentic-helper": {
      "command": "/path/to/Agentic-Helper/.venv/bin/agentic-helper-mcp",
      "args": []
    }
  }
}
```

Now Claude or Cursor can natively invoke:
- `extract_questions()`: Inspects current quiz.
- `fill_answer(question_index=0, value="2.0")`: Fills answer.
- `solve_batch(answers={"0": "2.0", "1": 1})`: Fills all answers.
- `submit_assessment(predicted_confidence_pct=95.0)`: Submits assessment safely.
- `solve_diagram(image_path="/path/to/diagram.png")`: Parses spacetime diagrams.

---

### 2. Multi-LMS Python Automation API

```python
from playwright.sync_api import sync_playwright
from quiz_pilot.lms_adapters import get_lms_adapter
from quiz_pilot.attempt_protector import FastAttemptManager

attempt_mgr = FastAttemptManager(min_pass_threshold=80.0)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].pages[0]

    # Auto-detects platform (Coursera, Canvas, Moodle, Blackboard, Google Forms)
    adapter = get_lms_adapter(page)
    questions = adapter.extract_questions()
    print(f"Extracted {len(questions)} questions!")

    # Check previous attempt cache to reuse 100% correct answers
    known = attempt_mgr.get_known_verified_answers("assignment_1")
    
    # Fill answers
    adapter.fill_answer(0, "Answer Option Text")

    # Verify attempt budget before submitting
    allowed, msg = attempt_mgr.verify_attempt_budget(predicted_confidence_pct=90.0)
    if allowed:
        adapter.submit_assessment()
```

---

### 3. Fast Diagram & Distributed Algorithm Solver

```python
from quiz_pilot.diagram_parser import LocalDiagramParser
from quiz_pilot.graph_solvers import LamportVectorClockSolver, MulticastSimulator

# 1. Fast sub-second diagram parsing
parser = LocalDiagramParser()
diagram = parser.parse_spacetime_diagram("path/to/spacetime_diagram.png")
solution = parser.solve_fast_lamport(diagram)
print("Event timestamps:", solution["timestamps"])

# 2. Multicast FIFO & Causal Ordering Simulation
sim = MulticastSimulator(num_processes=4)
res = sim.simulate_causal(
    num_processes=4,
    multicasts=[{"id": "M1", "src": 1}, {"id": "M2", "src": 2}],
    arrivals=[{"msg": "M1", "dst": 0}, {"msg": "M2", "dst": 0}]
)
print("Buffered messages:", res["total_buffered"])
```

---

## ⚡ 3-Attempt Fast Heuristic Strategy & Temporary Cache Law

1. **Attempt 1 (Speed Run)**:
   - Run heuristic and diagram solvers rapidly without manual over-verification.
   - Submit and retrieve LMS feedback.
   - Cache results to temporary `.assessment_cache/<quiz>_attempt_1.md` and `.json`.
2. **Attempt 2 & 3 (Zero-Compute Diff)**:
   - Agent reads `.assessment_cache/<quiz>_attempt_1.md`.
   - All questions marked `✅ CORRECT` are locked in immediately with **zero compute**.
   - Agent solves only the questions marked `❌ WRONG`.
3. **Automatic Purge**:
   - Once score $\ge 80\%$, all temporary cache files and screenshots are purged automatically.

---

## 📁 Repository Structure

```
Agentic-Helper/
├── quiz_pilot/                  # Core engine package
│   ├── attempt_protector.py     # 3-Attempt manager, temporary cache & budget protector
│   ├── diagram_parser.py        # Sub-second OpenCV/NumPy diagram graph parser
│   ├── mcp_server.py            # Model Context Protocol stdio server
│   ├── lms_adapters/            # Multi-LMS drivers
│   │   ├── base_adapter.py      # Abstract LMS interface
│   │   ├── coursera_adapter.py  # Coursera driver
│   │   ├── canvas_adapter.py    # Canvas Instructure driver
│   │   ├── moodle_adapter.py    # Moodle driver
│   │   ├── blackboard_adapter.py# Blackboard Learn driver
│   │   └── google_forms_adapter.py # Google Forms driver
│   ├── graph_solvers.py         # Lamport, Vector clock & Multicast simulators
│   ├── ai_solver.py             # Reasoning engine & prompt builder
│   ├── automation_engine.py     # Playwright automation executor
│   ├── cdp_client.py            # Chrome DevTools Protocol client
│   ├── dom_detector.py          # Universal DOM detection scripts
│   ├── server.py                # FastAPI REST / WebSocket bridge
│   └── hud/                     # In-browser HUD overlay assets
├── tests/                       # Unit tests
│   ├── test_quiz_pilot.py       # Core unit tests
│   ├── test_graph_solvers.py    # Algorithmic solver test suite
│   └── test_new_features.py     # Multi-LMS, diagram parser, and attempt budget tests
├── coursera_extractor.js        # Standalone browser console extraction utility
├── pyproject.toml               # Package build configuration
├── .gitignore                   # Ignore profiles, logs, and temp files
└── README.md                    # Documentation
```

---

## 🧪 Testing

Run full test suite:
```bash
python3 -m unittest discover -s tests
```

---

## 📜 License

MIT License. Designed for academic research, education automation, and AI agent experimentation.
