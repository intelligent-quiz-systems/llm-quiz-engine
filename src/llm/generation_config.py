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
QUIZ_SOURCE_CONTEXT_CHARS = 10000

# Maximum extracted text size for RAG mode (chars after file extraction).
# Checked in source_slices.py before the RAG pipeline runs.
# Corresponds to ~25 000 tokens (chars / 4), which allows documents up to
# ~100 000 characters — enough for most textbooks, articles, and manuals.
MAX_EXTRACTED_SOURCE_CHARS = 100_000

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
