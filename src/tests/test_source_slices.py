"""
Tests for RAG source-slice helpers.
No API access required — only pure logic functions are tested.

Run with pytest or directly:  python src/tests/test_source_slices.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from rag.source_slices import _clamp_questions_to_file_size, _group_batches_into_slices
from rag.rag import RAGBatch, RAGChunk
from llm.generation_config import (
    MIN_CHARS_PER_QUESTION,
    RAG_LARGE_FILE_THRESHOLD,
    MAX_SLICE_CHARS,
    TARGET_QUESTIONS_PER_SLICE_SMALL,
    TARGET_QUESTIONS_PER_SLICE_LARGE,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_batch(batch_id: str, text_chars: int = 1000) -> RAGBatch:
    """Create a minimal RAGBatch with a single chunk of approximately text_chars chars."""
    chunk = RAGChunk(
        chunk_id=f"{batch_id}:1:1",
        source_id="test",
        source_type="file",
        source_name="test.txt",
        section_label="section_1",
        token_count=text_chars // 4,
        text="w " * (text_chars // 2),
    )
    return RAGBatch(batch_id=batch_id, chunks=[chunk], total_tokens=text_chars // 4)


def _make_batches(n: int, text_chars: int = 1000) -> list[RAGBatch]:
    return [_make_batch(f"batch_{i+1}", text_chars) for i in range(n)]


# ── _clamp_questions_to_file_size ──────────────────────────────────────────────

def test_clamp_no_cap_needed():
    """Requested < safe limit → no change, no warning."""
    count, warning = _clamp_questions_to_file_size(10_000, 5)
    assert count == 5
    assert warning is None


def test_clamp_exact_limit():
    """Requested exactly equals floor(chars / min_cqp) → no change."""
    safe = 10_000 // MIN_CHARS_PER_QUESTION  # = 20
    count, warning = _clamp_questions_to_file_size(10_000, safe)
    assert count == safe
    assert warning is None


def test_clamp_reduces_questions():
    """Requested > safe → clamped to safe, warning returned."""
    count, warning = _clamp_questions_to_file_size(5_000, 20)
    assert count == 5_000 // MIN_CHARS_PER_QUESTION  # = 10
    assert warning is not None
    assert "10" in warning


def test_clamp_below_minimum_returns_zero():
    """File too short for even 3 questions → (0, error)."""
    count, warning = _clamp_questions_to_file_size(1_000, 5)
    assert count == 0
    assert warning is not None


def test_clamp_exactly_three_questions_passes():
    """Exactly 3 * MIN_CHARS_PER_QUESTION chars → safe_q == 3, no error."""
    chars = 3 * MIN_CHARS_PER_QUESTION
    count, warning = _clamp_questions_to_file_size(chars, 3)
    assert count == 3
    assert warning is None


def test_clamp_one_below_minimum_fails():
    """One char below the 3-question floor → error."""
    chars = 3 * MIN_CHARS_PER_QUESTION - 1
    count, warning = _clamp_questions_to_file_size(chars, 3)
    assert count == 0
    assert warning is not None


# ── _group_batches_into_slices ─────────────────────────────────────────────────

def test_group_single_batch_gives_one_slice():
    batches = _make_batches(1)
    groups = _group_batches_into_slices(batches, source_chars=5_000, total_questions=10)
    assert len(groups) == 1
    assert groups[0] == batches


def test_group_small_file_medium_target_10():
    """Small file + medium → target 10q/slice → ceil(20/10)=2 slices from 8 batches."""
    batches = _make_batches(8)
    groups = _group_batches_into_slices(
        batches, source_chars=50_000, total_questions=20, difficulty="medium"
    )
    assert len(groups) == 2
    assert sum(len(g) for g in groups) == 8


def test_group_large_file_medium_target_5():
    """Large file + medium → target 5q/slice → ceil(20/5)=4 slices from 8 batches."""
    batches = _make_batches(8)
    groups = _group_batches_into_slices(
        batches, source_chars=RAG_LARGE_FILE_THRESHOLD + 1, total_questions=20, difficulty="medium"
    )
    assert len(groups) == 4
    assert sum(len(g) for g in groups) == 8


def test_group_hard_difficulty_target_5():
    """Hard difficulty on small file → target 5q/slice → ceil(20/5)=4 slices."""
    batches = _make_batches(8)
    groups = _group_batches_into_slices(
        batches, source_chars=50_000, total_questions=20, difficulty="hard"
    )
    assert len(groups) == 4


def test_group_n_slices_capped_at_n_batches():
    """More target slices than batches → capped at number of batches."""
    batches = _make_batches(2)
    groups = _group_batches_into_slices(
        batches, source_chars=50_000, total_questions=100, difficulty="medium"
    )
    assert len(groups) <= len(batches)


def test_group_all_batches_included():
    """Every batch must appear in exactly one group."""
    batches = _make_batches(11)
    groups = _group_batches_into_slices(
        batches, source_chars=30_000, total_questions=10, difficulty="medium"
    )
    all_batch_ids = [b.batch_id for g in groups for b in g]
    assert sorted(all_batch_ids) == sorted(b.batch_id for b in batches)


def test_group_safety_split_on_large_context():
    """A group exceeding MAX_SLICE_CHARS should be split in the safety pass."""
    # Each batch context ≈ MAX_SLICE_CHARS/4 chars; 4 in one group → combined > MAX_SLICE_CHARS.
    # After split into groups of 2, each group < MAX_SLICE_CHARS.
    batch_chars = MAX_SLICE_CHARS // 4
    batches = _make_batches(4, text_chars=batch_chars)
    # 1 slice requested → all 4 batches in one group → combined > MAX_SLICE_CHARS → split
    groups = _group_batches_into_slices(
        batches, source_chars=50_000, total_questions=5, difficulty="medium"
    )
    # Safety pass must have produced more than 1 group
    assert len(groups) > 1
    # Each resulting group must be within MAX_SLICE_CHARS (since individual batches are small)
    for group in groups:
        combined = sum(len(b.context_text) for b in group)
        assert combined <= MAX_SLICE_CHARS or len(group) == 1


# ── spec examples ──────────────────────────────────────────────────────────────

def test_spec_example_10q_medium_gives_1_slice():
    """10q medium, small file, enough batches → 1 slice."""
    batches = _make_batches(11)
    groups = _group_batches_into_slices(
        batches, source_chars=33_000, total_questions=10, difficulty="medium"
    )
    assert len(groups) == 1


def test_spec_example_25q_medium_gives_3_slices():
    """25q medium, small file → ceil(25/10)=3 slices."""
    batches = _make_batches(12)
    groups = _group_batches_into_slices(
        batches, source_chars=50_000, total_questions=25, difficulty="medium"
    )
    assert len(groups) == 3


def test_spec_example_45q_medium_gives_5_slices():
    """45q medium, small file → ceil(45/10)=5 slices."""
    batches = _make_batches(20)
    groups = _group_batches_into_slices(
        batches, source_chars=80_000, total_questions=45, difficulty="medium"
    )
    assert len(groups) == 5


def test_spec_example_43q_hard_gives_9_slices():
    """43q hard → ceil(43/5)=9 slices."""
    batches = _make_batches(20)
    groups = _group_batches_into_slices(
        batches, source_chars=80_000, total_questions=43, difficulty="hard"
    )
    assert len(groups) == 9


# ── Standalone runner ──────────────────────────────────────────────────────────

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
