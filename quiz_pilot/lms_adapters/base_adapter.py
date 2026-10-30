"""
Base LMS Adapter Interface for Agentic-Helper.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseLMSAdapter(ABC):
    """
    Abstract LMS Driver for multi-platform quiz automation.
    """
    def __init__(self, page: Any):
        self.page = page

    @abstractmethod
    def detect(self) -> bool:
        """Returns True if the current page matches this LMS platform."""
        pass

    @abstractmethod
    def extract_questions(self) -> List[Dict[str, Any]]:
        """Extracts list of questions, options, types, and images from the active DOM."""
        pass

    @abstractmethod
    def fill_answer(self, question_index: int, value: Any) -> bool:
        """Selects radio/checkbox or types numeric/text answer for the question."""
        pass

    def batch_fill_answers(self, answers: Dict[int, Any], auto_submit: bool = False) -> Dict[str, Any]:
        """Default batch filling: iterates over individual fill_answer calls."""
        res = {}
        for q_idx, val in answers.items():
            res[str(q_idx)] = self.fill_answer(int(q_idx), val)
        if auto_submit:
            self.submit_assessment()
        return res

    @abstractmethod
    def submit_assessment(self) -> bool:
        """Triggers assessment submission with any required confirmation steps."""
        pass

    @abstractmethod
    def extract_feedback(self) -> Dict[str, Any]:
        """Parses score percentage and per-question correctness from results screen."""
        pass
