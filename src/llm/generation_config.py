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

# Question quality checks
SIMILAR_QUESTION_THRESHOLD = 0.7   # Jaccard word-set similarity; pairs above this are flagged

# Guardrail context - maximum number of prior questions forwarded to the model
GUARDRAIL_MAX_QUESTIONS = 10

# Batch generation settings
INITIAL_BATCH_SIZE          = 10  # questions per API call on first attempt
FALLBACK_BATCH_SIZE         = 5   # reduced batch size after first failure
MIN_BATCH_SIZE              = 1   # floor - cannot go lower
MAX_ATTEMPTS_PER_BATCH_SIZE = 2   # retries before reducing batch size

# Guardrail context — maximum number of prior questions forwarded to the model
GUARDRAIL_MAX_QUESTIONS = 10
