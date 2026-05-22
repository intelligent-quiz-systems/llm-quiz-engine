"""
RAG source slice builder for quiz generation.

Bridges the RAG pipeline (document → RAGBatch) and the worker layer
(BackgroundGenerationWorker source_slices parameter).

Each RAGBatch becomes one source slice: a (context_text, n_questions) tuple
where retry/reduce operates independently per slice, not across the whole document.
"""
from __future__ import annotations

from rag.rag import RAGBatch, build_rag_pipeline, distribute_questions, make_file_source


def build_source_slices_from_file(
    source_text: str,
    file_name: str,
    total_questions: int,
) -> tuple[list[tuple[str, int]] | None, str | None]:
    """
    Run the RAG pipeline on extracted file text and return source slices.

    Returns (slices, None) on success or (None, error_message) on failure.
    Each slice is a (context_text, n_questions) tuple ready for
    BackgroundGenerationWorker(source_slices=...).
    """
    rag_source = make_file_source("src_1", file_name, source_text)
    try:
        _, rag_batches, _ = build_rag_pipeline([rag_source])
    except ValueError as exc:
        return None, str(exc)

    if not rag_batches:
        return None, "Nie udało się podzielić pliku na partie kontekstu RAG."

    question_counts = distribute_questions(total_questions, rag_batches)
    slices = [
        (batch.context_text, n)
        for batch, n in zip(rag_batches, question_counts)
        if n > 0
    ]
    return slices, None
