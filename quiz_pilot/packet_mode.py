"""
Host-Packet mode: the token-efficient answering path.

The problem it solves: in the classic flow the host agent (the IDE's AI)
receives the FULL quiz several times per attempt - extraction, memory
check, solving, filling, recording - so most of its tokens are spent
re-reading questions the tool already knows the answers to.

Packet flow instead:
1. prepare: the server extracts the questions ONCE and pre-solves every
   question it can answer with CERTAINTY from its own memory - only
   answers Coursera/LMS feedback has previously marked correct
   (LOCKED_CORRECT), re-matched to the current options by text so option
   shuffling is safe. Elimination candidates are NEVER auto-answered:
   they are hints for the agent, not knowledge.
2. The host receives ONE compact packet containing only the unresolved
   questions (index, type, full prompt, full options, which options are
   already eliminated by earlier feedback, images when present).
3. apply: the host returns answers for just those questions; the server
   validates them, merges them with the locked answers, enforces the
   same 80% coverage floor as every other submit path, fills, submits,
   records the feedback, and returns a short receipt. On failure the
   next prepare produces a DELTA packet: newly-correct questions move
   to the locked set and only the still-wrong questions travel again.

Packet state is kept on disk (one JSON per packet) so prepare and apply
can happen in separate tool calls - or even separate server processes -
without the question set ever crossing the host boundary again.
"""

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from quiz_pilot.attempt_protector import FastAttemptManager


class PacketManager:
    """Builds packets, persists packet state, merges host answers."""

    def __init__(self, attempt_mgr: FastAttemptManager, state_dir: Optional[str] = None):
        self.mgr = attempt_mgr
        self.state_dir = state_dir or os.path.join(attempt_mgr.base_cache_dir, "packets")
        os.makedirs(self.state_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # state persistence
    # ------------------------------------------------------------------
    def _state_path(self, packet_id: str) -> str:
        safe = "".join(c for c in str(packet_id) if c.isalnum() or c in "-_")
        return os.path.join(self.state_dir, f"{safe}.json")

    def _save_state(self, state: Dict[str, Any]) -> None:
        with open(self._state_path(state["packet_id"]), "w", encoding="utf-8") as f:
            json.dump(state, f, separators=(",", ":"))

    def load_state(self, packet_id: str) -> Optional[Dict[str, Any]]:
        try:
            with open(self._state_path(packet_id), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def delete_state(self, packet_id: str) -> None:
        try:
            os.remove(self._state_path(packet_id))
        except OSError:
            pass

    # ------------------------------------------------------------------
    # memory lookup (verified answers only)
    # ------------------------------------------------------------------
    def _match_entry(self, bucket: Optional[Dict[str, Any]], norm_prompt: str) -> Optional[Dict[str, Any]]:
        if not bucket or not norm_prompt:
            return None
        questions = bucket.get("questions", {})
        if norm_prompt in questions:
            return questions[norm_prompt]
        for key, entry in questions.items():
            if norm_prompt in key or key in norm_prompt:
                return entry
        return None

    def _verified_entry(self, quiz_id: str, norm_prompt: str) -> Optional[Dict[str, Any]]:
        """Finds a LOCKED_CORRECT memory entry for this prompt: this quiz's
        bucket first, then any other quiz's bucket (a verified-correct
        answer to the identical question is safe to reuse anywhere; an
        elimination hint is NOT carried across quizzes)."""
        memory = self.mgr.quiz_memory or {}
        entry = self._match_entry(memory.get(quiz_id), norm_prompt)
        if entry and entry.get("status") == "LOCKED_CORRECT" and entry.get("verified_text"):
            return entry
        for other_id, bucket in memory.items():
            if other_id == quiz_id:
                continue
            entry = self._match_entry(bucket, norm_prompt)
            if entry and entry.get("status") == "LOCKED_CORRECT" and entry.get("verified_text"):
                return entry
        return None

    # ------------------------------------------------------------------
    # prepare
    # ------------------------------------------------------------------
    def build_packet(self, quiz_id: str, questions: List[Dict[str, Any]],
                     md_path: str = "quiz_analysis.md") -> Dict[str, Any]:
        mgr = self.mgr
        if not mgr.quiz_memory or quiz_id not in mgr.quiz_memory:
            try:
                mgr.load_quiz_analysis(md_path=md_path, quiz_id=quiz_id)
            except Exception:
                pass

        known: Dict[int, Any] = {}
        unknown_items: List[Dict[str, Any]] = []
        unknown_indices: List[int] = []

        for q in questions:
            idx = q.get("index", 0)
            options = q.get("options", [])
            opt_texts = [mgr._get_opt_text(o) for o in options]
            norm_prompt = mgr._normalize_text(q.get("prompt", ""))

            verified = self._verified_entry(quiz_id, norm_prompt)
            if verified is not None:
                v_text = verified.get("verified_text")
                if options:
                    opt_idx = mgr._match_option_by_text(v_text, options)
                    if opt_idx is not None:
                        known[idx] = opt_idx
                        continue
                else:
                    # Text/number question: the verified value itself.
                    known[idx] = v_text
                    continue
                # Options exist but the verified text no longer matches
                # any of them (question changed): fall through and let
                # the host re-solve it rather than forcing a stale answer.

            entry = self._match_entry((mgr.quiz_memory or {}).get(quiz_id), norm_prompt)
            eliminated: List[int] = []
            if entry:
                elim_texts = entry.get("eliminated_texts", [])
                eliminated = [
                    j for j, o in enumerate(options)
                    if mgr._is_option_eliminated(o, elim_texts)
                ]
            item: Dict[str, Any] = {
                "i": idx,
                "t": q.get("type", "radio"),
                "q": q.get("prompt", ""),
                "o": opt_texts,
            }
            if eliminated:
                item["e"] = eliminated
            images = q.get("images") or []
            if images:
                item["img"] = images
            unknown_items.append(item)
            unknown_indices.append(idx)

        seed = f"{quiz_id}|{time.time()}|{len(questions)}"
        packet_id = "pkt-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        state = {
            "packet_id": packet_id,
            "quiz_id": quiz_id,
            "total": len(questions),
            "questions": questions,
            "known": {str(k): v for k, v in known.items()},
            "unknown_indices": unknown_indices,
        }
        self._save_state(state)

        return {
            "packet_id": packet_id,
            "quiz_id": quiz_id,
            "total": len(questions),
            "known_count": len(known),
            "unknown_count": len(unknown_items),
            "ready": len(unknown_items) == 0,
            "questions": unknown_items,
        }

    # ------------------------------------------------------------------
    # apply: validate + merge the host's answers
    # ------------------------------------------------------------------
    def _validate_value(self, q: Dict[str, Any], value: Any) -> Any:
        """Normalizes one host answer to the fill value, or raises ValueError.
        Accepts option indices, option texts, lists (multi-select), and raw
        strings/numbers for text/number questions."""
        mgr = self.mgr
        options = q.get("options", [])
        if isinstance(value, list):
            return [self._validate_single(q, v) for v in value]
        return self._validate_single(q, value)

    def _validate_single(self, q: Dict[str, Any], value: Any) -> Any:
        mgr = self.mgr
        options = q.get("options", [])
        if isinstance(value, bool):
            raise ValueError("boolean is not a valid answer value")
        if isinstance(value, int):
            if options and not (0 <= value < len(options)):
                raise ValueError(f"option index {value} out of range (0..{len(options) - 1})")
            return value
        if isinstance(value, float) and float(value).is_integer():
            return self._validate_single(q, int(value))
        if isinstance(value, str):
            if options:
                opt_idx = mgr._match_option_by_text(value, options)
                if opt_idx is None:
                    raise ValueError(f"answer text does not match any option: {value!r}")
                return opt_idx
            return value
        raise ValueError(f"unsupported answer value type: {type(value).__name__}")

    def merge_answers(self, state: Dict[str, Any], host_answers: Any) -> Dict[str, Any]:
        """Merges the host's answers into the packet's locked answers.

        host_answers may be a map {index: value} or a compact list of
        [index, value] pairs. Answers aimed at locked questions are
        IGNORED (verified answers are never overridden); invalid values
        are reported, never guessed around."""
        if isinstance(host_answers, list):
            pairs = {}
            for pair in host_answers:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    pairs[pair[0]] = pair[1]
            host_answers = pairs
        if not isinstance(host_answers, dict):
            host_answers = {}

        questions = state.get("questions", [])
        by_index = {q.get("index", 0): q for q in questions}
        answers: Dict[int, Any] = {}
        for k, v in (state.get("known") or {}).items():
            try:
                answers[int(k)] = v
            except (TypeError, ValueError):
                pass

        accepted = 0
        ignored_locked: List[int] = []
        errors: List[str] = []
        for raw_idx, value in host_answers.items():
            try:
                idx = int(raw_idx)
            except (TypeError, ValueError):
                errors.append(f"bad question index: {raw_idx!r}")
                continue
            if idx in answers:
                ignored_locked.append(idx)
                continue
            q = by_index.get(idx)
            if q is None:
                errors.append(f"unknown question index: {idx}")
                continue
            try:
                answers[idx] = self._validate_value(q, value)
                accepted += 1
            except ValueError as exc:
                errors.append(f"Q{idx}: {exc}")

        total = state.get("total") or len(questions)
        remaining = [q.get("index", 0) for q in questions if q.get("index", 0) not in answers]
        coverage = round(100.0 * len(answers) / total, 1) if total else 100.0
        return {
            "answers": answers,
            "accepted": accepted,
            "ignored_locked": ignored_locked,
            "errors": errors,
            "remaining_unknown": remaining,
            "coverage_pct": coverage,
            "total": total,
        }
