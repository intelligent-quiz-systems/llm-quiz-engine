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
    
    