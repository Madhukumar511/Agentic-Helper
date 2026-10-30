# Agentic-Helper 🚀

> **Universal LMS & Web Assessment Automation Engine for Autonomous AI Agents**  
> Connect any AI coding agent (Claude Code, Antigravity, OpenAI Codex, custom LLM agents) to your live browser session to reliably inspect, reason, and solve quizzes on Coursera, Canvas, Moodle, Blackboard, edX, and custom web assessments.

---

## 🌟 Key Features

- **🌐 Zero-API Browser Session Pairing**: No paid external API keys needed. Connects directly to your everyday browser via Chrome DevTools Protocol (CDP).
- **🛡️ Anti-Prompt-Injection DOM Extractor**: Strips hidden prompt injection honey-pots and watermarks embedded inside assessment HTML before passing clean question data to reasoning agents.
- **🎯 Robust Leaf-Group DOM Automation**: Uses leaf-node bounding tree traversal to interact with radio buttons, checkboxes, numeric boxes, and text fields without hitting overlay interception errors.
- **🧠 Advanced Graph & Distributed Systems Solvers**: Built-in simulation engines for:
  - **Lamport & Vector Clocks**: Computes logical timestamps and concurrency across distributed process DAGs.
  - **Multicast Ordering**: Simulates FIFO and Causal multicast message buffering and sequence vectors.
  - **Chandy-Lamport Snapshots**: Solves process snapshot and in-flight channel state problems.
- **🔌 Multi-Agent Bridge Server**: Built-in FastAPI / WebSocket bridge so any agent, script, or workflow can call high-level actions (`/extract`, `/answer`, `/submit`).

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

2. **Create virtual environment and install**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   playwright install chromium
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
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   playwright install chromium
   ```

2. **Launch Google Chrome with Remote Debugging**:
   ```bash
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=/tmp/agent_browser
   ```

---

### 🪟 Windows (PowerShell / Command Prompt)

1. **Clone and setup**:
   ```powershell
   git clone https://github.com/Madhukumar511/Agentic-Helper.git
   cd Agentic-Helper
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -e .
   playwright install chromium
   ```

2. **Launch Google Chrome or Edge with Remote Debugging**:
   ```powershell
   # Using Google Chrome:
   & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\tmp\agent_browser"

   # OR using Microsoft Edge:
   & "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\tmp\agent_browser"
   ```

---

## 🤖 How AI Agents Can Use Agentic-Helper

Agentic-Helper is designed from the ground up for agentic pair-programming and tool-augmented LLMs.

### Option 1: Connecting via Bridge Server (Universal REST API)

Launch the bridge server in background:
```bash
agentic-helper server --port 8000
```

Any AI Agent (e.g. Claude, Antigravity, OpenAI Codex, LangChain, AutoGen) can make HTTP calls:

- **Extract all questions from active tab**:
  ```bash
  curl -X GET http://127.0.0.1:8000/api/extract
  ```
  Returns a clean JSON array of questions, options, input types (`radio`, `checkbox`, `number`, `text`), and diagram image URLs.

- **Select answer on page**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/select \
       -H "Content-Type: application/json" \
       -d '{"question_index": 0, "option_index": 2}'
  ```

- **Fill numeric or text input**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/fill \
       -H "Content-Type: application/json" \
       -d '{"question_index": 3, "value": "42"}'
  ```

- **Submit assessment**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/submit
  ```

---

### Option 2: Python Script / Playwright Direct Automation

AI Agents can write simple Python automation scripts directly importing `quiz_pilot`:

```python
from playwright.sync_api import sync_playwright
from quiz_pilot.dom_detector import DOMDetector

with sync_playwright() as p:
    # Connect to user's logged-in Chrome
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].pages[0]

    # Extract all questions cleanly
    questions = DOMDetector.extract_questions(page)
    print(f"Extracted {len(questions)} questions!")

    for q in questions:
        print(f"Q{q['index']}: {q['prompt'][:80]}... Type: {q['type']}")
```

---

### Option 3: Distributed Systems & Graph Problem Solvers

For complex algorithmic questions (e.g., Computer Science / Cloud Computing / Distributed Systems):

```python
from quiz_pilot.graph_solvers import LamportVectorClockSolver, MulticastSimulator

# 1. Lamport & Vector Clock Solver
solver = LamportVectorClockSolver(num_processes=3)
solver.add_message("M1", src=0, dst=1)
solver.add_process_trace(0, [("send", "M1")])
solver.add_process_trace(1, [("recv", "M1")])

result = solver.solve()
print("Lamport timestamp of receive:", result["events"]["P1_recv_M1"]["lamport"])
print("Is concurrent?", solver.is_concurrent("P0_send_M1", "P1_recv_M1"))

# 2. Multicast FIFO & Causal Ordering Simulator
sim = MulticastSimulator(num_processes=4)
fifo_res = sim.simulate_fifo(
    num_processes=4,
    multicasts=[{"id": "M1", "src": 1}, {"id": "M2", "src": 1}],
    arrivals=[{"msg": "M2", "dst": 3}, {"msg": "M1", "dst": 3}]
)
print("Multicasts buffered under FIFO:", fifo_res["total_buffered"])
```

---

## 📁 Repository Structure

```
Agentic-Helper/
├── quiz_pilot/                  # Core engine package
│   ├── ai_solver.py             # Reasoning parser and prompt builder
│   ├── automation_engine.py     # Playwright automation executor
│   ├── cdp_client.py            # Chrome DevTools Protocol client
│   ├── cli.py                   # Command-line interface entrypoint
│   ├── dom_detector.py          # Universal DOM detection scripts
│   ├── graph_solvers.py         # Lamport, Vector clock & Multicast solvers
│   ├── server.py                # FastAPI bridge server
│   └── hud/                     # In-browser HUD overlay assets
├── tests/                       # Unit tests
│   ├── test_quiz_pilot.py       # Core test suite
│   └── test_graph_solvers.py    # Algorithmic solver test suite
├── coursera_extractor.js        # Standalone browser console extraction utility
├── pyproject.toml               # Package build configuration
├── .gitignore                   # Ignore profiles, logs, and temp files
└── README.md                    # Documentation
```

---

## 🧪 Testing

Run test suite:
```bash
python3 -m unittest discover -s tests
```

---

## 📜 License

MIT License. Designed for academic research, education automation, and AI agent experimentation.
