"""
Tests for question quality checks.
No API access required — all checks are pure functions on dicts.

Run with pytest or directly:  python src/tests/test_question_quality.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "llm"))
from question_quality import (
    normalize_question_text,
    check_duplicate_questions,
    check_duplicate_options,
    check_similar_questions,
    check_cross_batch_duplicates,
    check_cross_batch_similar,
    run_per_batch_gate,
    run_quality_checks,
    format_quality_log,
    SIMILAR_QUESTION_THRESHOLD,
    HARD_REJECT_SIMILARITY,
    ISSUE_DUPLICATE_QUESTION,
    ISSUE_DUPLICATE_OPTIONS,
    ISSUE_SIMILAR_QUESTIONS,
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

# France/Germany pair: Jaccard ≈ 5/7 ≈ 0.714 — in [0.70, 0.85) → warning
FRANCE_Q  = _q("What is the capital of France?")
GERMANY_Q = _q("What is the capital of Germany?")

# High-overlap pair: Jaccard = 12/14 ≈ 0.857 — ≥ 0.85 → hard reject
_HIGH_A = "What is the important central role of Python in modern data science programming?"
_HIGH_B = "What is the important central role of Java in modern data science programming?"
HIGH_SIM_Q1 = _q(_HIGH_A)
HIGH_SIM_Q2 = _q(_HIGH_B)


# ── normalize_question_text ───────────────────────────────────────────────────

def test_normalize_lowercases():
    assert normalize_question_text("HELLO WORLD") == "hello world"


def test_normalize_strips_whitespace():
    assert normalize_question_text("  hello  ") == "hello"


def test_normalize_collapses_internal_spaces():
    assert normalize_question_text("hello   world") == "hello world"


def test_normalize_empty_string():
    assert normalize_question_text("") == ""


def test_normalize_combined():
    assert normalize_question_text("  What  Is  Python?  ") == "what is python?"


# ── check_duplicate_questions ─────────────────────────────────────────────────

def test_no_duplicates_returns_empty():
    assert check_duplicate_questions(CLEAN_QUIZ) == []


def test_exact_duplicate_detected():
    questions = [_q("What is Python?"), _q("What is a list?"), _q("What is Python?")]
    issues = check_duplicate_questions(questions)
    assert len(issues) == 1
    assert issues[0]["issue_type"] == ISSUE_DUPLICATE_QUESTION
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
    assert issues[0]["issue_type"] == ISSUE_DUPLICATE_OPTIONS
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


def test_similar_pair_detected_as_warning():
    issues = check_similar_questions([FRANCE_Q, GERMANY_Q, _q("How does Python handle memory?")])
    # France/Germany ≈ 0.714 — in warning range [0.70, 0.85)
    assert any(
        i["issue_type"] == ISSUE_SIMILAR_QUESTIONS
        and i["severity"] == "warning"
        and set(i["question_indices"]) == {0, 1}
        for i in issues
    )


def test_high_similarity_triggers_error():
    issues = check_similar_questions([HIGH_SIM_Q1, HIGH_SIM_Q2])
    assert any(
        i["issue_type"] == ISSUE_SIMILAR_QUESTIONS and i["severity"] == "error"
        for i in issues
    )


def test_warn_threshold_respected():
    # France/Germany at 0.714 — below 0.99 warn_threshold → no issue
    issues_high = check_similar_questions([FRANCE_Q, GERMANY_Q], warn_threshold=0.99)
    # France/Germany at 0.714 — above 0.01 warn_threshold → warning
    issues_low  = check_similar_questions([FRANCE_Q, GERMANY_Q], warn_threshold=0.01)
    assert len(issues_high) == 0
    assert len(issues_low) > 0


def test_identical_texts_are_hard_reject():
    questions = [_q("Same question text here"), _q("Same question text here")]
    issues = check_similar_questions(questions)
    # score = 1.0 >= HARD_REJECT_SIMILARITY → error
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"


def test_custom_hard_threshold():
    # France/Germany ≈ 0.714 — above custom hard_threshold=0.5 → error
    issues = check_similar_questions([FRANCE_Q, GERMANY_Q], hard_threshold=0.5, warn_threshold=0.3)
    assert any(i["severity"] == "error" for i in issues)


# ── check_cross_batch_duplicates ──────────────────────────────────────────────

def test_cross_batch_dup_empty_accumulated():
    assert check_cross_batch_duplicates([_q("New question?")], []) == []


def test_cross_batch_dup_no_match():
    issues = check_cross_batch_duplicates(
        [_q("What is Python?")],
        [_q("What is a list?"), _q("What is a dict?")],
    )
    assert issues == []


def test_cross_batch_dup_exact_match():
    issues = check_cross_batch_duplicates(
        [_q("What is Python?")],
        [_q("What is Python?")],
    )
    assert len(issues) == 1
    assert issues[0]["issue_type"] == ISSUE_DUPLICATE_QUESTION
    assert issues[0]["severity"] == "error"


def test_cross_batch_dup_case_insensitive():
    issues = check_cross_batch_duplicates(
        [_q("WHAT IS PYTHON?")],
        [_q("what is python?")],
    )
    assert len(issues) == 1


def test_cross_batch_dup_multiple_new_only_one_matches():
    issues = check_cross_batch_duplicates(
        [_q("What is Python?"), _q("What is a list?")],
        [_q("What is Python?"), _q("What is a dict?")],
    )
    assert len(issues) == 1


# ── check_cross_batch_similar ─────────────────────────────────────────────────

def test_cross_batch_similar_empty_accumulated():
    assert check_cross_batch_similar([FRANCE_Q], []) == []


def test_cross_batch_similar_no_match():
    issues = check_cross_batch_similar(
        [_q("How does Python handle memory?")],
        [_q("What is a list?")],
    )
    assert issues == []


def test_cross_batch_similar_warning_default_thresholds():
    # France/Germany ≈ 0.714 — in [SIMILAR_QUESTION_THRESHOLD, HARD_REJECT_SIMILARITY)
    issues = check_cross_batch_similar([FRANCE_Q], [GERMANY_Q])
    assert any(
        i["issue_type"] == ISSUE_SIMILAR_QUESTIONS and i["severity"] == "warning"
        for i in issues
    )


def test_cross_batch_similar_hard_reject_default_thresholds():
    # HIGH_SIM_Q1 vs HIGH_SIM_Q2: Jaccard ≈ 0.857 — ≥ HARD_REJECT_SIMILARITY
    issues = check_cross_batch_similar([HIGH_SIM_Q1], [HIGH_SIM_Q2])
    assert any(
        i["issue_type"] == ISSUE_SIMILAR_QUESTIONS and i["severity"] == "error"
        for i in issues
    )


def test_cross_batch_similar_custom_hard_threshold():
    # France/Germany ≈ 0.714 — above custom hard_threshold=0.5 → error
    issues = check_cross_batch_similar([FRANCE_Q], [GERMANY_Q], hard_threshold=0.5, warn_threshold=0.3)
    assert any(i["severity"] == "error" for i in issues)


def test_cross_batch_similar_no_issue_below_warn_threshold():
    issues = check_cross_batch_similar([FRANCE_Q], [GERMANY_Q], hard_threshold=0.99, warn_threshold=0.99)
    # France/Germany ≈ 0.714 — below both thresholds
    assert issues == []


# ── run_per_batch_gate ────────────────────────────────────────────────────────

def test_gate_empty_new_questions():
    assert run_per_batch_gate([], [_q("Something")]) == []


def test_gate_clean_batch_empty_accumulated():
    assert run_per_batch_gate(CLEAN_QUIZ, []) == []


def test_gate_clean_batch_different_accumulated():
    acc = [_q("How does Python handle memory?"), _q("What is a generator?")]
    assert run_per_batch_gate(CLEAN_QUIZ, acc) == []


def test_gate_cross_batch_duplicate_is_error():
    acc = [_q("What is Python?"), _q("What is a list?")]
    new_batch = [_q("What is Python?")]   # exact duplicate of acc[0]
    issues = run_per_batch_gate(new_batch, acc)
    assert any(i["severity"] == "error" for i in issues)


def test_gate_within_batch_duplicate_is_error():
    new_batch = [_q("What is Python?"), _q("What is Python?")]
    issues = run_per_batch_gate(new_batch, [])
    assert any(i["severity"] == "error" and i["issue_type"] == ISSUE_DUPLICATE_QUESTION for i in issues)


def test_gate_duplicate_options_is_error():
    new_batch = [_q("Q?", options=["A", "B", "A", "D"])]
    issues = run_per_batch_gate(new_batch, [])
    assert any(i["severity"] == "error" and i["issue_type"] == ISSUE_DUPLICATE_OPTIONS for i in issues)


def test_gate_warning_only_no_hard_reject():
    # France/Germany ≈ 0.714 — warning only (within-batch pair)
    new_batch = [FRANCE_Q, GERMANY_Q]
    issues = run_per_batch_gate(new_batch, [])
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    assert len(errors) == 0
    assert len(warnings) > 0


def test_gate_cross_batch_high_similarity_is_error():
    # HIGH_SIM pairs: Jaccard ≈ 0.857 — hard reject
    issues = run_per_batch_gate([HIGH_SIM_Q1], [HIGH_SIM_Q2])
    assert any(i["severity"] == "error" for i in issues)


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
        FRANCE_Q,
        GERMANY_Q,                                      # similar to France at warn threshold
    ]
    issues = run_quality_checks(questions, similar_threshold=0.5)
    types = {i["issue_type"] for i in issues}
    assert ISSUE_DUPLICATE_QUESTION in types
    assert ISSUE_DUPLICATE_OPTIONS   in types
    assert ISSUE_SIMILAR_QUESTIONS   in types


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
