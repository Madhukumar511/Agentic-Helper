"""
Unit tests for PeerReviewManager and Peer Assignment Solvers.
"""

import pytest
from quiz_pilot.peer_review_solver import PeerReviewManager, DEFAULT_PEER_FEEDBACKS
from quiz_pilot.mcp_server import TOOLS

def test_peer_task_detection():
    prm = PeerReviewManager()
    
    # Test submission URL
    info_sub = prm.detect_peer_task(
        url="https://www.coursera.org/learn/cloud-computing-project/peer/5pBeh/task-1-submission",
        text="Peer-graded Assignment: Task 1 Submission"
    )
    assert info_sub["is_peer"] is True
    assert info_sub["mode"] == "submission"

    # Test review URL with remaining reviews
    info_rev = prm.detect_peer_task(
        url="https://www.coursera.org/learn/cloud-computing-project/peer/5pBeh/task-1-submission/give-feedback",
        text="Review fellow learners. Reviews 4 left to complete."
    )
    assert info_rev["is_peer"] is True
    assert info_rev["mode"] == "review"
    assert info_rev["reviews_left"] == 4

    # Test non-peer quiz URL
    info_quiz = prm.detect_peer_task(
        url="https://www.coursera.org/learn/cloud-networking/exam/abc/quiz",
        text="Cloud Intro Quiz Question 1"
    )
    assert info_quiz["is_peer"] is False

def test_peer_submission_missing_file_raises():
    prm = PeerReviewManager(page=None)
    with pytest.raises(ValueError, match="No active browser page attached"):
        prm.submit_peer_assignment(
            title="Test Project",
            report_pdf_path="/nonexistent/path/report.pdf"
        )

def test_default_feedbacks_pool():
    assert len(DEFAULT_PEER_FEEDBACKS) >= 3
    for fb in DEFAULT_PEER_FEEDBACKS:
        assert len(fb) > 20

def test_mcp_peer_tools_registered():
    tool_names = [t["name"] for t in TOOLS]
    assert "submit_peer_assignment" in tool_names
    assert "complete_peer_reviews" in tool_names
    assert "auto_solve_current_assignment" in tool_names
