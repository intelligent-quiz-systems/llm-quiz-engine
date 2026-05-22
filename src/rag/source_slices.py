"""
RAG source slice builder for quiz generation.

Bridges the RAG pipeline (document → RAGBatch) and the worker layer
(BackgroundGenerationWorker source_slices parameter).

Each RAGBatch becomes one source slice: a (context_text, n_questions) tuple
where retry/reduce operates independently per slice, not across the whole document.
"""
from __future__ import annotations

from llm.generation_config import MAX_EXTRACTED_SOURCE_CHARS
from rag.rag import (
    RAGBatch,
    build_rag_pipeline,
    distribute_questions,
    estimate_token_count,
    make_file_source,
)


def build_source_slices_from_file(
    source_text: str,
    file_name: str,
    total_questions: int,
) -> tuple[list[tuple[str, int]] | None, str | None, dict | None]:
    """
    Run the RAG pipeline on extracted file text and return source slices.

    Returns (slices, None, rag_split_summary) on success or
    (None, error_message, None) on failure.

    Each slice is a (context_text, n_questions) tuple ready for
    BackgroundGenerationWorker(source_slices=...).

    rag_split_summary contains human-readable metadata about how the document
    was divided: section/chunk/batch counts, per-slice token and question info.
    """
    if len(source_text) > MAX_EXTRACTED_SOURCE_CHARS:
        return (
            None,
            f"Plik zawiera zbyt dużo tekstu po ekstrakcji "
            f"({len(source_text):,} znaków). "
            f"Maksimum to {MAX_EXTRACTED_SOURCE_CHARS:,} znaków.",
            None,
        )

    rag_source = make_file_source("src_1", file_name, source_text)
    try:
        chunks, rag_batches, logs = build_rag_pipeline([rag_source])
    except ValueError as exc:
        return None, str(exc), None

    if not rag_batches:
        return None, "Nie udało się podzielić pliku na partie kontekstu RAG.", None

    question_counts = distribute_questions(total_questions, rag_batches)
    slices = [
        (batch.context_text, n)
        for batch, n in zip(rag_batches, question_counts)
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
        "slices": [
            {
                "slice_index": i + 1,
                "context_chars": len(batch.context_text),
                "estimated_tokens": batch.total_tokens,
                "question_count": n,
                "chunk_ids": logs[i].chunk_ids,
                "source_names": logs[i].source_names,
            }
            for i, (batch, n) in enumerate(zip(rag_batches, question_counts))
        ],
    }

    return slices, None, rag_split_summary
