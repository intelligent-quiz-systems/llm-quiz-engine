"""
Content quality checks for generated quiz questions.

Separate from structural validation (see src/validations/validate_quiz.py)
and from provider/model error classification (see provider_errors.py).

Checks operate on the raw question dicts returned by the generator
and produce a list of QualityIssue entries for logging and future reporting.

Per-batch gate (run_per_batch_gate) is the hard blocker: it compares a new
batch against all previously accumulated questions and returns error-severity
issues that should cause the batch to be rejected. Warning-severity issues
are recorded for observability only.
"""
from __future__ import annotations
from typing import TypedDict

# Module-level defaults — match generation_config values.
# Defined here so this module can be imported without loading the llm package init.
SIMILAR_QUESTION_THRESHOLD: float = 0.70
HARD_REJECT_SIMILARITY:     float = 0.85


class QualityIssue(TypedDict):
    issue_type: str          # see constants below
    severity: str            # "error" | "warning"
    question_indices: list[int]
    detail: str


# issue_type constants
ISSUE_DUPLICATE_QUESTION  = "duplicate_question"
ISSUE_DUPLICATE_OPTIONS   = "duplicate_options"
ISSUE_SIMILAR_QUESTIONS   = "similar_questions"


# ── Text helpers ──────────────────────────────────────────────────────────────

def normalize_question_text(text: str) -> str:
    """Lowercase, strip, collapse whitespace for comparison. Public helper."""
    return " ".join(text.lower().split())


def _jaccard(a: str, b: str) -> float:
    """Word-set Jaccard similarity between two pre-normalized strings."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


# ── Within-list checks (operate on a single question list) ───────────────────

def check_duplicate_questions(questions: list[dict]) -> list[QualityIssue]:
    """Flag questions with identical text (case-insensitive, whitespace-normalized)."""
    seen: dict[str, int] = {}
    issues: list[QualityIssue] = []
    for i, q in enumerate(questions):
        key = normalize_question_text(q.get("question", ""))
        if key in seen:
            issues.append(QualityIssue(
                issue_type=ISSUE_DUPLICATE_QUESTION,
                severity="error",
                question_indices=[seen[key], i],
                detail=f"questions {seen[key]} and {i} have identical text",
            ))
        else:
            seen[key] = i
    return issues


def check_duplicate_options(questions: list[dict]) -> list[QualityIssue]:
    """Flag questions where two or more answer options are identical."""
    issues: list[QualityIssue] = []
    for i, q in enumerate(questions):
        opts = [normalize_question_text(o) for o in q.get("options", [])]
        seen: dict[str, int] = {}
        for j, opt in enumerate(opts):
            if opt in seen:
                issues.append(QualityIssue(
                    issue_type=ISSUE_DUPLICATE_OPTIONS,
                    severity="error",
                    question_indices=[i],
                    detail=(
                        f"question {i}: options at positions {seen[opt]} "
                        f"and {j} are identical"
                    ),
                ))
            else:
                seen[opt] = j
    return issues


def check_similar_questions(
    questions: list[dict],
    hard_threshold: float = HARD_REJECT_SIMILARITY,
    warn_threshold: float = SIMILAR_QUESTION_THRESHOLD,
) -> list[QualityIssue]:
    """
    Flag pairs of questions by Jaccard word-set similarity (within a single list).

    score >= hard_threshold → severity "error"
    score >= warn_threshold → severity "warning"
    """
    issues: list[QualityIssue] = []
    texts = [normalize_question_text(q.get("question", "")) for q in questions]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            score = _jaccard(texts[i], texts[j])
            if score >= hard_threshold:
                issues.append(QualityIssue(
                    issue_type=ISSUE_SIMILAR_QUESTIONS,
                    severity="error",
                    question_indices=[i, j],
                    detail=f"questions {i} and {j} are too similar (score: {score:.2f}, threshold: {hard_threshold})",
                ))
            elif score >= warn_threshold:
                issues.append(QualityIssue(
                    issue_type=ISSUE_SIMILAR_QUESTIONS,
                    severity="warning",
                    question_indices=[i, j],
                    detail=f"questions {i} and {j} are similar (score: {score:.2f})",
                ))
    return issues


# ── Cross-batch checks (new batch vs all accumulated questions) ───────────────

def check_cross_batch_duplicates(
    new_questions: list[dict],
    accumulated: list[dict],
) -> list[QualityIssue]:
    """
    Flag questions in new_questions whose text exactly matches any question in accumulated.

    Uses a normalized set for O(n) lookup. Question indices in the issue refer
    to positions within new_questions (prefixed "new:") for clarity.
    """
    if not accumulated:
        return []
    accumulated_set = {normalize_question_text(q.get("question", "")) for q in accumulated}
    issues: list[QualityIssue] = []
    for i, q in enumerate(new_questions):
        key = normalize_question_text(q.get("question", ""))
        if key and key in accumulated_set:
            issues.append(QualityIssue(
                issue_type=ISSUE_DUPLICATE_QUESTION,
                severity="error",
                question_indices=[i],
                detail=f"new batch question {i} duplicates an already accepted question",
            ))
    return issues


def check_cross_batch_similar(
    new_questions: list[dict],
    accumulated: list[dict],
    hard_threshold: float = HARD_REJECT_SIMILARITY,
    warn_threshold: float = SIMILAR_QUESTION_THRESHOLD,
) -> list[QualityIssue]:
    """
    Compare each question in new_questions against every question in accumulated
    using Jaccard word-set similarity.

    score >= hard_threshold → severity "error"  (hard reject)
    score >= warn_threshold → severity "warning" (observability only)

    O(m × n) where m = len(new_questions), n = len(accumulated).
    For m=10, n=100: 1000 comparisons — negligible cost.
    """
    if not accumulated:
        return []
    new_texts = [normalize_question_text(q.get("question", "")) for q in new_questions]
    acc_texts = [normalize_question_text(q.get("question", "")) for q in accumulated]
    issues: list[QualityIssue] = []
    for i, new_t in enumerate(new_texts):
        for j, acc_t in enumerate(acc_texts):
            score = _jaccard(new_t, acc_t)
            if score >= hard_threshold:
                issues.append(QualityIssue(
                    issue_type=ISSUE_SIMILAR_QUESTIONS,
                    severity="error",
                    question_indices=[i],
                    detail=(
                        f"new batch question {i} is too similar to accepted "
                        f"question {j} (score: {score:.2f}, threshold: {hard_threshold})"
                    ),
                ))
            elif score >= warn_threshold:
                issues.append(QualityIssue(
                    issue_type=ISSUE_SIMILAR_QUESTIONS,
                    severity="warning",
                    question_indices=[i],
                    detail=(
                        f"new batch question {i} is similar to accepted "
                        f"question {j} (score: {score:.2f})"
                    ),
                ))
    return issues


# ── Per-batch gate (called before accumulated.extend()) ──────────────────────

def run_per_batch_gate(
    new_questions: list[dict],
    accumulated: list[dict],
    hard_threshold: float = HARD_REJECT_SIMILARITY,
    warn_threshold: float = SIMILAR_QUESTION_THRESHOLD,
) -> list[QualityIssue]:
    """
    Hard quality gate for a new batch before it is added to accumulated.

    Runs four checks:
      1. Exact duplicate within new batch
      2. Exact duplicate cross-batch (new vs accumulated)
      3. Jaccard similarity within new batch
      4. Jaccard similarity cross-batch (new vs accumulated)

    Returns all issues found. Callers should treat any severity="error" issue
    as a hard reject (reduce batch size). severity="warning" issues are
    observability only.
    """
    if not new_questions:
        return []
    issues: list[QualityIssue] = []
    issues.extend(check_duplicate_questions(new_questions))
    issues.extend(check_duplicate_options(new_questions))
    issues.extend(check_similar_questions(new_questions, hard_threshold, warn_threshold))
    issues.extend(check_cross_batch_duplicates(new_questions, accumulated))
    issues.extend(check_cross_batch_similar(new_questions, accumulated, hard_threshold, warn_threshold))
    return issues


# ── Full post-generation check (all accumulated, for final reporting) ─────────

def run_quality_checks(
    questions: list[dict],
    similar_threshold: float = SIMILAR_QUESTION_THRESHOLD,
) -> list[QualityIssue]:
    """
    Run all within-list quality checks on the final accumulated question set.
    Used in _post_process_quiz for full-quiz reporting after generation completes.
    Returns a (possibly empty) list of issues.
    """
    if not questions:
        return []
    issues: list[QualityIssue] = []
    issues.extend(check_duplicate_questions(questions))
    issues.extend(check_duplicate_options(questions))
    issues.extend(check_similar_questions(questions, warn_threshold=similar_threshold))
    return issues


# ── Log formatter ─────────────────────────────────────────────────────────────

def format_quality_log(issues: list[QualityIssue]) -> str:
    """Return a structured log block for printing to stdout."""
    errors   = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    lines = [
        "\n===== QUALITY ISSUES =====",
        f"total:    {len(issues)}  ({errors} error(s), {warnings} warning(s))",
    ]
    for issue in issues:
        lines.append(
            f"  [{issue['severity']:7}] {issue['issue_type']:<20} — {issue['detail']}"
        )
    return "\n".join(lines)
