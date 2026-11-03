"""No-shell-launch guard (2026-11-03).

Live episode: the host agent tried to open Chrome via a nested
PowerShell -> cmd -> launch_browser_windows.bat command; the user's
antivirus blocked it as a "malicious command line", so the browser
never opened automatically. The instruction files must (a) carry the
Browser Launch Rule (MCP launch_browser tool first, python -m fallback)
and (b) never again present a .bat invocation or a raw shell exe launch
as an agent action.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTION_FILES = [
    ".agents/skills/agentic-helper/SKILL.md",
    ".gemini/skills/agentic-helper/SKILL.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
]


def test_instruction_files_ban_shell_chain_launches():
    for rel in INSTRUCTION_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "Browser Launch Rule (Windows)" in text, f"{rel}: launch rule missing"
        for line in text.splitlines():
            if "launch_browser_windows" in line:
                # The only allowed mention is inside the prohibition.
                assert ("NEVER" in line) or ("double-click" in line), (
                    f"{rel}: .bat presented as an agent action: {line.strip()[:100]}"
                )
            assert "Start-Process" not in line, f"{rel}: raw PowerShell launch remains"
