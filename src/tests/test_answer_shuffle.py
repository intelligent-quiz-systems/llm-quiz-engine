"""
Tests for answer option shuffling.
No API access required — all functions are pure transformations on dicts.

Run with pytest or directly:  python src/tests/test_answer_shuffle.py
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "llm"))
from answer_shuffle import shuffle_options, shuffle_quiz_options


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _q(question: str, options: list[str], correct_index: int) -> dict:
    return {"question": question, "options": options, "correct_index": correct_index}


# ── shuffle_options — correctness ─────────────────────────────────────────────

def test_correct_answer_preserved_after_shuffle():
    q = _q("Q?", ["wrong1", "wrong2", "correct", "wrong3"], correct_index=2)
    rng = random.Random(42)
    result = shuffle_options(q, rng=rng)
    assert result["options"][result["correct_index"]] == "correct"


def test_all_options_still_present():
    q = _q("Q?", ["A", "B", "C", "D"], correct_index=0)
    result = shuffle_options(q, rng=random.Random(7))
    assert sorted(result["options"]) == sorted(q["options"])


def test_option_count_unchanged():
    q = _q("Q?", ["A", "B", "C", "D"], correct_index=1)
    result = shuffle_options(q, rng=random.Random(99))
    assert len(result["options"]) == 4


def test_original_dict_not_mutated():
    q = _q("Q?", ["A", "B", "C", "D"], correct_index=2)
    original_options = list(q["options"])
    original_index = q["correct_index"]
    shuffle_options(q, rng=random.Random(1))
    assert q["options"] == original_options
    assert q["correct_index"] == original_index


def test_correct_index_at_position_zero():
    q = _q("Q?", ["right", "w1", "w2", "w3"], correct_index=0)
    for seed in range(20):
        result = shuffle_options(q, rng=random.Random(seed))
        assert result["options"][result["correct_index"]] == "right"


def test_correct_index_at_last_position():
    q = _q("Q?", ["w1", "w2", "w3", "right"], correct_index=3)
    for seed in range(20):
        result = shuffle_options(q, rng=random.Random(seed))
        assert result["options"][result["correct_index"]] == "right"


def test_deterministic_with_same_seed():
    q = _q("Q?", ["A", "B", "C", "D"], correct_index=1)
    r1 = shuffle_options(q, rng=random.Random(42))
    r2 = shuffle_options(q, rng=random.Random(42))
    assert r1["options"] == r2["options"]
    assert r1["correct_index"] == r2["correct_index"]


def test_different_seeds_may_differ():
    q = _q("Q?", ["A", "B", "C", "D"], correct_index=1)
    results = [shuffle_options(q, rng=random.Random(s))["options"] for s in range(50)]
    assert len(set(tuple(r) for r in results)) > 1  # at least some variation


# ── shuffle_options — duplicate option strings ────────────────────────────────

def test_duplicate_options_correct_index_tracked_by_position():
    # Two identical strings: correct is at index 1, not index 0
    q = _q("Q?", ["same", "same", "wrong", "wrong"], correct_index=1)
    for seed in range(30):
        result = shuffle_options(q, rng=random.Random(seed))
        # The correct answer is the string "same" — verify index points to "same"
        assert result["options"][result["correct_index"]] == "same"


# ── shuffle_options — pass-through on invalid input ───────────────────────────

def test_passthrough_on_empty_options():
    q = {"question": "Q?", "options": [], "correct_index": 0}
    assert shuffle_options(q) is q


def test_passthrough_on_single_option():
    q = _q("Q?", ["only"], correct_index=0)
    assert shuffle_options(q) is q


def test_passthrough_on_out_of_range_index():
    q = _q("Q?", ["A", "B", "C", "D"], correct_index=10)
    assert shuffle_options(q) is q


def test_passthrough_on_negative_index():
    q = _q("Q?", ["A", "B", "C", "D"], correct_index=-1)
    assert shuffle_options(q) is q


def test_passthrough_on_non_list_options():
    q = {"question": "Q?", "options": "not a list", "correct_index": 0}
    assert shuffle_options(q) is q


def test_passthrough_preserves_extra_fields():
    q = {"question": "Q?", "options": ["A"], "correct_index": 0, "extra_field": "preserved"}
    result = shuffle_options(q)
    assert result["extra_field"] == "preserved"


# ── shuffle_quiz_options ──────────────────────────────────────────────────────

def test_quiz_all_questions_shuffled():
    quiz = {
        "quiz_title": "Test",
        "questions": [
            _q("Q1?", ["A", "B", "C", "D"], correct_index=0),   # correct = "A"
            _q("Q2?", ["W", "X", "Y", "Z"], correct_index=3),   # correct = "Z"
        ],
    }
    expected_correct = ["A", "Z"]
    rng = random.Random(42)
    result = shuffle_quiz_options(quiz, rng=rng)
    for i, q in enumerate(result["questions"]):
        assert q["options"][q["correct_index"]] == expected_correct[i]


def test_quiz_correct_answers_preserved():
    correct_answers = ["correct1", "correct2", "correct3"]
    quiz = {
        "quiz_title": "T",
        "questions": [
            _q(f"Q{i}?", [f"w{i}a", f"w{i}b", f"w{i}c", correct_answers[i]], correct_index=3)
            for i in range(3)
        ],
    }
    for seed in range(10):
        result = shuffle_quiz_options(quiz, rng=random.Random(seed))
        for i, q in enumerate(result["questions"]):
            assert q["options"][q["correct_index"]] == correct_answers[i]


def test_quiz_title_preserved():
    quiz = {"quiz_title": "My Quiz", "questions": [_q("Q?", ["A", "B", "C", "D"], 0)]}
    result = shuffle_quiz_options(quiz)
    assert result["quiz_title"] == "My Quiz"


def test_quiz_passthrough_on_missing_questions():
    quiz = {"quiz_title": "No questions"}
    result = shuffle_quiz_options(quiz)
    assert result is quiz


def test_quiz_passthrough_on_non_list_questions():
    quiz = {"quiz_title": "T", "questions": "bad"}
    result = shuffle_quiz_options(quiz)
    assert result is quiz


def test_quiz_original_not_mutated():
    quiz = {
        "quiz_title": "T",
        "questions": [_q("Q?", ["A", "B", "C", "D"], correct_index=2)],
    }
    original_options = list(quiz["questions"][0]["options"])
    shuffle_quiz_options(quiz, rng=random.Random(42))
    assert quiz["questions"][0]["options"] == original_options


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
