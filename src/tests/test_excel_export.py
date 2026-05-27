"""
Structural tests for the Excel export (llm_observability_analytics.xlsx).

Calls build_excel() directly with minimal mock data and verifies:
  - file is created with the expected name,
  - sheet names and order are correct,
  - Dane_pivot_FULL has 67 columns,
  - headers contain PL + EN in one cell (newline-separated),
  - EN part of each header is snake_case (no spaces),
  - freeze pane and auto-filter are set on Dane_pivot_FULL.

Skipped when openpyxl is not installed.
"""
import sys
import tempfile
from pathlib import Path

import pytest

# Skip entire module if openpyxl is not available
openpyxl = pytest.importorskip("openpyxl")

# Make sure quiz_runner is importable (same path trick as other tests)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quiz_runner.excel_export import build_excel

# ── Expected workbook structure ───────────────────────────────────────────────

EXPECTED_FILENAME   = "llm_observability_analytics.xlsx"
EXPECTED_N_COLS     = 67
EXPECTED_SHEET_ORDER = [
    "Dane_pivot_FULL",
    "01_Dashboard",
    "02_Testy",
    "03_Podsumowania",
    "04_Bledy_per_test",
    "05_Kategorie_bledow",
    "06_Batche_srednie",
    "07_Guardrail",
    "08_Raw_rejections",
    "09_Raw_batches",
    "10_Quality_issues",
    "11_Slownik_kolumn",
]


# ── Minimal mock data ─────────────────────────────────────────────────────────

def _make_results():
    return [
        {
            "test_id":              "001_python_easy_3",
            "label":                "",
            "topic":                "Python",
            "difficulty":           "easy",
            "count_requested":      3,
            "count_generated":      3,
            "ok":                   True,
            "status":               "completed",
            "duration_seconds":     4.5,
            "avg_seconds_per_question": 1.5,
            "n_batches":            1,
            "n_rejected_attempts":  0,
            "min_batch_size":       3,
            "total_tokens":         900,
            "avg_tokens_per_question": 300,
            "model":                None,
            "error":                None,
        },
        {
            "test_id":              "002_docker_hard_3",
            "label":                "",
            "topic":                "Docker",
            "difficulty":           "hard",
            "count_requested":      3,
            "count_generated":      0,
            "ok":                   False,
            "status":               "failed",
            "duration_seconds":     2.1,
            "avg_seconds_per_question": None,
            "n_batches":            None,
            "n_rejected_attempts":  None,
            "min_batch_size":       None,
            "total_tokens":         None,
            "avg_tokens_per_question": None,
            "model":                None,
            "error":                "GROQ_BASE_URL not set",
        },
    ]


def _make_batch_rows():
    return [
        {
            "test_id":                  "001_python_easy_3",
            "batch_number":             1,
            "accepted_batch_size":      3,
            "accepted_questions":       3,
            "total_attempts":           2,
            "outcome":                  "accepted",
            "attempt_duration_seconds": 3.5,
            "batch_duration_seconds":   4.2,
            "input_tokens":             450,
            "output_tokens":            350,
            "reasoning_tokens":         100,
            "total_tokens":             900,
            "guardrail_question_count": 0,
            "guardrail_chars":          0,
            "system_prompt_chars":      400,
            "user_prompt_chars":        350,
            "total_prompt_chars":       750,
        },
    ]


def _make_rejection_rows():
    return [
        {
            "test_id":                  "001_python_easy_3",
            "batch_number":             1,
            "attempt_number":           1,
            "attempted_batch_size":     3,
            "decision":                 "retry",
            "error_type":               "APITimeoutError",
            "attempt_duration_seconds": 0.7,
            "provider_error_info":      None,
            "system_prompt_chars":      400,
            "user_prompt_chars":        350,
            "total_prompt_chars":       750,
            "guardrail_question_count": 0,
            "guardrail_chars":          0,
        },
    ]


def _make_quality_rows():
    return [
        {
            "test_id":       "001_python_easy_3",
            "issue_type":    "similar",
            "question_index": 0,
            "question_text": "Co robi print()?",
            "detail":        "similarity=0.85 with Q2",
        },
    ]


# ── Fixture: generate workbook once ──────────────────────────────────────────

@pytest.fixture(scope="module")
def generated_xlsx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("excel_test")
    out = tmp / EXPECTED_FILENAME
    build_excel(
        out,
        _make_results(),
        batch_rows=_make_batch_rows(),
        rejection_rows=_make_rejection_rows(),
        quality_rows=_make_quality_rows(),
        run_id="test_run_mock",
        run_datetime="2026-05-11 12:00:00",
        git_branch="test-branch",
    )
    return out


@pytest.fixture(scope="module")
def workbook(generated_xlsx):
    # read_only=False so freeze_panes and auto_filter are accessible
    return openpyxl.load_workbook(str(generated_xlsx), data_only=True)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_file_exists_with_correct_name(generated_xlsx):
    assert generated_xlsx.exists(), "Excel file was not created"
    assert generated_xlsx.name == EXPECTED_FILENAME


def test_first_sheet_is_pivot_full(workbook):
    assert workbook.sheetnames[0] == "Dane_pivot_FULL"


def test_sheet_order(workbook):
    assert workbook.sheetnames == EXPECTED_SHEET_ORDER


def test_pivot_full_has_67_columns(workbook):
    ws = workbook["Dane_pivot_FULL"]
    assert ws.max_column == EXPECTED_N_COLS, (
        f"Expected 67 columns, got {ws.max_column}"
    )


def test_pivot_headers_are_bilingual(workbook):
    """Every header cell must contain a newline separating PL and EN parts."""
    ws = workbook["Dane_pivot_FULL"]
    row1 = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    for i, val in enumerate(row1, 1):
        assert val is not None, f"Column {i} header is None"
        assert "\n" in val, (
            f"Column {i} header missing PL\\nEN separator: {val!r}"
        )


def test_pivot_en_names_are_snake_case(workbook):
    """EN part (after newline) must be snake_case — no spaces."""
    ws = workbook["Dane_pivot_FULL"]
    row1 = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    bad = []
    for i, val in enumerate(row1, 1):
        if val and "\n" in val:
            en = val.split("\n")[-1]
            if " " in en:
                bad.append((i, en))
    assert not bad, f"EN header names with spaces (not snake_case): {bad}"


def test_pivot_full_has_data_rows(workbook):
    ws = workbook["Dane_pivot_FULL"]
    # mock data produces accepted_batch + rejected_attempt + quality_issue + generation_error
    assert ws.max_row > 1, "Dane_pivot_FULL has no data rows"


def test_pivot_full_event_types(workbook):
    """Check that expected event types appear in the event_type column."""
    ws = workbook["Dane_pivot_FULL"]
    # Find event_type column index from EN header
    row1 = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    event_col = None
    for i, val in enumerate(row1, 1):
        if val and val.split("\n")[-1] == "event_type":
            event_col = i
            break
    assert event_col is not None, "event_type column not found"

    event_types = set()
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
        if row[event_col - 1] is not None:
            event_types.add(row[event_col - 1])

    assert "accepted_batch"   in event_types, "accepted_batch event missing"
    assert "rejected_attempt" in event_types, "rejected_attempt event missing"
    assert "quality_issue"    in event_types, "quality_issue event missing"
    assert "generation_error" in event_types, "generation_error event missing"


def test_freeze_pane_set(workbook):
    ws = workbook["Dane_pivot_FULL"]
    assert ws.freeze_panes == "A2", (
        f"freeze_panes expected A2, got {ws.freeze_panes!r}"
    )


def test_autofilter_set(workbook):
    ws = workbook["Dane_pivot_FULL"]
    assert ws.auto_filter.ref is not None, "auto_filter.ref is not set"
    assert ws.auto_filter.ref.startswith("A1"), (
        f"auto_filter.ref should start at A1, got {ws.auto_filter.ref!r}"
    )


def test_slownik_kolumn_has_all_columns(workbook):
    ws = workbook["11_Slownik_kolumn"]
    # header row + 67 column rows + legend sections (colour legends added below)
    min_expected = EXPECTED_N_COLS + 1  # at minimum header + all columns
    assert ws.max_row >= min_expected, (
        f"11_Slownik_kolumn: expected at least {min_expected} rows, got {ws.max_row}"
    )
    # Verify EN column names are in the first column (skip header row 1)
    col_a = [ws.cell(row=ri, column=1).value for ri in range(2, EXPECTED_N_COLS + 2)]
    from quiz_runner.excel_sheets import _PIVOT_COLUMNS
    expected_en = [en for en, *_ in _PIVOT_COLUMNS]
    assert col_a == expected_en, "Column EN names in Slownik_kolumn don't match _PIVOT_COLUMNS"
