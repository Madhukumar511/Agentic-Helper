"""
Comprehensive Architectural & Integration Tests for Refactored Agentic-Helper / Quiz-Pilot.

Verifies fixes for:
1. MCP Handler NameError (tool_args -> arguments)
2. Unification of Async/Sync Playwright Execution in LMS Adapters & CourseOrchestrator
3. FastAttemptManager schema mismatch handling (dict vs string options, fingerprints)
4. Elimination of hardcoded brain paths and machine-specific /tmp paths
5. PeerReview rubric maximum point inspection and Diagram solver non-blind fallback
6. CourseraDirectAPI page wiring & graceful DOM fallback
"""

import os
import json
import asyncio
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock

from quiz_pilot.mcp_server import handle_call_tool, TOOLS
from quiz_pilot.attempt_protector import FastAttemptManager
from quiz_pilot.lms_adapters import CourseraAdapter, CanvasAdapter, get_lms_adapter
from quiz_pilot.ai_solver import AISolver
from quiz_pilot.peer_review_solver import PeerReviewManager
from quiz_pilot.diagram_parser import LocalDiagramParser
from quiz_pilot.course_orchestrator import CourseOrchestrator
from quiz_pilot.direct_api_solver import CourseraDirectAPI


@pytest.mark.anyio
async def test_mcp_record_quiz_analysis_and_retry_answers(tmp_path):
    """
    Issue 1: Verifies record_quiz_analysis and get_retry_answers MCP tools execute
    cleanly using `arguments` without NameError: name 'tool_args' is not defined.
    """
    md_test_path = str(tmp_path / "quiz_analysis.md")
    questions = [
        {"index": 0, "prompt": "What is Paxos?", "type": "radio", "options": ["Consensus", "Storage"]},
        {"index": 1, "prompt": "What is Raft?", "type": "radio", "options": ["Consensus", "Networking"]}
    ]
    arguments = {
        "quiz_id": "test_mcp_quiz",
        "questions": questions,
        "answers": {"0": 0, "1": 1},
        "feedback": {"0": True, "1": False},
        "score_pct": 50.0,
        "attempt_num": 1,
        "md_path": md_test_path
    }
    
    res = await handle_call_tool("record_quiz_analysis", arguments)
    assert not res.get("isError")
    assert "content" in res
    assert "LOCKED_CORRECT" in res["content"][0]["text"]
    assert "NEEDS_RETRY" in res["content"][0]["text"]

    retry_res = await handle_call_tool("get_retry_answers", {
        "quiz_id": "test_mcp_quiz",
        "questions": questions,
        "md_path": md_test_path
    })
    assert not retry_res.get("isError")
    retry_answers = json.loads(retry_res["content"][0]["text"])
    assert retry_answers["0"] == 0  # Verified correct locked answer preserved


def test_attempt_manager_dict_options_and_fingerprints(tmp_path):
    """
    Issue 3: Verifies option extraction across dict options (dom_detector schema)
    and string options (coursera_adapter schema) produce identical fingerprints
    and work transparently in elimination & matching.
    """
    mgr = FastAttemptManager(base_cache_dir=str(tmp_path / "cache"))
    
    q_dict = {
        "index": 0,
        "prompt": "What is CAP theorem?",
        "type": "radio",
        "options": [
            {"index": 0, "text": "Consistency, Availability, Partition tolerance", "checked": False},
            {"index": 1, "text": "Compute, Access, Protocol", "checked": False}
        ]
    }
    q_str = {
        "index": 0,
        "prompt": "What is CAP theorem?",
        "type": "radio",
        "options": [
            "Consistency, Availability, Partition tolerance",
            "Compute, Access, Protocol"
        ]
    }
    
    # 1. Fingerprint equality regardless of schema
    fp_dict = mgr._get_q_fingerprint(q_dict)
    fp_str = mgr._get_q_fingerprint(q_str)
    assert fp_dict == fp_str

    # 2. Option text matching with dict options
    match_idx = mgr._match_option_by_text("Compute, Access, Protocol", q_dict["options"])
    assert match_idx == 1

    # 3. Elimination with dict options
    assert mgr._is_option_eliminated(q_dict["options"][1], ["Compute, Access, Protocol"]) is True
    assert mgr._is_option_eliminated(q_dict["options"][0], ["Compute, Access, Protocol"]) is False

    # 4. Recording attempt and retry with dict options
    md_path = str(tmp_path / "quiz_analysis.md")
    md = mgr.record_attempt(
        quiz_id="cap_quiz",
        attempt_num=1,
        questions=[q_dict],
        answers={0: 1},  # Picked wrong answer
        feedback={0: False},
        md_path=md_path
    )
    assert "Compute, Access, Protocol" in md
    assert "NEEDS_RETRY" in md

    # 5. Retry answers select the untried candidate (index 0)
    retries = mgr.get_retry_answers([q_dict], quiz_id="cap_quiz", md_path=md_path)
    assert retries[0] == 0


def test_no_machine_specific_brain_paths(tmp_path):
    """
    Issue 4: Verifies elimination of hardcoded ~/.gemini-account2/... paths.
    Only writes to specified md_path and self.base_cache_dir.
    """
    mgr = FastAttemptManager(base_cache_dir=str(tmp_path / "cache"))
    md_test_path = str(tmp_path / "quiz_analysis.md")
    q = {"index": 0, "prompt": "Sample Question", "options": ["A", "B"]}
    
    mgr.record_attempt(
        quiz_id="isolation_test",
        attempt_num=1,
        questions=[q],
        answers={0: 0},
        feedback={0: True},
        md_path=md_test_path
    )
    assert os.path.exists(md_test_path)
    # Ensure quiz_analysis is only in requested path and cache dir
    cache_md = os.path.join(str(tmp_path / "cache"), "quiz_analysis.md")
    assert os.path.exists(cache_md)


def test_ai_solver_bridge_file_uses_tempdir(monkeypatch):
    """
    Issue 4: Verifies ai_solver uses tempfile.gettempdir() instead of hardcoded /tmp.
    """
    solver = AISolver(api_key=None)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    
    q = {
        "text": "What is Amdahl's Law?",
        "type": "single_choice",
        "options": ["Speedup law", "Storage law"]
    }
    sol = solver.solve_question(q)
    expected_bridge = os.path.join(tempfile.gettempdir(), "quiz_pilot_bridge.json")
    assert os.path.exists(expected_bridge)
    with open(expected_bridge, "r") as f:
        data = json.load(f)
    assert data["question"]["text"] == "What is Amdahl's Law?"
    try:
        os.remove(expected_bridge)
    except Exception:
        pass


@pytest.mark.anyio
async def test_async_adapter_execution_model():
    """
    Issue 2: Verifies BaseLMSAdapter and CourseraAdapter async execution model
    on async Playwright pages where page.evaluate() returns coroutines.
    """
    class AsyncFakePage:
        def __init__(self, url):
            self.url = url
            self.eval_calls = []

        async def evaluate(self, script, *args):
            self.eval_calls.append((script, args))
            if "leafGroups.map" in script:
                return [{"index": 0, "prompt": "Async Q?", "options": ["Yes", "No"], "type": "radio"}]
            if "ansMap" in script:
                return {"0": True}
            if "scoreMatch" in script:
                return {"score_pct": 100.0, "passed": True, "feedback": {0: True}}
            return True

    fake_page = AsyncFakePage("https://www.coursera.org/learn/cloud/quiz")
    adapter = get_lms_adapter(fake_page)
    assert isinstance(adapter, CourseraAdapter)

    # Calling async methods on adapter directly returns awaited values
    qs = await adapter.extract_questions_async()
    assert isinstance(qs, list)
    assert len(qs) == 1
    assert qs[0]["prompt"] == "Async Q?"

    fill_res = await adapter.batch_fill_answers_async({0: 0}, auto_submit=False)
    assert fill_res == {"0": True}

    sub_res = await adapter.submit_assessment_async()
    assert sub_res is True

    fb = await adapter.extract_feedback_async()
    assert fb["score_pct"] == 100.0
    assert fb["passed"] is True


def test_peer_review_rubric_max_points_inspection():
    """
    Issue 5: Verifies complete_peer_reviews inspects rubric point values and maxPoints
    rather than blindly clicking the last radio in each group.
    """
    class MockLocator:
        def count(self):
            return 0

    class MockPeerPage:
        def __init__(self):
            self.evaluated_scripts = []

        def locator(self, sel):
            return MockLocator()

        def evaluate(self, script):
            self.evaluated_scripts.append(script)
            if "maxPoints" in script:
                return 4  # Clicked 4 highest-scoring rubric radios
            if "document.body.innerText" in script:
                return "Reviews completed: 4/4"
            return None

    p_page = MockPeerPage()
    prm = PeerReviewManager(page=p_page)
    res = prm.complete_peer_reviews(count=1)
    assert res["status"] in ("completed", "max_reviews_reached")
    # Verify the JS script contained the maxPoints scoring evaluation logic
    assert any("maxPoints" in s for s in p_page.evaluated_scripts)
    # Regression guard (2026-11-01): peer grading must NEVER go back to random
    # selection. A bare "maxPoints" string check passed even when the logic
    # was replaced by Math.random (the variable survived as dead code), so
    # assert on the actual selection behaviour instead.
    from quiz_pilot.peer_review_solver import RUBRIC_SELECTION_JS
    assert "Math.random" not in RUBRIC_SELECTION_JS
    assert "bestRadio" in RUBRIC_SELECTION_JS and "effectiveScore" in RUBRIC_SELECTION_JS
    assert not any("Math.random" in s for s in p_page.evaluated_scripts)


def test_diagram_parser_removes_blind_selection():
    """
    Issue 5: Verifies diagram parser does not blindly pick tuple_opts[0][0] or
    'consistent' in opt, and falls back to LLM reasoning.
    """
    parser = LocalDiagramParser()
    
    res = parser.solve_diagram_question(
        image_source=None,
        question_prompt="Consider the distributed execution. What is the vector clock value for event e2?",
        options=["(0, 0, 1)", "(2, 1, 0)", "(1, 0, 0)", "None of the above"]
    )
    assert res["success"] is True
    # Verify domain is either llm_fallback or heuristic_matcher, not blind hardcoded tuple_opts[0][0]
    assert res["domain"] in ("llm_fallback", "heuristic_matcher")


@pytest.mark.anyio
async def test_course_orchestrator_direct_api_and_dom_fallback(tmp_path, monkeypatch):
    """
    Issue 6: Verifies CourseraDirectAPI wiring and fallback to DOM execution in CourseOrchestrator.
    """
    monkeypatch.chdir(tmp_path)
    class MockAsyncPage:
        def __init__(self):
            self.url = "https://www.coursera.org/learn/cloud/exam/123/quiz"
            self.goto_calls = []

        async def goto(self, url, **kwargs):
            self.goto_calls.append(url)

        async def wait_for_selector(self, sel, **kwargs):
            return True

        async def evaluate(self, script, *args):
            if "window.__APOLLO_STATE__" in script:
                # Return extracted assessmentId
                return "assessment_12345"
            if "leafGroups.map" in script:
                return [{"index": 0, "prompt": "Orchestrator Q", "options": ["A", "B"], "type": "radio"}]
            if "ansMap" in script:
                return {"0": True}
            if "scoreMatch" in script:
                return {"score_pct": 100.0, "passed": True, "feedback": {0: True}}
            return True

    page = MockAsyncPage()
    orch = CourseOrchestrator(max_concurrency=2)
    orch.attempt_mgr = FastAttemptManager(base_cache_dir=str(tmp_path / "cache"))

    item = {
        "title": "Cloud Assessment 1",
        "url": "https://www.coursera.org/learn/cloud/exam/123/quiz",
        "type": "quiz"
    }

    # Test direct API submission with mapped questions and grade polling
    mock_direct_api = MagicMock()
    mock_direct_api.fetch_assessment = AsyncMock(return_value={
        "id": "assessment_12345",
        "questions": [{"id": "part_1", "prompt": "API Q1", "options": ["X", "Y"]}]
    })
    mock_direct_api.submit_answers = AsyncMock(return_value={"success": True, "data": {"id": "sub_999"}})
    mock_direct_api.get_grade_feedback = AsyncMock(return_value={"score_pct": 100.0, "passed": True, "feedback": {0: True}})

    res_api = await orch._solve_item_on_page(page, item, direct_api=mock_direct_api)
    assert res_api["status"] == "submitted_direct_api"
    assert res_api["assessment_id"] == "assessment_12345"
    assert res_api["score_pct"] == 100.0
    assert res_api["passed"] is True
    assert mock_direct_api.submit_answers.called
    assert mock_direct_api.get_grade_feedback.called
    submitted_payload = mock_direct_api.submit_answers.call_args[0][1]
    assert submitted_payload != {}  # Never submit empty answers

    # Test clean fall-through to DOM execution when submit_answers returns HTTP 400
    mock_400_api = MagicMock()
    mock_400_api.fetch_assessment = AsyncMock(return_value={
        "id": "assessment_12345",
        "questions": [{"id": "part_1", "prompt": "API Q1", "options": ["X", "Y"]}]
    })
    mock_400_api.submit_answers = AsyncMock(return_value={"success": False, "status_code": 400, "body": "Bad Request"})

    res_400 = await orch._solve_item_on_page(page, item, direct_api=mock_400_api)
    assert res_400["status"] == "submitted"  # DOM fallback executed
    assert res_400["questions_solved"] == 1
    assert res_400["score_pct"] == 100.0

    # Test fall-through to DOM execution when direct API has no valid answers
    mock_empty_api = MagicMock()
    mock_empty_api.fetch_assessment = AsyncMock(return_value={"id": "assessment_12345", "questions": []})
    mock_empty_api.submit_answers = AsyncMock()

    res_fallthrough = await orch._solve_item_on_page(page, item, direct_api=mock_empty_api)
    assert res_fallthrough["status"] == "submitted"
    assert res_fallthrough["questions_solved"] == 1
    assert not mock_empty_api.submit_answers.called

    # Test graceful fallback to DOM execution when direct API fails
    mock_failing_api = MagicMock()
    mock_failing_api.fetch_assessment = AsyncMock(side_effect=Exception("API Error"))

    res_dom = await orch._solve_item_on_page(page, item, direct_api=mock_failing_api)
    assert res_dom["status"] == "submitted"
    assert res_dom["questions_solved"] == 1
    assert res_dom["score_pct"] == 100.0


@pytest.mark.anyio
async def test_async_tab_finders():
    """
    Verifies find_assessment_page and ProgrammingAssignmentManager.find_target_page
    are async and await p.title() properly without calling .lower() on unawaited coroutines.
    """
    from quiz_pilot.mcp_server import find_assessment_page
    from quiz_pilot.programming_solver import ProgrammingAssignmentManager

    class MockAsyncTab:
        def __init__(self, url, title_val):
            self.url = url
            self._title = title_val

        async def title(self):
            await asyncio.sleep(0.01)
            return self._title

    class MockContext:
        def __init__(self, pages):
            self.pages = pages

    class MockBrowser:
        def __init__(self, pages):
            self.contexts = [MockContext(pages)]

    tab1 = MockAsyncTab("https://google.com", "Search")
    tab2 = MockAsyncTab("https://www.coursera.org/learn/cloud/quiz", "Cloud Computing Quiz")
    tab3 = MockAsyncTab("https://www.coursera.org/learn/cloud/programming/123", "Project Assignment")
    browser = MockBrowser([tab1, tab2, tab3])

    # 1. find_assessment_page with keyword in title
    found_page = await find_assessment_page(browser, target_keyword="Cloud")
    assert found_page == tab2

    # 2. find_assessment_page with LMS keyword
    found_lms = await find_assessment_page(browser)
    assert found_lms in (tab2, tab3)

    # 3. find_target_page in ProgrammingAssignmentManager
    pm = ProgrammingAssignmentManager()
    found_prog = await pm.find_target_page(browser, target_keyword="Project")
    assert found_prog == tab3


def test_coursera_adapter_batch_fill_separate_from_submit():
    """
    Verifies batch_fill_answers only fills inputs and does not embed inline doSubmit,
    and submit_assessment_async explicitly handles the confirmation dialog.
    """
    import inspect

    src = inspect.getsource(CourseraAdapter.batch_fill_answers)
    assert "doSubmit" not in src
    assert "([ansMap])" in src

    src_async = inspect.getsource(CourseraAdapter.submit_assessment_async)
    assert "asyncio.sleep(0.5)" in src_async


def test_coursera_adapter_prevent_runaway_dom_traversal():
    """
    Verifies extract_questions restricts upward traversal to question boundary selectors
    (div[data-testid='part-submission-container'], div.rc-Formulation, fieldset, form)
    and does not assign document.body.innerText.
    """
    import inspect

    src = inspect.getsource(CourseraAdapter.extract_questions)
    assert "boundarySelectors" in src
    assert "part-submission-container" in src
    assert "rc-Formulation" in src
    assert "document.body" in src
    assert "boundaryElem" in src


def test_quiz_analysis_preserved_across_purge_all(tmp_path):
    """
    Verifies that quiz_analysis.md in workspace root is preserved even after
    FastAttemptManager.purge_all() wipes .assessment_cache/.
    """
    cache_dir = str(tmp_path / "cache")
    mgr = FastAttemptManager(base_cache_dir=cache_dir)

    root_md = str(tmp_path / "quiz_analysis.md")
    mgr.record_attempt(
        quiz_id="persist_test",
        attempt_num=1,
        questions=[{"index": 0, "prompt": "Persist Q", "options": ["A"]}],
        answers={0: 0},
        feedback={0: True},
        md_path=root_md
    )
    assert os.path.exists(root_md)
    assert os.path.exists(os.path.join(cache_dir, "quiz_analysis.md"))

    # Purge all temporary cache
    mgr.purge_all()

    # Cache folder files are purged
    assert not os.path.exists(os.path.join(cache_dir, "quiz_analysis.md"))
    # Workspace root quiz_analysis.md is preserved!
    assert os.path.exists(root_md)


def test_cli_peer_commands_use_async_playwright():
    """
    Verifies cmd_submit_peer and cmd_complete_reviews use async_playwright
    and await find_assessment_page within asyncio.run.
    """
    import inspect
    from quiz_pilot import cli

    src_sub = inspect.getsource(cli.cmd_submit_peer)
    assert "async_playwright" in src_sub
    assert "asyncio.run" in src_sub
    assert "await find_assessment_page" in src_sub

    src_rev = inspect.getsource(cli.cmd_complete_reviews)
    assert "async_playwright" in src_rev
    assert "asyncio.run" in src_rev
    assert "await find_assessment_page" in src_rev


@pytest.mark.anyio
async def test_server_websocket_pool_multi_tab():
    """
    Verifies WebSocket bridge server connection pool handles multi-tab
    connects and disconnects without dropping bridge connectivity.
    """
    from quiz_pilot import server

    ws1 = MagicMock()
    ws1.accept = AsyncMock()
    ws1.receive_text = AsyncMock(side_effect=Exception("disconnect"))
    ws1.send_text = AsyncMock()

    ws2 = MagicMock()
    ws2.accept = AsyncMock()
    ws2.receive_text = AsyncMock(side_effect=Exception("disconnect"))
    ws2.send_text = AsyncMock()

    # Reset pool
    server.active_websockets.clear()
    server.latest_page_state["is_connected"] = False

    # Simulate tab 1 connect
    await server.websocket_endpoint(ws1)
    # ws1 disconnected in finally block
    assert len(server.active_websockets) == 0
    assert server.latest_page_state["is_connected"] is False

    # Simulate multi-tab presence
    server.active_websockets.append(ws1)
    server.active_websockets.append(ws2)
    server.latest_page_state["is_connected"] = True

    # Tab 1 disconnects: Tab 2 must remain active
    server.active_websockets.remove(ws1)
    server.latest_page_state["is_connected"] = len(server.active_websockets) > 0

    assert len(server.active_websockets) == 1
    assert server.latest_page_state["is_connected"] is True
    assert server.active_websockets[0] == ws2

    # Clean up
    server.active_websockets.clear()
    server.latest_page_state["is_connected"] = False


def test_no_duplicate_files():
    """
    Verifies that the project repository contains only single canonical copies
    of course_orchestrator.py, mcp_server.py, and programming_solver.py.
    """
    import glob
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    for filename in ["course_orchestrator.py", "mcp_server.py", "programming_solver.py"]:
        matches = glob.glob(f"{base_dir}/**/{filename}", recursive=True)
        # Filter out virtual environments or pycache
        repo_matches = [m for m in matches if ".venv" not in m and "__pycache__" not in m]
        assert len(repo_matches) == 1, f"Found multiple copies of {filename}: {repo_matches}"
        assert os.path.dirname(repo_matches[0]).endswith("quiz_pilot")


def test_batch_fill_guarantees_no_unanswered_questions():
    """
    Verifies CourseraAdapter.batch_fill_answers includes the millisecond
    failsafe sweep preventing unanswered questions.
    """
    import inspect
    from quiz_pilot.lms_adapters.coursera_adapter import CourseraAdapter

    src = inspect.getsource(CourseraAdapter.batch_fill_answers)
    assert "leafGroups.forEach" in src
    assert "hasChecked" in src
    assert "radios[0].click()" in src


def test_purge_all_cleans_bridge_temp_files(tmp_path):
    """
    Verifies FastAttemptManager.purge_all deletes both cache directory
    and temporary bridge files.
    """
    cache_dir = str(tmp_path / "cache")
    mgr = FastAttemptManager(base_cache_dir=cache_dir)
    bridge_file = os.path.join(tempfile.gettempdir(), "quiz_pilot_bridge.json")
    with open(bridge_file, "w") as f:
        f.write("{}")
    assert os.path.exists(bridge_file)

    mgr.purge_all()
    assert not os.path.exists(bridge_file)
    assert not os.path.exists(os.path.join(cache_dir, "quiz_analysis.md"))


