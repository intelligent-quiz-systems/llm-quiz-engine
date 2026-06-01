"""
RAG source slice builder for quiz generation.

Bridges the RAG pipeline (document → RAGBatch) and the worker layer
(BackgroundGenerationWorker source_slices parameter).

RAGBatches are grouped into source_slices based on total question count
and difficulty. Each source_slice drives one run_batched_generation call
where retry/reduce operates independently per slice.

Grouping rules:
- easy/medium + small file (< RAG_LARGE_FILE_THRESHOLD): target 10q/slice
- hard or large file (>= RAG_LARGE_FILE_THRESHOLD): target 5q/slice
- No slice exceeds MAX_SLICE_CHARS to avoid prompt truncation.
"""
from __future__ import annotations

import math

from llm.generation_config import (
    MAX_EXTRACTED_SOURCE_CHARS,
    MAX_FILE_SOURCE_CHARS,
    MIN_CHARS_PER_QUESTION,
    RAG_LARGE_FILE_THRESHOLD,
    TARGET_QUESTIONS_PER_SLICE_SMALL,
    TARGET_QUESTIONS_PER_SLICE_LARGE,
    MAX_SLICE_CHARS,
)
from rag.rag import (
    RAGBatch,
    build_rag_pipeline,
    distribute_questions,
    estimate_token_count,
    make_file_source,
)


def _clamp_questions_to_file_size(
    source_chars: int,
    requested_questions: int,
    min_chars_per_question: int = MIN_CHARS_PER_QUESTION,
) -> tuple[int, str | None]:
    """
    Returns (allowed_count, warning_or_None).

    Clamps requested_questions to floor(source_chars / min_chars_per_question).
    Returns (0, error) if the file is too short for even 3 questions.
    """
    safe_q = math.floor(source_chars / min_chars_per_question)
    if safe_q < 3:
        return 0, (
            f"Plik ma za mało tekstu dla sensownego quizu "
            f"({source_chars:,} znaków, minimum {3 * min_chars_per_question:,})."
        )
    if requested_questions > safe_q:
        return safe_q, (
            f"Ten plik ma za mało tekstu na {requested_questions} pytań. "
            f"Na podstawie długości pliku zostanie wygenerowanych {safe_q} pytań. "
            "Zmniejsz liczbę pytań albo użyj dłuższego pliku."
        )
    return requested_questions, None


def _group_batches_into_slices(
    batches: list[RAGBatch],
    source_chars: int,
    total_questions: int,
    difficulty: str = "medium",
) -> list[list[RAGBatch]]:
    """
    Group consecutive RAGBatches into slices.

    Target questions per slice is determined by difficulty and file size:
    - hard: 5q/slice
    - easy/medium + large file (>= RAG_LARGE_FILE_THRESHOLD): 5q/slice
    - easy/medium + small file: 10q/slice

    Number of slices = ceil(total_questions / target_q), capped at len(batches).
    Safety pass: any group whose combined context_text exceeds MAX_SLICE_CHARS
    is split in half (applied once — result groups are not re-checked).
    """
    difficulty_cap = 5 if difficulty == "hard" else TARGET_QUESTIONS_PER_SLICE_SMALL
    file_cap = (
        TARGET_QUESTIONS_PER_SLICE_LARGE
        if source_chars > RAG_LARGE_FILE_THRESHOLD
        else TARGET_QUESTIONS_PER_SLICE_SMALL
    )
    target_q = min(difficulty_cap, file_cap)

    n_slices = max(1, math.ceil(total_questions / target_q))
    n_slices = min(n_slices, len(batches))

    # Split batches into exactly n_slices groups (some get one extra batch to use all).
    k, remainder = divmod(len(batches), n_slices)
    groups: list[list[RAGBatch]] = []
    start = 0
    for i in range(n_slices):
        size = k + (1 if i < remainder else 0)
        groups.append(batches[start : start + size])
        start += size

    # Safety pass: split groups that would exceed MAX_SLICE_CHARS
    result: list[list[RAGBatch]] = []
    for group in groups:
        combined_chars = sum(len(b.context_text) for b in group)
        if combined_chars <= MAX_SLICE_CHARS or len(group) == 1:
            result.append(group)
        else:
            mid = max(1, len(group) // 2)
            result.append(group[:mid])
            result.append(group[mid:])
    return result


def build_source_slices_from_file(
    source_text: str,
    file_name: str,
    total_questions: int,
    difficulty: str = "medium",
) -> tuple[list[tuple[str, int]] | None, str | None, dict | None]:
    """
    Run the RAG pipeline on extracted file text and return source slices.

    Returns (slices, None, rag_split_summary) on success or
    (None, error_message, None) on failure.

    Each slice is a (context_text, n_questions) tuple ready for
    BackgroundGenerationWorker(source_slices=...).

    When the file is too short for the requested question count, questions are
    clamped silently — rag_split_summary["questions_capped"] is True and
    rag_split_summary["clamp_warning"] contains a user-facing message.
    """
    if len(source_text) > MAX_EXTRACTED_SOURCE_CHARS:
        return (
            None,
            f"Plik zawiera zbyt dużo tekstu po ekstrakcji "
            f"({len(source_text):,} znaków). "
            f"Maksimum to {MAX_EXTRACTED_SOURCE_CHARS:,} znaków.",
            None,
        )

    if len(source_text) > MAX_FILE_SOURCE_CHARS:
        return (
            None,
            "Plik jest zbyt duży do wygenerowania quizu.\n\n"
            "Maksymalny rozmiar tekstu w pliku PDF/TXT to około 20 000 znaków, "
            "czyli mniej więcej 8 stron tekstu.\n\n"
            "Podziel plik na mniejsze części albo użyj krótszego dokumentu.",
            None,
        )

    clamped_questions, clamp_warning = _clamp_questions_to_file_size(
        len(source_text), total_questions
    )
    if clamped_questions == 0:
        return None, clamp_warning, None

    rag_source = make_file_source("src_1", file_name, source_text)
    try:
        chunks, rag_batches, _logs = build_rag_pipeline([rag_source])
    except ValueError as exc:
        return None, str(exc), None

    if not rag_batches:
        return None, "Nie udało się podzielić pliku na partie kontekstu RAG.", None

    grouped = _group_batches_into_slices(
        rag_batches, len(source_text), clamped_questions, difficulty
    )
    question_counts = distribute_questions(clamped_questions, grouped)

    slices = [
        ("\n\n".join(b.context_text for b in group), n)
        for group, n in zip(grouped, question_counts)
        if n > 0
    ]

    section_count = len({(c.source_id, c.section_label) for c in chunks})

    rag_split_summary = {
        "source_name": file_name,
        "source_chars": len(source_text),
        "estimated_tokens": estimate_token_count(source_text),
        "section_count": section_count,
        "chunk_count": len(chunks),
        "rag_batch_count": len(rag_batches),
        "questions_requested": total_questions,
        "questions_allowed": clamped_questions,
        "questions_capped": clamped_questions < total_questions,
        "clamp_warning": clamp_warning,
        "slices": [
            {
                "slice_index": i + 1,
                "batch_ids": [b.batch_id for b in group],
                "context_chars": len("\n\n".join(b.context_text for b in group)),
                "estimated_tokens": sum(b.total_tokens for b in group),
                "question_count": n,
                "chunk_ids": [c.chunk_id for b in group for c in b.chunks],
                "source_names": sorted({c.source_name for b in group for c in b.chunks}),
            }
            for i, (group, n) in enumerate(zip(grouped, question_counts))
            if n > 0
        ],
    }

    return slices, None, rag_split_summary
