import os
import tempfile
import pytest
from quiz_pilot.attempt_protector import FastAttemptManager


def test_create_host_packet_partitioning():
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, "quiz_analysis.md")
        mgr = FastAttemptManager(base_cache_dir=tmpdir)

        # Mock initial questions
        questions = [
            {
                "index": 0,
                "prompt": "What is the primary role of a Paxos proposer?",
                "type": "radio",
                "options": ["Propose values", "Accept proposals", "Store logs", "Crash gracefully"]
            },
            {
                "index": 1,
                "prompt": "Which algorithm is used for global snapshot?",
                "type": "radio",
                "options": ["Chandy-Lamport", "Raft", "Bully", "Gossip"]
            },
            {
                "index": 2,
                "prompt": "What is eventual consistency?",
                "type": "radio",
                "options": ["Replicas eventually converge", "Immediate updates", "No updates", "Linear order"]
            }
        ]

        # Simulate Attempt 1: Q0 was correct (Propose values), Q1 was wrong with 'Raft'
        mgr.record_attempt(
            quiz_id="TestQuiz",
            attempt_num=1,
            questions=questions,
            answers={0: 0, 1: 1, 2: 2},  # Q0: opt 0, Q1: opt 1, Q2: opt 2
            feedback={0: True, 1: False, 2: False},
            score_pct=33.3,
            md_path=md_path
        )

        # Now simulate Attempt 2 packet generation:
        # Q0 is LOCKED_CORRECT -> stays with tool in locally_solved
        # Q1 has 1 option eliminated ('Raft') -> still has 3 candidates -> travels in packet
        # Q2 has 1 option eliminated ('No updates') -> still has 3 candidates -> travels in packet
        packet_res = mgr.create_host_packet(questions=questions, quiz_id="TestQuiz", md_path=md_path)

        assert packet_res["total_questions"] == 3
        assert packet_res["locally_solved_count"] == 1
        assert packet_res["unresolved_count"] == 2
        assert packet_res["status"] == "READY_FOR_HOST"

        # Check locally solved
        assert "0" in packet_res["locally_solved"]
        assert packet_res["locally_solved"]["0"] == 0

        # Check packet contents
        packet = packet_res["packet"]
        assert len(packet) == 2
        q1_item = next(p for p in packet if p["index"] == 1)
        assert q1_item["q_num"] == 2
        assert "Raft" in q1_item["eliminated_texts"]
        # In options, 'Raft' should have eliminated=True
        raft_opt = next(opt for opt in q1_item["options"] if opt["text"] == "Raft")
        assert raft_opt["eliminated"] is True


def test_create_host_packet_deterministic_forced_candidate():
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, "quiz_analysis.md")
        mgr = FastAttemptManager(base_cache_dir=tmpdir)

        # A question with 2 options (True/False)
        questions = [
            {
                "index": 0,
                "prompt": "Is Lamport timestamp causal?",
                "type": "radio",
                "options": ["True", "False"]
            }
        ]

        # Attempt 1: Submitted 'True' (opt 0) and it was marked WRONG (False)
        mgr.record_attempt(
            quiz_id="TFQuiz",
            attempt_num=1,
            questions=questions,
            answers={0: 0},
            feedback={0: False},
            score_pct=0.0,
            md_path=md_path
        )

        # On retry: Since 'True' is eliminated, 'False' is the only remaining candidate.
        # It should be resolved locally with zero compute, leaving packet empty!
        packet_res = mgr.create_host_packet(questions=questions, quiz_id="TFQuiz", md_path=md_path)

        assert packet_res["locally_solved_count"] == 1
        assert packet_res["unresolved_count"] == 0
        assert packet_res["status"] == "ALL_SOLVED_LOCALLY"
        assert packet_res["locally_solved"]["0"] == 1  # Selected 'False'


def test_merge_host_packet_answers():
    mgr = FastAttemptManager()

    locally_solved = {"0": 1, "1": 3}
    host_answers = {"2": 0, "q3": 2, "Q4": 1}

    merged = mgr.merge_host_packet_answers(locally_solved, host_answers)

    assert merged[0] == 1
    assert merged[1] == 3
    assert merged[2] == 0
    assert merged[3] == 2
    assert merged[4] == 1
