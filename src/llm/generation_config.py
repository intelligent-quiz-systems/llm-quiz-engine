"""
Generation settings for the quiz generator.

All tunable constants for model selection, API parameters, and source context
limits are defined here. Individual modules import from this file rather than
defining their own values.
"""

# Model and API settings
LLM_MODEL       = "openai/gpt-oss-120b"
LLM_TEMPERATURE = 0.7

# Source context limits — how much of the uploaded text is passed to the model
TOPIC_EXTRACTION_CHARS    = 2000
QUIZ_SOURCE_CONTEXT_CHARS = 10000

# Question quality checks
SIMILAR_QUESTION_THRESHOLD = 0.7   # Jaccard word-set similarity; pairs above this are flagged
