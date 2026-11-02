"""
Host-Packet mode behaviour tests.

The packet contract, proven by outcomes (not string presence):
- prepare locks ONLY feedback-verified answers, rematched by option TEXT
  so shuffled options stay correct;
- questions with a previously-wrong answer travel again, carrying the
  eliminated option indices as hints (never as auto-answers);
- merging validates host answers, never lets the host override a locked
  answer, and reports coverage honestly for the submit gate;
- after a failed attempt is recorded, the next packet is a DELTA: newly
  correct questions lock, only still-wrong questions travel;
- packet state survives across PacketManager instances (separate tool
  calls / server processes) without the questions re-crossing the host.
"""
import pytest

from quiz_pilot.attempt_protector import FastAttemptManager
from quiz_pilot.packet_mode import PacketManager

QUIZ = "Module 1 Quiz [course-1]"


def make_questions():
    return [
        {"index": 0, "qNum": 1, "type": "radio", "prompt": "What is 2 + 2?",
         "options": ["3", "4", "5"], "images": [], "diagram_meta": [{"tag": "img"}]},
        {"index": 1, "qNum": 2, "type": "radio", "prompt": "Capital of France?",
         "options": ["London", "Paris", "Rome"], "images": [], "diagram_meta": []},
        {"index": 2, "qNum": 3, "type": "radio", "prompt": "Colour of the sky?",
         "options": ["Green", "Red", "Blue"], "images": [], "diagram_meta": []},
        {"index": 3, "qNum": 4, "type": "radio", "prompt": "Chemical symbol for gold?",
         "options": ["Ag", "Fe", "Au"], "images": [], "diagram_meta": []},
    ]


@pytest.fixture()
def mgr(tmp_path):
    return FastAttemptManager(base_cache_dir=str(tmp_path / "cache"))


@pytest.fixture()
def pm(mgr):
    return PacketManager(mgr)


def record_first_attempt(mgr, tmp_path):
    qs = make_questions()
    mgr.record_attempt(
        quiz_id=QUIZ, attempt_num=1, questions=qs,
        answers={0: 1, 1: 0, 2: 2},               # Q0 right, Q1 wrong, Q2 right; Q3 unseen
        feedback={0: True, 1: False, 2: True},
        score_pct=66.7, md_path=str(tmp_path / "quiz_analysis.md"),
    )


def test_prepare_locks_verified_and_marks_eliminated(pm, mgr, tmp_path):
    record_first_attempt(mgr, tmp_path)
    qs = make_questions()
    qs[0] = dict(qs[0], options=["5", "4", "3"])  # shuffled: verified "4" now at index 1
    packet = pm.build_packet(QUIZ, qs, md_path=str(tmp_path / "quiz_analysis.md"))

    assert packet["total"] == 4
    assert packet["known_count"] == 2             # Q0 + Q2 verified
    assert packet["unknown_count"] == 2           # Q1 (was wrong) + Q3 (new)
    assert packet["ready"] is False

    state = pm.load_state(packet["packet_id"])
    assert state["known"] == {"0": 1, "2": 2}     # "4" rematched by text after shuffle

    items = {item["i"]: item for item in packet["questions"]}
    assert set(items) == {1, 3}
    assert items[1]["e"] == [0]                   # "London" was marked wrong -> eliminated hint
    assert items[1]["o"] == ["London", "Paris", "Rome"]
    assert "diagram_meta" not in items[1] and "qNum" not in items[1]  # no payload noise


def test_merge_validates_and_never_overrides_locked(pm, mgr, tmp_path):
    record_first_attempt(mgr, tmp_path)
    packet = pm.build_packet(QUIZ, make_questions(), md_path=str(tmp_path / "quiz_analysis.md"))
    state = pm.load_state(packet["packet_id"])

    merged = pm.merge_answers(state, {
        0: 0,          # tries to override the locked Q0 -> ignored
        1: "Paris",    # option TEXT form -> resolves to index 1
        3: 9,          # out of range -> error, not filled
    })
    assert merged["answers"][0] == 1              # locked value kept
    assert merged["answers"][1] == 1
    assert 3 not in merged["answers"]
    assert merged["ignored_locked"] == [0]
    assert merged["errors"] and merged["remaining_unknown"] == [3]
    assert merged["coverage_pct"] == 75.0         # below the 80% floor: handler must not submit


def test_merge_accepts_compact_pair_list(pm, mgr, tmp_path):
    record_first_attempt(mgr, tmp_path)
    packet = pm.build_packet(QUIZ, make_questions(), md_path=str(tmp_path / "quiz_analysis.md"))
    state = pm.load_state(packet["packet_id"])
    merged = pm.merge_answers(state, [[1, 1], [3, 2]])
    assert merged["answers"][1] == 1 and merged["answers"][3] == 2
    assert merged["coverage_pct"] == 100.0


def test_delta_packet_after_failed_attempt(pm, mgr, tmp_path):
    record_first_attempt(mgr, tmp_path)
    qs = make_questions()
    # Attempt 2: Q1 now correct, Q3 answered wrong ("Ag"), rest as locked.
    mgr.record_attempt(
        quiz_id=QUIZ, attempt_num=2, questions=qs,
        answers={0: 1, 1: 1, 2: 2, 3: 0},
        feedback={0: True, 1: True, 2: True, 3: False},
        score_pct=75.0, md_path=str(tmp_path / "quiz_analysis.md"),
    )
    packet = pm.build_packet(QUIZ, qs, md_path=str(tmp_path / "quiz_analysis.md"))
    assert packet["known_count"] == 3
    assert packet["unknown_count"] == 1
    item = packet["questions"][0]
    assert item["i"] == 3 and item["e"] == [0]    # only Q3 travels, "Ag" eliminated


def test_state_survives_across_manager_instances(mgr, tmp_path):
    pm1 = PacketManager(mgr)
    packet = pm1.build_packet(QUIZ, make_questions(), md_path=str(tmp_path / "quiz_analysis.md"))
    pm2 = PacketManager(mgr)  # a later tool call / new server process
    state = pm2.load_state(packet["packet_id"])
    assert state is not None and state["quiz_id"] == QUIZ and state["total"] == 4
    merged = pm2.merge_answers(state, {0: 1, 1: 1, 2: 2, 3: 2})
    assert merged["coverage_pct"] == 100.0 and not merged["errors"]


def test_verified_reuse_crosses_quizzes_but_elimination_does_not(mgr, tmp_path):
    qs = make_questions()
    mgr.record_attempt(
        quiz_id="Other Quiz [other]", attempt_num=1, questions=qs,
        answers={0: 1, 1: 0}, feedback={0: True, 1: False},
        score_pct=50.0, md_path=str(tmp_path / "quiz_analysis.md"),
    )
    pm = PacketManager(mgr)
    packet = pm.build_packet("Brand New Quiz [new]", qs, md_path=str(tmp_path / "quiz_analysis.md"))
    state = pm.load_state(packet["packet_id"])
    assert state["known"].get("0") == 1           # verified answer reused
    items = {item["i"]: item for item in packet["questions"]}
    assert 1 in items and "e" not in items[1]     # other quiz's elimination NOT imported


def test_packet_tools_registered():
    from quiz_pilot.mcp_server import TOOLS
    names = {t["name"] for t in TOOLS}
    assert "prepare_packet" in names and "apply_packet" in names
