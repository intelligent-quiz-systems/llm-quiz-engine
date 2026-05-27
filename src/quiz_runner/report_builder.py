"""
Build CSV, Markdown, and JSON reports for a test series.
"""
import csv
import json
from datetime import datetime
from pathlib import Path

NA = "n/a"

# ── Column schemas (kept here so Excel and CSV share the same definitions) ───

TEST_INDEX_FIELDS = [
    "test_id", "label", "topic", "difficulty",
    "count_requested", "count_generated", "ok", "status",
    "duration_seconds", "avg_seconds_per_question",
    "n_batches", "n_rejected_attempts", "min_batch_size",
    "total_tokens", "avg_tokens_per_question", "error",
]

BATCH_EFFICIENCY_FIELDS = [
    "test_id", "batch_number", "batch_duration_seconds",
    "attempts_count", "rejected_attempts_count", "accepted_questions_count",
    "final_accepted_batch_size", "gross_s_per_q", "clean_s_per_q",
    "rejection_overhead_s_total", "rejection_overhead_pct",
    "guardrail_question_count", "guardrail_chars", "total_prompt_chars",
    "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
]

REJECTIONS_DETAIL_FIELDS = [
    "test_id", "batch_number", "attempt_number", "attempted_batch_size",
    "attempt_duration_seconds", "reject_reason", "reject_family",
    "json_failure_kind", "provider_error_message_type", "provider_http_status",
    "token_usage_known", "input_tokens", "output_tokens",
    "output_tokens_wasted", "output_token_usage_pct",
    "guardrail_chars", "total_prompt_chars", "failed_generation_chars",
]

REJECTION_CATEGORIES_FIELDS = [
    "reject_reason", "reject_family", "n_attempts",
    "sum_duration_seconds", "mean_duration_seconds",
    "mean_attempted_batch_size", "token_usage_known_count",
    "token_usage_unknown_count", "output_tokens_wasted_sum",
]

GUARDRAIL_STATS_FIELDS = [
    "test_id", "batch_number", "guardrail_question_count",
    "guardrail_chars", "system_prompt_chars", "user_prompt_chars",
    "total_prompt_chars", "input_tokens_estimate",
]


# ── Writers ───────────────────────────────────────────────────────────────────

def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, NA) for k in fieldnames})


def _result_to_index_row(r: dict) -> dict:
    return {k: r.get(k, NA) for k in TEST_INDEX_FIELDS}


# ── Main entry point ──────────────────────────────────────────────────────────

def build_all_reports(reports_dir: Path, results: list[dict]) -> None:
    """Write all CSV, Markdown, and JSON reports into reports_dir."""
    reports_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(
        reports_dir / "test_index.csv",
        TEST_INDEX_FIELDS,
        [_result_to_index_row(r) for r in results],
    )
    # Schema-only CSVs — ready for future batch/rejection data
    _write_csv(reports_dir / "batch_efficiency.csv",    BATCH_EFFICIENCY_FIELDS,    [])
    _write_csv(reports_dir / "rejections_detail.csv",   REJECTIONS_DETAIL_FIELDS,   [])
    _write_csv(reports_dir / "rejection_categories.csv", REJECTION_CATEGORIES_FIELDS, [])
    _write_csv(reports_dir / "guardrail_stats.csv",     GUARDRAIL_STATS_FIELDS,     [])

    _build_md(reports_dir / "epoch_comparison.md", results)
    _build_meta(reports_dir / "report_meta.json", results)


def _build_md(path: Path, results: list[dict]) -> None:
    completed = [r for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok") and r.get("status") != "dry-run"]
    dry = [r for r in results if r.get("status") == "dry-run"]

    lines = [
        "# Test Series Summary",
        "",
        (f"Total: **{len(results)}**  |  "
         f"Completed: **{len(completed)}**  |  "
         f"Failed: **{len(failed)}**  |  "
         f"Dry-run: **{len(dry)}**"),
        "",
        "## Tests",
        "",
        "| # | Topic | Difficulty | Target | Generated | Status | Duration (s) |",
        "| -- | ----- | ---------- | ------ | --------- | ------ | ------------ |",
    ]
    for r in results:
        lines.append(
            f"| {r.get('test_id', '')} | {r.get('topic', '')} | {r.get('difficulty', '')} "
            f"| {r.get('count_requested', '')} | {r.get('count_generated', '')} "
            f"| {r.get('status', '')} | {r.get('duration_seconds', '')} |"
        )

    lines += [
        "",
        "---",
        "",
        "_Batch and rejection details are not available in the current generator version._",
        "_These columns are reserved for future diagnostic data._",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _build_meta(path: Path, results: list[dict]) -> None:
    completed = sum(1 for r in results if r.get("ok"))
    data = {
        "generated_at": datetime.now().isoformat(),
        "total_tests": len(results),
        "completed": completed,
        "failed": len(results) - completed,
        "diagnostics_note": (
            "Batch, rejection, token, and guardrail data are not available "
            "in the current generator version. Schema columns are reserved."
        ),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
