"""Per-quiz purge policy (2026-11-03).

The agent must never wipe the whole .assessment_cache after a pass:
purge_all() erases every quiz's verified memory AND all Host-Packet
state (.assessment_cache/packets/), which a multi-quiz or
specialization run depends on. The settled policy is:
- on a pass, purge ONLY the finished quiz via purge_cache(quiz_id);
- a full wipe is manual-only (the user running `agentic-helper clean`).
"""
import os
from pathlib import Path

from quiz_pilot.attempt_protector import FastAttemptManager

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTION_FILES = [
    ".agents/skills/agentic-helper/SKILL.md",
    ".gemini/skills/agentic-helper/SKILL.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
]


def test_purge_cache_removes_only_that_quiz(tmp_path):
    cache = tmp_path / "cache"
    mgr = FastAttemptManager(base_cache_dir=str(cache))
    quiz_a = "Quiz A [course-a]"
    quiz_b = "Quiz B [course-b]"
    a_json = cache / f"{quiz_a}_attempt_1.json"
    a_md = cache / f"{quiz_a}_analysis.md"
    b_json = cache / f"{quiz_b}_attempt_1.json"
    packets = cache / "packets"
    packets.mkdir(parents=True, exist_ok=True)
    pkt = packets / "pkt-abc123.json"
    for p in (a_json, a_md, b_json, pkt):
        p.write_text("{}", encoding="utf-8")

    mgr.purge_cache(quiz_a)

    assert not a_json.exists()
    assert not a_md.exists()
    # Other quizzes' memory and Host-Packet state survive untouched.
    assert b_json.exists()
    assert pkt.exists()
    assert cache.exists()


def test_instruction_files_direct_per_quiz_purge_only():
    for rel in INSTRUCTION_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "purge_cache(quiz_id)" in text, f"{rel}: missing per-quiz purge directive"
        for line in text.splitlines():
            if "purge_all" in line:
                assert ("NEVER" in line) or ("Never" in line), (
                    f"{rel}: purge_all mentioned without a prohibition: {line.strip()[:100]}"
                )
