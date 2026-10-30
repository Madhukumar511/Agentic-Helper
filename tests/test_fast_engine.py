"""
Unit tests for Autonomous SyllabusCrawler, Direct REST API, and CourseOrchestrator.
"""

import pytest
from quiz_pilot.syllabus_crawler import SyllabusCrawler
from quiz_pilot.direct_api_solver import CourseraDirectAPI
from quiz_pilot.course_orchestrator import CourseOrchestrator
from quiz_pilot.mcp_server import TOOLS

def test_syllabus_crawler_missing_page_raises():
    crawler = SyllabusCrawler(page=None)
    with pytest.raises(ValueError, match="No active browser page attached"):
        crawler.crawl_course_assignments("https://www.coursera.org/learn/cloud-networking")

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

def test_mcp_fast_tools_registered():
    tool_names = [t["name"] for t in TOOLS]
    assert "crawl_syllabus" in tool_names
    assert "auto_complete_entire_course" in tool_names
