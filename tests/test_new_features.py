"""
Unit Tests for Agentic-Helper Features:
- Attempt Budget Protector & Temporary Cache Law
- Isolated Single Screenshot Folder
- Multi-LMS Adapters
- Local Diagram Parser
- MCP Server Tools
"""

import unittest
import os
import shutil
import numpy as np
from PIL import Image

from quiz_pilot.attempt_protector import FastAttemptManager
from quiz_pilot.diagram_parser import LocalDiagramParser
from quiz_pilot.lms_adapters import (
    CourseraAdapter,
    CanvasAdapter,
    MoodleAdapter,
    BlackboardAdapter,
    GoogleFormsAdapter,
    get_lms_adapter
)
from quiz_pilot.mcp_server import TOOLS


class MockPage:
    def __init__(self, url: str):
        self.url = url


class TestAgenticHelperFeatures(unittest.TestCase):
    def setUp(self):
        self.test_cache = ".test_assessment_cache"
        self.mgr = FastAttemptManager(base_cache_dir=self.test_cache, min_pass_threshold=80.0)

    def tearDown(self):
        shutil.rmtree(self.test_cache, ignore_errors=True)

    def test_single_screenshot_folder_law(self):
        # All screenshots must strictly live in the dedicated screenshot directory
        path = self.mgr.get_screenshot_path("my_diagram")
        expected_dir = os.path.abspath(os.path.join(self.test_cache, "screenshots"))
        self.assertEqual(os.path.dirname(path), expected_dir)
        self.assertTrue(path.endswith("my_diagram.png"))

    def test_attempt_budget_protector(self):
        # Confidence < 80% blocked to preserve 3-attempt limit
        allowed, reason = self.mgr.verify_attempt_budget(75.0)
        self.assertFalse(allowed)
        self.assertIn("Blocked Submission", reason)

        # Confidence >= 80% allowed
        allowed, reason = self.mgr.verify_attempt_budget(92.0)
        self.assertTrue(allowed)

    def test_temporary_md_cache_and_known_answers(self):
        quiz_id = "test_quiz_101"
        questions = [
            {"index": 0, "prompt": "What is PUE?", "type": "radio"},
            {"index": 1, "prompt": "Paxos guarantees safety?", "type": "radio"}
        ]
        answers = {0: "2.0", 1: "Is always safe"}
        feedback = {0: True, 1: False} # Q0 is correct, Q1 is wrong

        json_file, md_file = self.mgr.save_attempt(
            quiz_id=quiz_id,
            attempt_num=1,
            questions=questions,
            answers=answers,
            score_pct=50.0,
            feedback=feedback
        )
        self.assertTrue(os.path.exists(json_file))
        self.assertTrue(os.path.exists(md_file))

        # Check that Q0 answer is remembered for attempt 2
        known = self.mgr.get_known_verified_answers(quiz_id)
        self.assertEqual(len(known), 1)
        self.assertIn("2.0", known.values())

        # Purge temporary files
        self.mgr.purge_cache(quiz_id)
        self.assertFalse(os.path.exists(json_file))
        self.assertFalse(os.path.exists(md_file))

    def test_multi_lms_adapter_detection(self):
        c_page = MockPage("https://www.coursera.org/learn/cloud/exam")
        canvas_page = MockPage("https://canvas.instructure.com/courses/1/quizzes/2")
        moodle_page = MockPage("https://school.edu/moodle/mod/quiz/attempt.php")
        bb_page = MockPage("https://learn.blackboard.com/webapps/assessment")
        forms_page = MockPage("https://docs.google.com/forms/d/e/1FAIpQLSc/viewform")

        self.assertIsInstance(get_lms_adapter(c_page), CourseraAdapter)
        self.assertIsInstance(get_lms_adapter(canvas_page), CanvasAdapter)
        self.assertIsInstance(get_lms_adapter(moodle_page), MoodleAdapter)
        self.assertIsInstance(get_lms_adapter(bb_page), BlackboardAdapter)
        self.assertIsInstance(get_lms_adapter(forms_page), GoogleFormsAdapter)

    def test_local_diagram_parser(self):
        # Generate dummy spacetime diagram
        img_arr = np.ones((100, 200), dtype=np.uint8) * 255
        # Draw 2 horizontal process lines
        img_arr[30, 20:180] = 0
        img_arr[70, 20:180] = 0
        # Draw vertical stroke
        img_arr[25:35, 60] = 0
        
        test_img_path = os.path.join(self.test_cache, "dummy_diagram.png")
        Image.fromarray(img_arr).save(test_img_path)

        parser = LocalDiagramParser()
        res = parser.parse_spacetime_diagram(test_img_path)
        self.assertEqual(res["num_processes"], 2)
        self.assertIn("adjacency_matrix", res)

        solved = parser.solve_fast_lamport(res)
        self.assertIn("timestamps", solved)

    def test_mcp_server_tools_registered(self):
        tool_names = [t["name"] for t in TOOLS]
        self.assertIn("launch_browser", tool_names)
        self.assertIn("extract_questions", tool_names)
        self.assertIn("fill_answer", tool_names)
        self.assertIn("solve_batch", tool_names)
        self.assertIn("submit_assessment", tool_names)
        self.assertIn("solve_multicast", tool_names)
        self.assertIn("solve_diagram", tool_names)
        self.assertIn("inspect_all_tabs", tool_names)
        self.assertIn("solve_parallel_quizzes", tool_names)

    def test_async_tab_scheduler_detection(self):
        from quiz_pilot.tab_scheduler import AsyncTabScheduler
        
        p_quiz = MockPage("https://www.coursera.org/learn/cloud/assignment-submission/123/quiz")
        p_normal = MockPage("https://www.google.com")
        p_canvas = MockPage("https://canvas.instructure.com/courses/1/quizzes/5")
        
        self.assertTrue(AsyncTabScheduler.is_assessment_page(p_quiz))
        self.assertTrue(AsyncTabScheduler.is_assessment_page(p_canvas))
        self.assertFalse(AsyncTabScheduler.is_assessment_page(p_normal))

        class MockBrowser:
            def __init__(self, pages):
                class MockCtx:
                    def __init__(self, p_list):
                        self.pages = p_list
                self.contexts = [MockCtx(pages)]

        mb = MockBrowser([p_quiz, p_normal, p_canvas])
        scheduler = AsyncTabScheduler()
        discovered = scheduler.discover_assessment_tabs(mb)
        self.assertEqual(len(discovered), 2)
        self.assertIn(p_quiz, discovered)
        self.assertIn(p_canvas, discovered)


if __name__ == "__main__":
    unittest.main()
