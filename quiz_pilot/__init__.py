"""
Quiz Pilot / Agentic Helper Package.
"""

from .dom_detector import (
    DETECTION_SCRIPT,
    SELECT_OPTION_SCRIPT,
    NAVIGATE_NEXT_SCRIPT,
    IS_SUBMIT_SCREEN_SCRIPT
)
from .cdp_client import CDPQuizClient
from .automation_engine import AutomationEngine
from .ai_solver import AISolver
from .graph_solvers import ChandyLamportSolver, MulticastSimulator, LamportVectorClockSolver
from .diagram_parser import LocalDiagramParser
from .attempt_protector import FastAttemptManager
from .lms_adapters import get_lms_adapter
from .tab_scheduler import AsyncTabScheduler, solve_all_open_quizzes_sync
from .programming_solver import (
    ProgrammingAssignmentManager,
    inspect_programming_task_sync,
    submit_code_file_sync,
    poll_autograder_results_sync
)
from .peer_review_solver import PeerReviewManager

__all__ = [
    "DETECTION_SCRIPT",
    "SELECT_OPTION_SCRIPT",
    "NAVIGATE_NEXT_SCRIPT",
    "IS_SUBMIT_SCREEN_SCRIPT",
    "CDPQuizClient",
    "AutomationEngine",
    "AISolver",
    "ChandyLamportSolver",
    "MulticastSimulator",
    "LamportVectorClockSolver",
    "LocalDiagramParser",
    "FastAttemptManager",
    "get_lms_adapter",
    "AsyncTabScheduler",
    "solve_all_open_quizzes_sync",
    "ProgrammingAssignmentManager",
    "inspect_programming_task_sync",
    "submit_code_file_sync",
    "poll_autograder_results_sync",
    "PeerReviewManager"
]
