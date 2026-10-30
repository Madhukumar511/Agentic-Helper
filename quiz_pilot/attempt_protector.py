"""
Fast Attempt Strategy and Attempt Budget Protector for Quiz-Pilot / Agentic-Helper.

Enforces:
1. Isolated Screenshots Directory: All screenshots stored strictly in one directory (.assessment_cache/screenshots/).
2. Fast 3-Attempt Heuristic & Caching:
   - Attempt 1: Fast heuristic solve and submit.
   - Saves questions, answers, and feedback to temporary markdown and json cache.
   - Attempt 2/3: Instantly locks in verified correct answers (0 extra compute), only computes diffs.
   - Cleans up temporary files automatically upon passing.
3. Budget Threshold Protector:
   - Prevents submission if confidence score < threshold (default 80%) to avoid burning attempts.
"""

import os
import shutil
import json
import hashlib
from typing import Dict, List, Optional, Any, Tuple


class FastAttemptManager:
    """
    Manages quiz attempts, temporary answer caching, and single-folder screenshot storage.
    """
    def __init__(self, base_cache_dir: str = ".assessment_cache", min_pass_threshold: float = 80.0):
        self.base_cache_dir = os.path.abspath(base_cache_dir)
        self.screenshot_dir = os.path.join(self.base_cache_dir, "screenshots")
        self.min_pass_threshold = min_pass_threshold
        
        # Ensure directories exist
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def get_screenshot_path(self, filename: str) -> str:
        """
        Enforces rule: All screenshots strictly stored in the dedicated screenshots folder.
        """
        clean_name = os.path.basename(filename)
        if not clean_name.endswith(".png"):
            clean_name += ".png"
        return os.path.join(self.screenshot_dir, clean_name)

    def capture_screenshot(self, page_or_element: Any, filename: str) -> str:
        """
        Takes screenshot directly into the isolated screenshot folder.
        """
        path = self.get_screenshot_path(filename)
        page_or_element.screenshot(path=path)
        return path

    def _get_q_fingerprint(self, question: Dict) -> str:
        """
        Computes a collision-resistant fingerprint for a question using:
        1. Full normalized prompt text (no truncation).
        2. Sorted normalized options.
        3. Question type.
        Eliminates collisions even in randomized question pools with identical intro text.
        """
        prompt = question.get("prompt", "").strip()
        norm_prompt = " ".join(prompt.split())
        options = question.get("options", [])
        norm_opts = "|".join(sorted([" ".join(str(opt).split()) for opt in options]))
        q_type = str(question.get("type", ""))
        content = f"{q_type}::{norm_prompt}::options::{norm_opts}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]

    def save_attempt(
        self,
        quiz_id: str,
        attempt_num: int,
        questions: List[Dict],
        answers: Dict[int, Any],
        score_pct: Optional[float] = None,
        feedback: Optional[Dict[int, bool]] = None
    ) -> Tuple[str, str]:
        """
        Saves attempt data to temporary JSON and Markdown cache.
        Returns (json_path, md_path).
        """
        data = {
            "quiz_id": quiz_id,
            "attempt": attempt_num,
            "score_pct": score_pct,
            "questions": questions,
            "answers": answers,
            "feedback": feedback or {}
        }
        
        json_file = os.path.join(self.base_cache_dir, f"{quiz_id}_attempt_{attempt_num}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Generate temporary markdown file for quick AI reading
        md_file = os.path.join(self.base_cache_dir, f"{quiz_id}_attempt_{attempt_num}.md")
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# Assessment Cache: {quiz_id} (Attempt {attempt_num})\n\n")
            if score_pct is not None:
                f.write(f"**Score**: {score_pct:.1f}% | **Status**: {'PASSED' if score_pct >= self.min_pass_threshold else 'FAILED'}\n\n")
            f.write("## Questions & Answer Log\n\n")
            for q in questions:
                idx = q.get("index", 0)
                q_num = idx + 1
                q_prompt = q.get("prompt", "").replace("\n", " ")[:120]
                ans = answers.get(idx, "Unanswered")
                correct = feedback.get(idx, None) if feedback else None
                status_badge = "✅ CORRECT" if correct is True else ("❌ WRONG" if correct is False else "❔ UNKNOWN")
                
                f.write(f"### Q{q_num} [{q.get('type', 'radio')}] - {status_badge}\n")
                f.write(f"- **Prompt**: {q_prompt}...\n")
                f.write(f"- **Submitted Answer**: `{ans}`\n\n")

        return json_file, md_file

    def get_known_verified_answers(self, quiz_id: str) -> Dict[str, Any]:
        """
        Scans previous attempts for this quiz and returns a map of verified correct answers
        by question fingerprint. Allows next attempts to solve instantly with 0 compute.
        """
        verified_answers = {}
        for fname in os.listdir(self.base_cache_dir):
            if fname.startswith(f"{quiz_id}_attempt_") and fname.endswith(".json"):
                path = os.path.join(self.base_cache_dir, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    feedback = data.get("feedback", {})
                    answers = data.get("answers", {})
                    for q in data.get("questions", []):
                        idx = str(q.get("index", 0))
                        # If Coursera/LMS marked this question 100% correct
                        if feedback.get(idx) is True:
                            fp = self._get_q_fingerprint(q)
                            verified_answers[fp] = answers.get(idx)
                except Exception:
                    continue
        return verified_answers

    def verify_attempt_budget(self, predicted_confidence_pct: float) -> Tuple[bool, str]:
        """
        Attempt Budget Protector:
        Prevents wasting attempts if predicted score is below the passing threshold.
        """
        if predicted_confidence_pct < self.min_pass_threshold:
            return False, (
                f"Blocked Submission: Predicted confidence {predicted_confidence_pct:.1f}% "
                f"is below safety threshold {self.min_pass_threshold:.1f}%. "
                f"Coursera/LMS limits attempts (3 every 8 hours). Re-evaluating uncertain questions."
            )
        return True, f"Confidence {predicted_confidence_pct:.1f}% meets safety threshold."

    def purge_cache(self, quiz_id: Optional[str] = None):
        """
        Clean up law: Purge temporary files when quiz is passed or on finalization.
        """
        if quiz_id:
            for fname in os.listdir(self.base_cache_dir):
                if fname.startswith(f"{quiz_id}_") and (fname.endswith(".json") or fname.endswith(".md")):
                    try:
                        os.remove(os.path.join(self.base_cache_dir, fname))
                    except OSError:
                        pass
        else:
            self.purge_all()

    def purge_all(self):
        """
        Full Zero-Artifact cleanup: Wipes all temporary attempt files, JSON, Markdown,
        and all screenshots from .assessment_cache to ensure the project remains completely pristine.
        """
        if os.path.exists(self.base_cache_dir):
            shutil.rmtree(self.base_cache_dir, ignore_errors=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)

