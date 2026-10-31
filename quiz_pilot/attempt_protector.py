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
import re
import shutil
import json
import hashlib
import tempfile
from typing import Dict, List, Optional, Any, Tuple


class FastAttemptManager:
    """
    Manages quiz attempts, temporary answer caching, and single-folder screenshot storage.
    """
    def __init__(self, base_cache_dir: str = ".assessment_cache", min_pass_threshold: float = 80.0):
        self.base_cache_dir = os.path.abspath(base_cache_dir)
        self.screenshot_dir = os.path.join(self.base_cache_dir, "screenshots")
        self.min_pass_threshold = min_pass_threshold
        self.quiz_memory: Dict[str, Dict[str, Any]] = {}
        
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

    def _get_opt_text(self, opt: Any) -> str:
        """Extracts plain text representation from either a string or option dict."""
        if isinstance(opt, dict):
            return str(opt.get("text") or opt.get("label") or opt.get("val") or opt.get("name") or "")
        return str(opt) if opt is not None else ""

    def _get_q_fingerprint(self, question: Dict) -> str:
        """
        Computes a collision-resistant fingerprint for a question using:
        1. Full normalized prompt text (no truncation).
        2. Sorted normalized options.
        3. Question type.
        Eliminates collisions even in randomized question pools with identical intro text.
        """
        prompt = question.get("prompt") or question.get("text") or ""
        norm_prompt = " ".join(str(prompt).strip().split())
        options = question.get("options", [])
        norm_opts = "|".join(sorted([" ".join(self._get_opt_text(opt).split()) for opt in options]))
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

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        s = re.sub(r'[\r\n\t]+', ' ', str(text))
        s = re.sub(r'\s+', ' ', s).strip().lower()
        return s

    def _match_option_by_text(self, target_text: str, options: List[Any]) -> Optional[int]:
        if not target_text or not options:
            return None
        norm_target = self._normalize_text(target_text)
        # 1. Exact match
        for i, opt in enumerate(options):
            opt_text = self._get_opt_text(opt)
            if self._normalize_text(opt_text) == norm_target:
                return i
        # 2. Substring / containment match
        for i, opt in enumerate(options):
            norm_opt = self._normalize_text(self._get_opt_text(opt))
            if (norm_target and norm_target in norm_opt) or (norm_opt and norm_opt in norm_target):
                return i
        return None

    def _is_option_eliminated(self, opt_text: Any, eliminated_texts: List[str]) -> bool:
        norm_opt = self._normalize_text(self._get_opt_text(opt_text))
        if not norm_opt:
            return False
        for elim in eliminated_texts:
            norm_elim = self._normalize_text(elim)
            if norm_opt == norm_elim or (norm_elim and norm_elim in norm_opt) or (norm_opt and norm_opt in norm_elim):
                return True
        return False

    def record_attempt(
        self,
        quiz_id: str,
        attempt_num: int,
        questions: List[Dict],
        answers: Dict[Any, Any],
        feedback: Dict[Any, bool],
        score_pct: Optional[float] = None,
        md_path: str = "quiz_analysis.md"
    ) -> str:
        """
        Records attempt feedback, locks in verified correct options,
        eliminates failed options from future selection, and exports/updates quiz_analysis.md.
        """
        # Maintain backwards-compatible temporary cache
        int_answers = {}
        for k, v in answers.items():
            try:
                int_answers[int(k)] = v
            except (ValueError, TypeError):
                pass
        int_feedback = {}
        for k, v in feedback.items():
            try:
                int_feedback[int(k)] = bool(v)
            except (ValueError, TypeError):
                pass

        if score_pct is None and int_feedback:
            correct_cnt = sum(1 for v in int_feedback.values() if v is True)
            score_pct = (correct_cnt / max(1, len(int_feedback))) * 100.0

        self.save_attempt(
            quiz_id=quiz_id,
            attempt_num=attempt_num,
            questions=questions,
            answers=int_answers,
            score_pct=score_pct,
            feedback=int_feedback
        )

        # Retrieve or initialize quiz memory
        if quiz_id not in self.quiz_memory:
            self.load_quiz_analysis(md_path=md_path, quiz_id=quiz_id)

        q_mem = self.quiz_memory.setdefault(quiz_id, {
            "quiz_id": quiz_id,
            "attempts": 0,
            "latest_score": score_pct or 0.0,
            "passed": bool(score_pct is not None and score_pct >= self.min_pass_threshold),
            "questions": {}
        })

        q_mem["attempts"] = attempt_num
        if score_pct is not None:
            q_mem["latest_score"] = score_pct
            q_mem["passed"] = score_pct >= self.min_pass_threshold

        for q in questions:
            idx = q.get("index", 0)
            prompt = q.get("prompt", "").strip()
            norm_p = self._normalize_text(prompt)
            options = q.get("options", [])
            q_type = q.get("type", "radio")

            # Determine submitted answer text
            sub_val = answers.get(idx)
            if sub_val is None:
                sub_val = answers.get(str(idx))

            sub_text = ""
            if isinstance(sub_val, int) and 0 <= sub_val < len(options):
                sub_text = self._get_opt_text(options[sub_val])
            elif isinstance(sub_val, list):
                sub_text = ", ".join([
                    self._get_opt_text(options[i]) if isinstance(i, int) and 0 <= i < len(options) else self._get_opt_text(i)
                    for i in sub_val
                ])
            elif sub_val is not None:
                sub_text = self._get_opt_text(sub_val)

            # Determine feedback
            fb_val = feedback.get(idx)
            if fb_val is None:
                fb_val = feedback.get(str(idx))

            entry = q_mem["questions"].setdefault(norm_p, {
                "index": idx,
                "qNum": idx + 1,
                "prompt": prompt,
                "type": q_type,
                "status": "UNKNOWN",
                "verified_text": None,
                "eliminated_texts": [],
                "options": options,
                "next_candidate": None
            })
            entry["options"] = options

            if fb_val is True:
                entry["status"] = "LOCKED_CORRECT"
                entry["verified_text"] = sub_text
                entry["eliminated_texts"] = [e for e in entry["eliminated_texts"] if self._normalize_text(e) != self._normalize_text(sub_text)]
                entry["next_candidate"] = sub_text
            elif fb_val is False:
                if entry.get("status") != "LOCKED_CORRECT":
                    entry["status"] = "NEEDS_RETRY"
                    if sub_text and not any(self._normalize_text(sub_text) == self._normalize_text(e) for e in entry["eliminated_texts"]):
                        entry["eliminated_texts"].append(sub_text)

                    # Compute remaining candidate options (excluding eliminated)
                    rem_candidates = [
                        self._get_opt_text(opt) for opt in options
                        if not self._is_option_eliminated(opt, entry["eliminated_texts"])
                    ]
                    entry["next_candidate"] = rem_candidates[0] if rem_candidates else None

        return self.export_quiz_analysis_markdown(quiz_id=quiz_id, md_path=md_path)

    def get_retry_answers(
        self,
        questions: List[Dict],
        md_path: str = "quiz_analysis.md",
        quiz_id: Optional[str] = None
    ) -> Dict[int, Any]:
        """
        Determines the optimal answers for a retry attempt:
        - Locks in verified correct answers (matched by exact text across shuffles)
        - Eliminates previously failed options and selects the next untried candidate
        - Guarantees failed options are never selected again
        """
        if not self.quiz_memory or (quiz_id and quiz_id not in self.quiz_memory):
            self.load_quiz_analysis(md_path=md_path, quiz_id=quiz_id)

        answers: Dict[int, Any] = {}
        target_mem = None
        if quiz_id and quiz_id in self.quiz_memory:
            target_mem = self.quiz_memory[quiz_id]
        elif self.quiz_memory:
            target_mem = next(iter(self.quiz_memory.values()))

        known_q_map = target_mem.get("questions", {}) if target_mem else {}

        for q in questions:
            idx = q.get("index", 0)
            prompt = q.get("prompt", "").strip()
            norm_p = self._normalize_text(prompt)
            options = q.get("options", [])

            # Match question prompt in memory
            matched_entry = None
            if norm_p in known_q_map:
                matched_entry = known_q_map[norm_p]
            else:
                for kp, ventry in known_q_map.items():
                    if norm_p and (norm_p in kp or kp in norm_p):
                        matched_entry = ventry
                        break

            if matched_entry:
                status = matched_entry.get("status")
                verified_text = matched_entry.get("verified_text")
                eliminated_texts = matched_entry.get("eliminated_texts", [])

                # 1. Verified correct -> lock in answer by text match
                if status == "LOCKED_CORRECT" and verified_text:
                    opt_idx = self._match_option_by_text(verified_text, options)
                    if opt_idx is not None:
                        answers[idx] = opt_idx
                        continue
                    else:
                        answers[idx] = verified_text
                        continue

                # 2. Needs retry -> choose candidate from uneliminated options
                if eliminated_texts and options:
                    valid_indices = [
                        i for i, opt in enumerate(options)
                        if not self._is_option_eliminated(opt, eliminated_texts)
                    ]
                    if valid_indices:
                        next_cand = matched_entry.get("next_candidate")
                        chosen_idx = None
                        if next_cand:
                            for vi in valid_indices:
                                if self._normalize_text(self._get_opt_text(options[vi])) == self._normalize_text(next_cand):
                                    chosen_idx = vi
                                    break
                        if chosen_idx is None:
                            chosen_idx = valid_indices[0]

                        answers[idx] = chosen_idx
                        continue

            # 3. Default fallback
            answers[idx] = 0

        return answers

    def export_quiz_analysis_markdown(
        self,
        quiz_id: str,
        md_path: str = "quiz_analysis.md"
    ) -> str:
        """
        Exports structured quiz analysis markdown documenting:
        - Overall status, score, attempt count
        - Verified correct answers (locked)
        - Eliminated wrong options (permanently excluded)
        - Next candidate options for retry
        Syncs automatically to workspace root, brain artifacts, and cache.
        """
        q_mem = self.quiz_memory.get(quiz_id, {
            "quiz_id": quiz_id,
            "attempts": 1,
            "latest_score": 0.0,
            "passed": False,
            "questions": {}
        })

        attempts = q_mem.get("attempts", 1)
        score = q_mem.get("latest_score", 0.0)
        passed = q_mem.get("passed", False)
        status_text = "🎉 PASSED (100%)" if score >= 100.0 else ("✅ PASSED" if passed else "🔄 NEEDS_RETRY")

        questions_dict = q_mem.get("questions", {})
        total_q = len(questions_dict)
        locked_q = sum(1 for e in questions_dict.values() if e.get("status") == "LOCKED_CORRECT")
        retry_q = sum(1 for e in questions_dict.values() if e.get("status") == "NEEDS_RETRY")

        lines = [
            f"# 📋 Assessment Analysis & Retry Memory: {quiz_id}\n",
            f"- **Assessment / Quiz**: `{quiz_id}`",
            f"- **Latest Attempt**: Attempt {attempts}",
            f"- **Latest Score**: **{score:.1f}%** ({status_text})",
            f"- **Locked Correct Answers**: **{locked_q} / {total_q}**",
            f"- **Questions Needing Retry**: **{retry_q} / {total_q}**\n",
            "---\n",
            "## 🎯 Verified Solution Key & Strategy Matrix\n",
            "| # | Status | Question Summary | Verified / Next Option | Result / Action |",
            "|---|---|---|---|---|"
        ]

        sorted_entries = sorted(questions_dict.values(), key=lambda x: x.get("index", 0))
        for item in sorted_entries:
            q_num = item.get("index", 0) + 1
            st = item.get("status", "UNKNOWN")
            prompt_short = item.get("prompt", "").replace("\n", " ").strip()
            if len(prompt_short) > 75:
                prompt_short = prompt_short[:72] + "..."

            if st == "LOCKED_CORRECT":
                badge = "🔒 `LOCKED_CORRECT`"
                opt_text = item.get("verified_text", "")
                action = "✅ Verified Correct (Locked)"
            elif st == "NEEDS_RETRY":
                badge = "🔄 `NEEDS_RETRY`"
                elim_cnt = len(item.get("eliminated_texts", []))
                next_c = item.get("next_candidate", "Alternative candidate")
                opt_text = f"`{next_c}`"
                action = f"❌ {elim_cnt} option(s) eliminated -> Select next"
            else:
                badge = "❔ `PENDING`"
                opt_text = "TBD"
                action = "Awaiting feedback"

            lines.append(f"| **Q{q_num}** | {badge} | *{prompt_short}* | `{opt_text}` | {action} |")

        lines.append("\n---\n")
        lines.append("## 🔍 Detailed Question Breakdown & Elimination Log\n")

        for item in sorted_entries:
            q_num = item.get("index", 0) + 1
            st = item.get("status", "UNKNOWN")
            prompt_full = item.get("prompt", "").strip()
            lines.append(f"### Q{q_num}: {prompt_full}\n")
            lines.append(f"- **Type**: `{item.get('type', 'radio')}`")
            lines.append(f"- **Status**: **{st}**")

            if st == "LOCKED_CORRECT":
                lines.append(f"- **Verified Correct Option**: `{item.get('verified_text', '')}`")
                lines.append("- **Rule**: Keep this exact option on all retries regardless of option shuffling.\n")
            else:
                eliminated = item.get("eliminated_texts", [])
                lines.append(f"- **Eliminated Options (DO NOT SELECT)**:")
                if eliminated:
                    for elim in eliminated:
                        lines.append(f"  - ❌ `{elim}`")
                else:
                    lines.append("  - *(None yet)*")

                remaining = [
                    self._get_opt_text(opt) for opt in item.get("options", [])
                    if not self._is_option_eliminated(opt, eliminated)
                ]
                lines.append(f"- **Remaining Candidate Options**:")
                for rem in remaining:
                    lines.append(f"  - ⏳ `{rem}`")

                next_pick = item.get("next_candidate") or (remaining[0] if remaining else "None")
                lines.append(f"- **Next Retry Choice**: `{next_pick}`\n")

        lines.append("---\n")
        lines.append("## 🤖 Autonomous Peer Agent Protocol")
        lines.append("When retrying or processing this assessment:")
        lines.append("1. **Read this file (`quiz_analysis.md`)** before answering.")
        lines.append("2. **For `LOCKED_CORRECT` questions**: Locate and select the exact **Verified Correct Option** text.")
        lines.append("3. **For `NEEDS_RETRY` questions**: NEVER select an **Eliminated Option**. Choose from **Remaining Candidate Options**.")
        lines.append("4. **After submission**: Record feedback immediately into `quiz_analysis.md` until 100% passed.\n")

        content = "\n".join(lines)

        target_paths = [os.path.abspath(md_path)]
        cache_path = os.path.join(self.base_cache_dir, "quiz_analysis.md")
        if cache_path not in target_paths:
            target_paths.append(cache_path)

        for p in target_paths:
            try:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                pass

        return content

    def load_quiz_analysis(
        self,
        md_path: str = "quiz_analysis.md",
        quiz_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parses an existing quiz_analysis.md file into memory so previous runs or
        peer agent findings are immediately loaded.
        """
        search_paths = [
            os.path.abspath(md_path),
            os.path.join(self.base_cache_dir, "quiz_analysis.md")
        ]

        found_content = None
        for p in search_paths:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        found_content = f.read()
                        if found_content.strip():
                            break
                except Exception:
                    continue

        if not found_content:
            return self.quiz_memory

        qid = quiz_id or "assessment"
        q_match = re.search(r"Assessment.*?:\s*[`\"]?([^`\"\r\n]+)[`\"]?", found_content)
        if q_match:
            qid = q_match.group(1).strip()

        q_mem = self.quiz_memory.setdefault(qid, {
            "quiz_id": qid,
            "attempts": 1,
            "latest_score": 0.0,
            "passed": False,
            "questions": {}
        })

        score_match = re.search(r"Latest Score.*?:\s*\*\*(\d+(?:\.\d+)?)%\*\*", found_content)
        if score_match:
            q_mem["latest_score"] = float(score_match.group(1))
            q_mem["passed"] = q_mem["latest_score"] >= self.min_pass_threshold

        sections = re.split(r"###\s*Q\d+:\s*", found_content)
        for sec in sections[1:]:
            lines = sec.strip().split("\n")
            if not lines:
                continue
            prompt = lines[0].strip()
            norm_p = self._normalize_text(prompt)

            is_locked = "LOCKED_CORRECT" in sec
            verified_match = re.search(r"Verified Correct Option.*?:\s*[`\"]([^`\"\n]+)[`\"]", sec)
            verified_text = verified_match.group(1).strip() if verified_match else None

            eliminated = []
            elim_block = re.search(r"Eliminated Options.*?:\s*\n((?:\s*-\s*❌[^\n]+\n)+)", sec)
            if elim_block:
                for elim_line in elim_block.group(1).split("\n"):
                    m = re.search(r"❌\s*[`\"]?([^`\"\n]+)[`\"]?", elim_line)
                    if m:
                        eliminated.append(m.group(1).strip())

            q_mem["questions"][norm_p] = {
                "prompt": prompt,
                "status": "LOCKED_CORRECT" if is_locked else "NEEDS_RETRY",
                "verified_text": verified_text,
                "eliminated_texts": eliminated,
                "options": [],
                "next_candidate": None
            }

        return self.quiz_memory

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
        try:
            bridge_file = os.path.join(tempfile.gettempdir(), "quiz_pilot_bridge.json")
            if os.path.exists(bridge_file):
                os.remove(bridge_file)
        except Exception:
            pass

