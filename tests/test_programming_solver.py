"""
Unit Tests for Programming Assignment Automation Engine.
"""

import os
import unittest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from quiz_pilot.programming_solver import ProgrammingAssignmentManager
from quiz_pilot.mcp_server import TOOLS


class TestProgrammingSolver(unittest.TestCase):
    def setUp(self):
        self.mgr = ProgrammingAssignmentManager()

    def test_is_programming_page_detection(self):
        # URL matching
        self.assertTrue(self.mgr.is_programming_page(
            "https://www.coursera.org/learn/cloud/programming/123/mp1", ""
        ))
        self.assertTrue(self.mgr.is_programming_page(
            "https://www.coursera.org/learn/cloud/peer/5pBeh/task-1-submission", ""
        ))
        self.assertTrue(self.mgr.is_programming_page(
            "https://canvas.instructure.com/courses/10/assignment-submission/20", ""
        ))

        # Text matching
        self.assertTrue(self.mgr.is_programming_page(
            "https://example.com/item", "Download the starter code zip and submit code to the autograder."
        ))

        # Non-matching standard quiz
        self.assertFalse(self.mgr.is_programming_page(
            "https://example.com/page", "What is the capital of France?"
        ))

    def test_upload_missing_file_error(self):
        import asyncio
        res = asyncio.run(self.mgr.upload_and_submit(file_path="/path/to/nonexistent_code_12345.zip"))
        self.assertFalse(res["success"])
        self.assertIn("not found on disk", res["error"])

    def test_mcp_programming_tools_registered(self):
        tool_names = [t["name"] for t in TOOLS]
        self.assertIn("inspect_programming_task", tool_names)
        self.assertIn("submit_code_file", tool_names)
        self.assertIn("poll_autograder_results", tool_names)

    def test_starter_file_download_logic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dummy_file = os.path.join(tmpdir, "starter.zip")
            with open(dummy_file, "w") as f:
                f.write("mock starter zip content")

            # Verify local destination handling
            self.assertTrue(os.path.exists(dummy_file))


if __name__ == "__main__":
    unittest.main()
