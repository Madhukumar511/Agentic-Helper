"""
Base LMS Adapter Interface for Agentic-Helper.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseLMSAdapter(ABC):
    """
    Abstract LMS Driver for multi-platform quiz automation.
    Supports both synchronous and asynchronous Playwright page execution.
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

    async def extract_questions_async(self) -> List[Dict[str, Any]]:
        """Asynchronously extracts questions from the active DOM."""
        res = self.extract_questions()
        if asyncio.iscoroutine(res):
            return await res
        return res

    @abstractmethod
    def fill_answer(self, question_index: int, value: Any) -> bool:
        """Selects radio/checkbox or types numeric/text answer for the question."""
        pass

    async def fill_answer_async(self, question_index: int, value: Any) -> bool:
        """Asynchronously fills the answer for the question."""
        res = self.fill_answer(question_index, value)
        if asyncio.iscoroutine(res):
            return await res
        return bool(res)

    def batch_fill_answers(self, answers: Dict[int, Any], auto_submit: bool = False) -> Dict[str, Any]:
        """Default batch filling: iterates over individual fill_answer calls."""
        res = {}
        for q_idx, val in answers.items():
            res[str(q_idx)] = self.fill_answer(int(q_idx), val)
        if auto_submit:
            self.submit_assessment()
        return res

    async def batch_fill_answers_async(self, answers: Dict[Any, Any], auto_submit: bool = False) -> Dict[str, Any]:
        """Asynchronously fills batch answers."""
        if hasattr(self, "batch_fill_answers") and type(self).batch_fill_answers != BaseLMSAdapter.batch_fill_answers:
            res = self.batch_fill_answers(answers, auto_submit=auto_submit)
            if asyncio.iscoroutine(res):
                return await res
            return res
        res = {}
        for q_idx, val in answers.items():
            res[str(q_idx)] = await self.fill_answer_async(int(q_idx), val)
        if auto_submit:
            await self.submit_assessment_async()
        return res

    @abstractmethod
    def submit_assessment(self) -> bool:
        """Triggers assessment submission with any required confirmation steps."""
        pass

    async def submit_assessment_async(self) -> bool:
        """Asynchronously submits assessment."""
        res = self.submit_assessment()
        if asyncio.iscoroutine(res):
            return await res
        return bool(res)

    @abstractmethod
    def extract_feedback(self) -> Dict[str, Any]:
        """Parses score percentage and per-question correctness from results screen."""
        pass

    async def extract_feedback_async(self) -> Dict[str, Any]:
        """Asynchronously parses feedback."""
        res = self.extract_feedback()
        if asyncio.iscoroutine(res):
            return await res
        return res
