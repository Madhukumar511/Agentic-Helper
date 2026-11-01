"""
Answering-core regression tests (2026-11-01).

The old core guessed silently in five places and submitted around the 80%
gate: the adapter filled unanswered questions with option 0 / "0", the
scheduler and orchestrator default-filled missing answers with 0, retry
answers defaulted unknown questions to 0, AISolver fell back to [0], and
the scheduler recorded every attempt as attempt_num=1. On top of that,
quizzes could be re-attempted inside one run.

Policy now: abstain on unknowns, submit only at >= 80% known coverage
(below the gate ZERO attempts are used), real attempt numbers from saved
history, and at most ONE submitted attempt per quiz per run.
"""
import asyncio
import os

from quiz_pilot.attempt_protector import FastAttemptManager
from quiz_pilot.ai_solver import AISolver

OPTS = [{"text": "Alpha"}, {"text": "Beta"}, {"text": "Gamma"}]


def _mgr(tmp_path):
    return FastAttemptManager(base_cache_dir=str(tmp_path))


def test_retry_answers_abstain_on_unknown_questions(tmp_path):
    mgr = _mgr(tmp_path)
    known_q = [{"index": 0, "prompt": "Capital of France?", "options": OPTS}]
    mgr.record_attempt(
        quiz_id="GeoQuiz", attempt_num=1, questions=known_q,
        answers={0: 1}, feedback={0: True}, score_pct=100.0,
        md_path=str(tmp_path / "quiz_analysis.md"),
    )
    questions = known_q + [{"index": 1, "prompt": "Never seen before?", "options": OPTS}]
    answers = mgr.get_retry_answers(questions, quiz_id="GeoQuiz",
                                    md_path=str(tmp_path / "quiz_analysis.md"))
    assert answers.get(0) == 1          # verified answer locked in
    assert 1 not in answers             # unknown question: abstain, NOT default 0


def test_next_attempt_num_counts_saved_attempts(tmp_path):
    mgr = _mgr(tmp_path)
    assert mgr.next_attempt_num("FreshQuiz") == 1
    qs = [{"index": 0, "prompt": "Q?", "options": OPTS}]
    mgr.save_attempt(quiz_id="CountedQuiz", attempt_num=1, questions=qs, answers={0: 0})
    mgr.save_attempt(quiz_id="CountedQuiz", attempt_num=2, questions=qs, answers={0: 0})
    assert mgr.next_attempt_num("CountedQuiz") == 3


def test_ai_solver_abstains_without_key():
    solver = AISolver(api_key=None)
    out = solver.solve_question({"prompt": "2+2?", "options": OPTS})
    assert out["selected_indices"] == []   # abstain - previously [0] (a guess)
    assert out["confidence"] == 0.0


class _FakePage:
    def __init__(self, url="https://www.coursera.org/learn/demo-course/exam/1"):
        self.url = url

    async def title(self):
        return "Gate Quiz"

    async def evaluate(self, *a, **k):
        raise RuntimeError("no JS in fake page")

    async def goto(self, *a, **k):
        raise RuntimeError("no nav in fake page")

    async def wait_for_selector(self, *a, **k):
        raise RuntimeError("no DOM in fake page")


class _FakeAdapter:
    def __init__(self, n_questions=5):
        self.questions = [
            {"index": i, "prompt": f"Q{i}?", "options": OPTS} for i in range(n_questions)
        ]
        self.filled = None
        self.submitted = False

    async def extract_questions_async(self):
        return self.questions

    async def batch_fill_answers_async(self, answers, auto_submit=False):
        self.filled = dict(answers)
        return {str(k): True for k in answers}

    async def submit_assessment_async(self):
        self.submitted = True
        return True

    async def extract_feedback_async(self):
        return {"score_pct": 100.0, "passed": True,
                "feedback": {q["index"]: True for q in self.questions}}


def _run_scheduler(tmp_path, monkeypatch, generator):
    import quiz_pilot.tab_scheduler as ts_mod
    from quiz_pilot.tab_scheduler import AsyncTabScheduler

    adapter = _FakeAdapter()
    monkeypatch.setattr(ts_mod, "get_lms_adapter", lambda page: adapter)
    monkeypatch.chdir(tmp_path)
    sched = AsyncTabScheduler()
    sched.attempt_mgr = _mgr(tmp_path)
    result = asyncio.run(sched._process_single_tab(
        _FakePage(), tab_index=0, semaphore=asyncio.Semaphore(1),
        answer_generator=generator, auto_submit=True,
    ))
    return sched, adapter, result


def test_scheduler_gate_blocks_submit_below_80_percent(tmp_path, monkeypatch):
    gen = lambda qs: {0: 0, 1: 1}  # knows 2 of 5 = 40%
    _, adapter, result = _run_scheduler(tmp_path, monkeypatch, gen)
    assert result["status"] == "NEEDS_REVIEW_NOT_SUBMITTED"
    assert result["submitted"] is False
    assert adapter.submitted is False          # zero attempts burned
    assert result["coverage_pct"] == 40.0
    assert result["unknown_questions"] == [2, 3, 4]
    assert adapter.filled == {0: 0, 1: 1}      # known answers still filled
    # Unknowns come back WITH their text so the driving agent can solve
    # them itself and complete the quiz in the same run (agent-only rule)
    detail = result["unknown_questions_detail"]
    assert [d["index"] for d in detail] == [2, 3, 4]
    assert detail[0]["prompt"] == "Q2?"
    assert detail[0]["options"] == ["Alpha", "Beta", "Gamma"]


def test_scheduler_submits_above_gate_and_records_real_attempt_numbers(tmp_path, monkeypatch):
    gen = lambda qs: {0: 0, 1: 1, 2: 2, 3: 0}  # 4 of 5 = 80%
    _, adapter, result = _run_scheduler(tmp_path, monkeypatch, gen)
    assert adapter.submitted is True
    assert result["status"] in ("PASSED", "COMPLETED")
    files = [f for f in os.listdir(tmp_path) if "_attempt_" in f]
    assert any(f.endswith("_attempt_1.json") for f in files), files

    # Second run: the recorded attempt must be number 2, not a fake "1" again
    _, adapter2, result2 = _run_scheduler(tmp_path, monkeypatch, gen)
    assert adapter2.submitted is True
    files = [f for f in os.listdir(tmp_path) if "_attempt_" in f]
    assert any(f.endswith("_attempt_2.json") for f in files), files


def test_orchestrator_single_attempt_guard():
    from quiz_pilot.course_orchestrator import CourseOrchestrator

    orch = CourseOrchestrator()
    orch._run_attempted_quizzes.add("Quiz X")
    item = {"title": "Quiz X", "type": "quiz",
            "url": "https://www.coursera.org/learn/demo/quiz/1"}
    res = asyncio.run(orch._solve_item_on_page(_FakePage(), item))
    assert res["status"] == "skipped_single_attempt_policy"
