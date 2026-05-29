"""
Generation settings for the quiz generator.

All tunable constants for model selection, API parameters, and source context
limits are defined here. Individual modules import from this file rather than
defining their own values.
"""

# Model and API settings
LLM_MODEL       = "openai/gpt-oss-120b"
LLM_TEMPERATURE = 0.7

# Source context limits - how much of the uploaded text is passed to the model
TOPIC_EXTRACTION_CHARS    = 2000
QUIZ_SOURCE_CONTEXT_CHARS = 10_000   # non-RAG (topic mode): how much source text reaches the prompt
RAG_SOURCE_CONTEXT_CHARS  = 21_000   # RAG mode: max chars per source_slice passed to the prompt

# Maximum extracted text size for RAG mode (chars after file extraction).
# Checked in source_slices.py before the RAG pipeline runs.
MAX_EXTRACTED_SOURCE_CHARS = 300_000

# Minimum extracted text to accept a file at all.
MIN_EXTRACTED_SOURCE_CHARS = 2_500

# Quality thresholds for file→question mapping
MIN_CHARS_PER_QUESTION    = 500    # hard floor: floor(chars/500) = max questions
TARGET_CHARS_PER_QUESTION = 1_000  # soft target; informational only

# RAG source-slice grouping constants
RAG_LARGE_FILE_THRESHOLD         = 100_000  # chars — boundary between small/large file
TARGET_QUESTIONS_PER_SLICE_SMALL = 10       # file < 100k chars: target q/slice
TARGET_QUESTIONS_PER_SLICE_LARGE = 5        # file >= 100k chars: target q/slice
MIN_SLICE_CHARS                  = 10_000   # a slice should contain at least this many chars
MAX_SLICE_CHARS                  = 21_000   # = RAG_SOURCE_CONTEXT_CHARS; slices stay within prompt limit

# Guardrail context - maximum number of prior questions forwarded to the model.
# Set high so the LLM sees full quiz context even for large quizzes and CLI runs
# that may exceed the UI limits.
GUARDRAIL_MAX_QUESTIONS = 100

# Question quality checks
SIMILAR_QUESTION_THRESHOLD = 0.70  # Jaccard similarity — observability / logging only
HARD_REJECT_SIMILARITY     = 0.85  # Jaccard similarity — hard gate, batch is rejected

# Batch generation settings
INITIAL_BATCH_SIZE          = 10   # questions per API call on first attempt
FALLBACK_BATCH_SIZE         = 5    # first reduction after failure
MIN_BATCH_SIZE              = 1    # floor — cannot go lower
MAX_ATTEMPTS_PER_BATCH_SIZE = 2    # retry attempts for transient errors before reducing

# Ordered reduction sequence: each failure steps to the next smaller size.
# batch_size=1 is handled separately with MAX_SINGLE_ATTEMPTS before halt.
BATCH_SIZE_STEPS   = (10, 5, 3, 2, 1)
MAX_SINGLE_ATTEMPTS = 3  # max consecutive fails at batch_size=1 before halting
