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
