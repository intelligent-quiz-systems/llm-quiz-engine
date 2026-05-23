"""
Tests for question quality checks.
No API access required — all checks are pure functions on dicts.

Run with pytest or directly:  python src/tests/test_question_quality.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "llm"))
from question_quality import (
    check_duplicate_questions,
    check_duplicate_options,
    check_similar_questions,
    run_quality_checks,
    format_quality_log,
    SIMILAR_QUESTION_THRESHOLD,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _q(text: str, options: list[str] | None = None, correct: int = 0) -> dict:
    return {
        "question": text,
        "options": options or ["A", "B", "C", "D"],
        "correct_index": correct,
    }


CLEAN_QUIZ = [
    _q("What is Python?"),
    _q("What is a list?"),
    _q("What is a dict?"),
]


# ── check_duplicate_questions ─────────────────────────────────────────────────

def test_no_duplicates_returns_empty():
    assert check_duplicate_questions(CLEAN_QUIZ) == []


def test_exact_duplicate_detected():
    questions = [_q("What is Python?"), _q("What is a list?"), _q("What is Python?")]
    issues = check_duplicate_questions(questions)
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "duplicate_question"
    assert issues[0]["severity"] == "error"
    assert 0 in issues[0]["question_indices"]
    assert 2 in issues[0]["question_indices"]


def test_case_insensitive_duplicate():
    questions = [_q("What Is Python?"), _q("what is python?")]
    issues = check_duplicate_questions(questions)
    assert len(issues) == 1


def test_whitespace_normalized_duplicate():
    questions = [_q("What  is   Python?"), _q("What is Python?")]
    issues = check_duplicate_questions(questions)
    assert len(issues) == 1


# ── check_duplicate_options ───────────────────────────────────────────────────

def test_no_duplicate_options_clean():
    assert check_duplicate_options(CLEAN_QUIZ) == []


def test_duplicate_options_detected():
    questions = [_q("Q?", options=["A", "B", "A", "D"])]
    issues = check_duplicate_options(questions)
    assert len(issues) == 1
    assert issues[0]["issue_type"] == "duplicate_options"
    assert issues[0]["severity"] == "error"
    assert 0 in issues[0]["question_indices"]


def test_duplicate_options_case_insensitive():
    questions = [_q("Q?", options=["yes", "No", "YES", "maybe"])]
    issues = check_duplicate_options(questions)
    assert len(issues) == 1


def test_duplicate_options_only_flags_affected_question():
    questions = [
        _q("Clean question?", options=["A", "B", "C", "D"]),
        _q("Dupl question?",  options=["X", "Y", "X", "Z"]),
    ]
    issues = check_duplicate_options(questions)
    assert len(issues) == 1
    assert issues[0]["question_indices"] == [1]


# ── check_similar_questions ───────────────────────────────────────────────────

def test_no_similar_questions():
    assert check_similar_questions(CLEAN_QUIZ) == []


def test_similar_pair_detected():
    questions = [
        _q("What is the capital of France?"),
        _q("What is the capital of Germany?"),
        _q("How does Python handle memory?"),
    ]
    issues = check_similar_questions(questions, threshold=0.5)
    assert any(
        i["issue_type"] == "similar_questions"
        and set(i["question_indices"]) == {0, 1}
        for i in issues
    )


def test_threshold_respected():
    questions = [_q("What is Python?"), _q("What is Java?")]
    # Very high threshold — these might not reach 0.99
    issues_high = check_similar_questions(questions, threshold=0.99)
    issues_low  = check_similar_questions(questions, threshold=0.01)
    assert len(issues_high) == 0 or len(issues_high) <= len(issues_low)


def test_identical_texts_flagged_as_similar():
    questions = [_q("Same question text here"), _q("Same question text here")]
    issues = check_similar_questions(questions, threshold=SIMILAR_QUESTION_THRESHOLD)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"


# ── run_quality_checks ────────────────────────────────────────────────────────

def test_empty_questions_returns_empty():
    assert run_quality_checks([]) == []


def test_clean_quiz_no_issues():
    assert run_quality_checks(CLEAN_QUIZ) == []


def test_all_checks_combined():
    questions = [
        _q("What is Python?"),                          # original
        _q("What is Python?"),                          # duplicate of 0
        _q("Q?", options=["A", "B", "A", "D"]),        # duplicate options
        _q("What is the capital of France?"),
        _q("What is the capital of Germany?"),          # similar to 3
    ]
    issues = run_quality_checks(questions, similar_threshold=0.5)
    types = {i["issue_type"] for i in issues}
    assert "duplicate_question" in types
    assert "duplicate_options"  in types
    assert "similar_questions"  in types


# ── format_quality_log ────────────────────────────────────────────────────────

def test_format_log_contains_header():
    questions = [_q("Q?"), _q("Q?")]
    issues = run_quality_checks(questions)
    log = format_quality_log(issues)
    assert "===== QUALITY ISSUES =====" in log
    assert "duplicate_question" in log


def test_format_log_empty_issues():
    log = format_quality_log([])
    assert "0" in log


# ── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in tests:
        try:
            fn()
            print(f"  OK  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{passed}/{len(tests)} passed.")
