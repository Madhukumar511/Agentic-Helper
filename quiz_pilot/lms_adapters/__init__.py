"""
LMS Adapters Factory for Agentic-Helper.
"""

from typing import Any, Optional
from .base_adapter import BaseLMSAdapter
from .coursera_adapter import CourseraAdapter
from .canvas_adapter import CanvasAdapter
from .moodle_adapter import MoodleAdapter
from .blackboard_adapter import BlackboardAdapter
from .google_forms_adapter import GoogleFormsAdapter

ADAPTERS = [
    CourseraAdapter,
    CanvasAdapter,
    MoodleAdapter,
    BlackboardAdapter,
    GoogleFormsAdapter
]

def get_lms_adapter(page: Any) -> BaseLMSAdapter:
    """
    Automatically detects the LMS platform from the active page URL and DOM structure.
    Falls back to Coursera/Universal adapter if unknown.
    """
    for adapter_cls in ADAPTERS:
        adapter = adapter_cls(page)
        if adapter.detect():
            return adapter
    # Default to Coursera/Universal adapter
    return CourseraAdapter(page)
