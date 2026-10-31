"""
Unit tests for Autonomous SyllabusCrawler, Direct REST API, and CourseOrchestrator.
"""

import os
import pytest
from quiz_pilot.syllabus_crawler import SyllabusCrawler
from quiz_pilot.direct_api_solver import CourseraDirectAPI
from quiz_pilot.course_orchestrator import CourseOrchestrator
from quiz_pilot.mcp_server import TOOLS

@pytest.mark.anyio
async def test_syllabus_crawler_missing_page_raises():
    crawler = SyllabusCrawler(page=None)
    with pytest.raises(ValueError, match="No active browser page attached"):
        await crawler.crawl_course_assignments("https://www.coursera.org/learn/cloud-networking")
    with pytest.raises(ValueError, match="No active browser page attached"):
        await crawler.crawl_specialization_courses("https://www.coursera.org/specializations/cloud-computing")

def test_direct_api_headers():
    api = CourseraDirectAPI(cauth_token="TEST_CAUTH_VAL", csrf_token="TEST_CSRF_VAL")
    headers = api._get_headers()
    assert "Cookie" in headers
    assert "CAUTH=TEST_CAUTH_VAL" in headers["Cookie"]
    assert "CSRF3-Token=TEST_CSRF_VAL" in headers["Cookie"]
    assert headers["X-CSRF3-Token"] == "TEST_CSRF_VAL"

def test_orchestrator_initialization():
    orch = CourseOrchestrator(cdp_url="http://127.0.0.1:9222", max_concurrency=6)
    assert orch.max_concurrency == 6
    assert orch.cdp_url == "http://127.0.0.1:9222"

def test_smart_multiworker_scheduler_init():
    from quiz_pilot.tab_scheduler import AsyncTabScheduler
    scheduler = AsyncTabScheduler(cdp_url="http://127.0.0.1:9222", max_concurrency=5)
    assert scheduler.max_concurrency == 5
    assert hasattr(scheduler, "smart_multiworker")

def test_mcp_fast_tools_registered():
    tool_names = [t["name"] for t in TOOLS]
    assert "crawl_syllabus" in tool_names
    assert "auto_complete_entire_course" in tool_names
    assert "open_and_solve_parallel" in tool_names
    assert "auto_complete_specialization" in tool_names
    assert "record_quiz_analysis" in tool_names
    assert "get_retry_answers" in tool_names


def test_browser_launcher_candidates_and_navigation(monkeypatch):
    from quiz_pilot.browser_launcher import get_browser_candidates, open_url_in_running_browser, ensure_browser

    candidates = get_browser_candidates()
    assert isinstance(candidates, list)

    # When port is not open, open_url_in_running_browser safely returns False
    res = open_url_in_running_browser("https://www.coursera.org", port=59999)
    assert res is False


def test_quiz_analysis_markdown_memory_and_option_elimination(tmp_path):
    from quiz_pilot.attempt_protector import FastAttemptManager

    mgr = FastAttemptManager(base_cache_dir=str(tmp_path / "cache"), min_pass_threshold=80.0)
    md_test_path = str(tmp_path / "quiz_analysis.md")

    # Attempt 1: 2 questions
    # Q0: "What is ZooKeeper's role in Giraph?" -> Option 0: "Coordination" (Incorrect)
    # Q1: "What is PUE?" -> Option 1: "Total Facility Energy / IT Equipment Energy" (Correct)
    questions_attempt1 = [
        {
            "index": 0,
            "prompt": "What is ZooKeeper's role in Giraph?",
            "type": "radio",
            "options": ["Responsible for coordination", "Responsible for the state of computation", "Responsible for vertices"]
        },
        {
            "index": 1,
            "prompt": "What is PUE?",
            "type": "radio",
            "options": ["IT Energy / Total Energy", "Total Facility Energy / IT Equipment Energy", "Fixed constant"]
        }
    ]
    answers_attempt1 = {0: 0, 1: 1} # Q0 picked "Responsible for coordination", Q1 picked "Total Facility..."
    feedback_attempt1 = {0: False, 1: True} # Q0 wrong, Q1 correct

    md_content = mgr.record_attempt(
        quiz_id="cloud_computing_quiz4",
        attempt_num=1,
        questions=questions_attempt1,
        answers=answers_attempt1,
        feedback=feedback_attempt1,
        score_pct=50.0,
        md_path=md_test_path
    )

    assert "NEEDS_RETRY" in md_content
    assert "LOCKED_CORRECT" in md_content
    assert "Responsible for coordination" in md_content
    assert "Total Facility Energy / IT Equipment Energy" in md_content
    assert os.path.exists(md_test_path)

    # Attempt 2: Coursera SHUFFLES the options randomly!
    # For Q0: "Responsible for coordination" is now at index 2!
    # For Q1: "Total Facility..." is now at index 0!
    questions_attempt2 = [
        {
            "index": 0,
            "prompt": "What is ZooKeeper's role in Giraph?",
            "type": "radio",
            "options": ["Responsible for the state of computation", "Responsible for vertices", "Responsible for coordination"]
        },
        {
            "index": 1,
            "prompt": "What is PUE?",
            "type": "radio",
            "options": ["Total Facility Energy / IT Equipment Energy", "Fixed constant", "IT Energy / Total Energy"]
        }
    ]

    retry_answers = mgr.get_retry_answers(questions_attempt2, md_path=md_test_path, quiz_id="cloud_computing_quiz4")

    # Q1 must match verified option text "Total Facility..." -> which is now at index 0!
    assert retry_answers[1] == 0

    # Q0 was failed with "Responsible for coordination" (now index 2).
    # Retry answer MUST NEVER be index 2! It must be index 0 or 1!
    assert retry_answers[0] != 2
    assert retry_answers[0] in (0, 1)

    # Parse back from markdown into clean manager to verify load_quiz_analysis
    mgr2 = FastAttemptManager(base_cache_dir=str(tmp_path / "cache2"), min_pass_threshold=80.0)
    parsed_mem = mgr2.load_quiz_analysis(md_path=md_test_path)
    assert len(parsed_mem) > 0
    q_data = next(iter(parsed_mem.values()))["questions"]
    assert any("pue" in p for p in q_data.keys())
