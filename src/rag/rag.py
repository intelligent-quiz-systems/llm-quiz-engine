from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from itertools import zip_longest
from typing import Iterable

MAX_RAG_SOURCES = 3
DEFAULT_MAX_SOURCE_TOKENS = 15_000
DEFAULT_CHUNK_MAX_TOKENS = 600
DEFAULT_CHUNK_OVERLAP_TOKENS = 75
DEFAULT_MAX_CHUNKS_PER_BATCH = 5
RAG_CONTEXT_MAX_TOKENS = 3_200

@dataclass(slots=True)
class RAGSource:
    source_id: str
    source_type: str
    source_name: str
    text: str

@dataclass(slots=True)
class RAGChunk:
    chunk_id: str
    source_id: str
    source_type: str
    source_name: str
    section_label: str
    token_count: int
    text: str


@dataclass(slots=True)
class RAGBatch:
    batch_id: str
    chunks: list[RAGChunk] = field(default_factory=list)
    total_tokens: int = 0

    @property
    def context_text(self) -> str:
        blocks: list[str] = []
        for chunk in self.chunks:
            blocks.append(
                "\n".join(
                    [
                        f"[SOURCE] {chunk.source_name}",
                        f"[TYPE] {chunk.source_type}",
                        f"[SECTION] {chunk.section_label}",
                        f"[CHUNK_ID] {chunk.chunk_id}",
                        f"[TOKENS] {chunk.token_count}",
                        "",
                        chunk.text,
                    ]
                )
            )
        return "\n\n".join(blocks)
    
@dataclass(slots=True)
class RAGBatchLog:
    batch_id: str
    chunk_ids: list[str]
    source_names: list[str]
    total_tokens: int
    chunk_count: int


def make_file_source(source_id: str, file_name: str, extracted_text: str) -> RAGSource:
    return RAGSource(
        source_id=source_id,
        source_type="file",
        source_name=file_name,
        text=normalize_text(extracted_text),
    )


def make_wikipedia_source(source_id: str, page_title: str, extracted_text: str) -> RAGSource:
    return RAGSource(
        source_id=source_id,
        source_type="wikipedia",
        source_name=page_title,
        text=normalize_text(extracted_text),
    )    

def normalize_text(text: str) -> str:
    if not text:
        return ""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def estimate_token_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    
    return math.ceil(len(stripped) / 4)

def split_into_sections(text: str) -> list[tuple[str, str]]:
    stripped = normalize_text(text)
    if not stripped:
        return []

    raw_sections = re.split(r"\n\s*\n+", stripped)
    sections: list[tuple[str, str]] = []

    for index, section_text in enumerate(raw_sections, start=1):
        section_text = section_text.strip()
        if not section_text:
            continue

        first_line = section_text.splitlines()[0].strip()
        if 0 < len(first_line) <= 80:
            section_label = f"section_{index}: {first_line}"
        else:
            section_label = f"section_{index}"

        sections.append((section_label, section_text))

    return sections


def split_section_into_token_windows(
    section_text: str,
    max_tokens: int = DEFAULT_CHUNK_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    words = section_text.split()
    if not words:
        return []

    approx_words_per_token = 0.75
    window_size = max(1, int(max_tokens * approx_words_per_token))
    overlap_size = min(window_size - 1, int(overlap_tokens * approx_words_per_token))
    step = max(1, window_size - overlap_size)

    chunks: list[str] = []
    start = 0

    while start < len(words):
        end = start + window_size
        chunk_words = words[start:end]
        if not chunk_words:
            break

        chunks.append(" ".join(chunk_words))

        if end >= len(words):
            break

        start += step

    return chunks


def validate_sources(
    sources: list[RAGSource],
    max_sources: int = MAX_RAG_SOURCES,
    max_source_tokens: int = DEFAULT_MAX_SOURCE_TOKENS,
) -> None:
    if not sources:
        raise ValueError("Brak źródeł do zbudowania RAG.")

    if len(sources) > max_sources:
        raise ValueError(f"Maksymalnie {max_sources} źródła na jedno generowanie quizu.")

    for source in sources:
        if not source.text.strip():
            raise ValueError(f"Źródło '{source.source_name}' nie zawiera tekstu po ekstrakcji.")

        source_token_count = estimate_token_count(source.text)
        if source_token_count > max_source_tokens:
            raise ValueError(
                f"Źródło '{source.source_name}' przekracza limit tokenów po ekstrakcji: "
                f"{source_token_count} > {max_source_tokens}."
            )
