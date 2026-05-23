"""
Tests for guardrail context builder.
No API access required — all functions are pure.

Run with pytest or directly:  python src/tests/test_guardrail.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "llm"))
from guardrail import (
    build_guardrail_context,
    extract_question_texts,
    format_guardrail_log,
    GUARDRAIL_MAX_QUESTIONS,
)


# ── build_guardrail_context ───────────────────────────────────────────────────

def test_empty_list_returns_none_text():
    ctx = build_guardrail_context([])
    assert ctx["question_count"] == 0
    assert ctx["truncated"] is False
    assert ctx["text"] == "(none)"
    assert ctx["chars"] > 0


def test_single_question():
    ctx = build_guardrail_context(["What is Python?"])
    assert ctx["question_count"] == 1
    assert "What is Python?" in ctx["text"]
    assert ctx["text"].startswith("- ")
    assert ctx["truncated"] is False


def test_multiple_questions_formatted():
    qs = ["Question A", "Question B", "Question C"]
    ctx = build_guardrail_context(qs)
    assert ctx["question_count"] == 3
    lines = ctx["text"].splitlines()
    assert all(line.startswith("- ") for line in lines)
    assert len(lines) == 3


def test_max_questions_cap():
    qs = [f"Question {i}" for i in range(20)]
    ctx = build_guardrail_context(qs, max_questions=5)
    assert ctx["question_count"] == 5
    assert ctx["truncated"] is True


def test_no_truncation_when_within_limit():
    qs = ["Q1", "Q2", "Q3"]
    ctx = build_guardrail_context(qs, max_questions=10)
    assert ctx["truncated"] is False
    assert ctx["question_count"] == 3


def test_takes_most_recent_questions():
    qs = [f"Question {i}" for i in range(15)]
    ctx = build_guardrail_context(qs, max_questions=3)
    # Should take qs[12], qs[13], qs[14]
    assert "Question 14" in ctx["text"]
    assert "Question 12" in ctx["text"]
    assert "Question 0" not in ctx["text"]


def test_chars_matches_text_length():
    qs = ["What is Python?", "What is a list?"]
    ctx = build_guardrail_context(qs)
    assert ctx["chars"] == len(ctx["text"])


def test_whitespace_stripped_from_questions():
    qs = ["  Leading space ", "Trailing space  "]
    ctx = build_guardrail_context(qs)
    assert "  Leading" not in ctx["text"]
    for line in ctx["text"].splitlines():
        assert line == line.rstrip()


def test_empty_string_questions_skipped():
    qs = ["Valid question", "", "   "]
    ctx = build_guardrail_context(qs)
    assert ctx["question_count"] == 1


def test_default_max_matches_config():
    assert GUARDRAIL_MAX_QUESTIONS == 10


# ── extract_question_texts ────────────────────────────────────────────────────

def test_extract_from_quiz_dict():
    quiz = {
        "questions": [
            {"question": "What is Python?", "options": ["A","B","C","D"], "correct_index": 0},
            {"question": "What is a list?", "options": ["A","B","C","D"], "correct_index": 1},
        ]
    }
    texts = extract_question_texts(quiz)
    assert len(texts) == 2
    assert "What is Python?" in texts


def test_extract_from_empty_quiz():
    assert extract_question_texts({}) == []
    assert extract_question_texts({"questions": []}) == []


def test_extract_ignores_missing_question_field():
    quiz = {"questions": [{"options": ["A","B","C","D"], "correct_index": 0}]}
    texts = extract_question_texts(quiz)
    assert texts == []


# ── format_guardrail_log ──────────────────────────────────────────────────────

def test_format_log_contains_key_fields():
    ctx = build_guardrail_context(["Q1", "Q2"])
    log = format_guardrail_log(ctx)
    assert "guardrail_question_count" in log
    assert "guardrail_chars" in log
    assert "guardrail_truncated" in log


def test_format_log_shows_correct_values():
    ctx = build_guardrail_context(["Q1"])
    log = format_guardrail_log(ctx)
    assert "1" in log
    assert "False" in log


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
