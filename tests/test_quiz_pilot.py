"""
Unit Tests for Quiz-Pilot.
"""

import unittest
from quiz_pilot.ai_solver import AISolver
from quiz_pilot.dom_detector import (
    DETECTION_SCRIPT,
    SELECT_OPTION_SCRIPT,
    NAVIGATE_NEXT_SCRIPT,
    IS_SUBMIT_SCREEN_SCRIPT
)


class TestQuizPilot(unittest.TestCase):
    def test_ai_solver_json_parsing(self):
        solver = AISolver()
        raw_json = '{"selected_indices": [2], "confidence": 0.99, "explanation": "TCP is connection oriented"}'
        parsed = solver._parse_json_response(raw_json, total_options=4)
        self.assertEqual(parsed["selected_indices"], [2])
        self.assertEqual(parsed["confidence"], 0.99)

    def test_ai_solver_markdown_wrapped_parsing(self):
        solver = AISolver()
        wrapped_json = """```json
{
  "selected_indices": [1, 3],
  "confidence": 0.95,
  "explanation": "Multiple valid choices"
}
```"""
        parsed = solver._parse_json_response(wrapped_json, total_options=4)
        self.assertEqual(parsed["selected_indices"], [1, 3])
        self.assertEqual(parsed["confidence"], 0.95)

    def test_ai_solver_fallback(self):
        solver = AISolver()
        corrupted = "I think the answer is [2] because of reason X."
        parsed = solver._parse_json_response(corrupted, total_options=4)
        self.assertEqual(parsed["selected_indices"], [2])

    def test_scripts_non_empty(self):
        self.assertTrue(len(DETECTION_SCRIPT) > 100)
        self.assertTrue(len(SELECT_OPTION_SCRIPT) > 50)
        self.assertTrue(len(NAVIGATE_NEXT_SCRIPT) > 50)
        self.assertTrue(len(IS_SUBMIT_SCREEN_SCRIPT) > 50)


if __name__ == "__main__":
    unittest.main()
