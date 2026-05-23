"""
Content quality checks for generated quiz questions.

Separate from structural validation (see src/validations/validate_quiz.py)
and from provider/model error classification (see provider_errors.py).

Checks operate on the raw question dicts returned by the generator
and produce a list of QualityIssue entries for logging and future reporting.
"""
from __future__ import annotations
from typing import TypedDict

# Default threshold — matches generation_config.SIMILAR_QUESTION_THRESHOLD.
# Defined here so this module can be imported without loading the llm package init.
SIMILAR_QUESTION_THRESHOLD: float = 0.7


class QualityIssue(TypedDict):
    issue_type: str          # "duplicate_question" | "duplicate_options" | "similar_questions"
    severity: str            # "error" | "warning"
    question_indices: list[int]
    detail: str


# ── Text helpers ──────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace for comparison."""
    return " ".join(text.lower().split())


def _jaccard(a: str, b: str) -> float:
    """Word-set Jaccard similarity between two strings."""
    words_a = set(_normalize(a).split())
    words_b = set(_normalize(b).split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


# ── Individual checks ─────────────────────────────────────────────────────────

def check_duplicate_questions(questions: list[dict]) -> list[QualityIssue]:
    """Flag questions with identical text (case-insensitive, whitespace-normalized)."""
    seen: dict[str, int] = {}
    issues: list[QualityIssue] = []
    for i, q in enumerate(questions):
        key = _normalize(q.get("question", ""))
        if key in seen:
            issues.append(QualityIssue(
                issue_type="duplicate_question",
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
        opts = [_normalize(o) for o in q.get("options", [])]
        seen: dict[str, int] = {}
        for j, opt in enumerate(opts):
            if opt in seen:
                issues.append(QualityIssue(
                    issue_type="duplicate_options",
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
    threshold: float = SIMILAR_QUESTION_THRESHOLD,
) -> list[QualityIssue]:
    """Flag pairs of questions whose Jaccard word-set similarity exceeds threshold."""
    issues: list[QualityIssue] = []
    texts = [_normalize(q.get("question", "")) for q in questions]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            score = _jaccard(texts[i], texts[j])
            if score >= threshold:
                issues.append(QualityIssue(
                    issue_type="similar_questions",
                    severity="warning",
                    question_indices=[i, j],
                    detail=f"questions {i} and {j} are similar (score: {score:.2f})",
                ))
    return issues


# ── Main entry point ──────────────────────────────────────────────────────────

def run_quality_checks(
    questions: list[dict],
    similar_threshold: float = SIMILAR_QUESTION_THRESHOLD,
) -> list[QualityIssue]:
    """Run all content quality checks. Returns a (possibly empty) list of issues."""
    if not questions:
        return []
    issues: list[QualityIssue] = []
    issues.extend(check_duplicate_questions(questions))
    issues.extend(check_duplicate_options(questions))
    issues.extend(check_similar_questions(questions, similar_threshold))
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
