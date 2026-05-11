"""
Excel sheet builders for quiz test series analysis.
Each function adds one sheet to the given Workbook.
"""
from collections import Counter, defaultdict
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# ── Colours ───────────────────────────────────────────────────────────────────
_HDR_BG   = "2F5496"
_HDR_FG   = "FFFFFF"
_OK_BG    = "E2EFDA"
_FAIL_BG  = "FCE4D6"
_WARN_BG  = "FFF2CC"
_NOTE_FG  = "808080"

NA = "n/a"

# ── Column dictionary entries ─────────────────────────────────────────────────
COLUMN_DICT = [
    ("test_id",                  "Identyfikator testu (nazwa folderu)"),
    ("label",                    "Opcjonalna etykieta testu"),
    ("topic",                    "Temat quizu"),
    ("difficulty",               "Poziom trudności: easy / medium / hard"),
    ("count_requested",          "Żądana liczba pytań"),
    ("count_generated",          "Wygenerowana liczba pytań"),
    ("ok",                       "True jeśli test zakończony sukcesem"),
    ("status",                   "Status: completed / failed / partial / dry-run"),
    ("duration_seconds",         "Czas trwania testu w sekundach"),
    ("avg_seconds_per_question", "Średni czas na jedno pytanie (s)"),
    ("n_batches",                "Liczba zaakceptowanych wsadów"),
    ("n_rejected_attempts",      "Liczba odrzuconych prób generacji"),
    ("min_batch_size",           "Minimalny rozmiar wsadu osiągnięty podczas generacji"),
    ("total_tokens",             "Łączna liczba tokenów (input + output)"),
    ("avg_tokens_per_question",  "Średnia tokenów na wygenerowane pytanie"),
    ("error",                    "Komunikat błędu jeśli status != completed"),
    ("batch_number",             "Numer wsadu w ramach testu (1-based)"),
    ("accepted_batch_size",      "Rozmiar zaakceptowanego wsadu (liczba pytań)"),
    ("accepted_questions",       "Liczba pytań zaakceptowanych w tym wsadzie"),
    ("total_attempts",           "Łączna liczba prób dla tego wsadu"),
    ("attempt_duration_seconds", "Czas trwania próby w sekundach"),
    ("input_tokens",             "Tokeny wejściowe (prompt)"),
    ("output_tokens",            "Tokeny wyjściowe (odpowiedź modelu)"),
    ("reasoning_tokens",         "Tokeny reasoning (jeśli dotyczy)"),
    ("total_tokens_batch",       "Łączne tokeny dla wsadu"),
    ("system_prompt_chars",      "Długość system prompt w znakach"),
    ("user_prompt_chars",        "Długość user prompt w znakach"),
    ("total_prompt_chars",       "Łączna długość promptu w znakach"),
    ("guardrail_question_count", "Liczba pytań w kontekście guardrail"),
    ("guardrail_chars",          "Długość tekstu guardrail w znakach"),
    ("decision",                 "Decyzja po odrzuceniu: reduce / retry / halt"),
    ("error_type",               "Typ wyjątku Python"),
    ("attempted_batch_size",     "Rozmiar wsadu w momencie odrzucenia"),
    ("provider_error_info",      "Szczegóły błędu od providera LLM"),
    ("issue_type",               "Typ problemu jakości: duplicate / similar / duplicate_options"),
    ("question_index",           "Indeks pytania (0-based)"),
    ("question_text",            "Tekst pytania"),
    ("detail",                   "Szczegół problemu"),
]

# ── Style helpers ─────────────────────────────────────────────────────────────

def _hdr(ws, row: int, col: int, value: str):
    c = ws.cell(row=row, column=col, value=value)
    c.font = Font(bold=True, color=_HDR_FG, size=10)
    c.fill = PatternFill("solid", fgColor=_HDR_BG)
    c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    return c


def _auto_width(ws, min_w: int = 10, max_w: int = 45) -> None:
    for col_cells in ws.columns:
        width = max(
            (len(str(c.value)) if c.value is not None else 0 for c in col_cells),
            default=min_w,
        )
        ltr = get_column_letter(col_cells[0].column)
        ws.column_dimensions[ltr].width = min(max(width + 2, min_w), max_w)


def _data_rows(ws, headers: list[str], rows: list[dict], start_row: int = 2) -> None:
    for ri, r in enumerate(rows, start=start_row):
        for col, h in enumerate(headers, 1):
            ws.cell(row=ri, column=col, value=r.get(h, NA))


# ── Sheet builders ────────────────────────────────────────────────────────────

def add_dashboard_sheet(
    wb: Workbook,
    results: list[dict],
    batch_rows: list[dict] | None = None,
    rejection_rows: list[dict] | None = None,
) -> None:
    ws = wb.create_sheet("00_Dashboard")
    completed  = sum(1 for r in results if r.get("ok"))
    failed     = len(results) - completed
    total_dur  = sum(r.get("duration_seconds") or 0 for r in results)
    total_tok  = sum(r.get("total_tokens") or 0 for r in results) or None
    total_rej  = sum(r.get("n_rejected_attempts") or 0 for r in results)
    has_diag   = any(r.get("n_batches") is not None for r in results)

    ws.cell(row=1, column=1, value="Quiz Test Series — Summary").font = Font(bold=True, size=12)
    rows_data = [
        ("Generated at",           datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Total tests",            len(results)),
        ("Completed",              completed),
        ("Failed",                 failed),
        ("Total duration (s)",     round(total_dur, 1)),
        ("Total tokens",           total_tok if total_tok else "n/a"),
        ("Total rejected attempts", total_rej if has_diag else "n/a"),
        ("Diagnostics available",  "yes" if has_diag else "no — run with diagnostics/raw-generation-logs"),
    ]
    for i, (lbl, val) in enumerate(rows_data, start=3):
        ws.cell(row=i, column=1, value=lbl).font = Font(bold=True)
        ws.cell(row=i, column=2, value=val)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 58


def add_tests_sheet(wb: Workbook, results: list[dict]) -> None:
    ws = wb.create_sheet("01_Testy")
    headers = [
        "test_id", "topic", "difficulty",
        "count_requested", "count_generated", "status",
        "duration_seconds", "avg_seconds_per_question",
        "n_batches", "n_rejected_attempts", "min_batch_size",
        "total_tokens", "avg_tokens_per_question", "error",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)

    for ri, r in enumerate(results, start=2):
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=ri, column=col, value=r.get(h, NA))
            if r.get("ok"):
                cell.fill = PatternFill("solid", fgColor=_OK_BG)
            elif r.get("status") == "failed":
                cell.fill = PatternFill("solid", fgColor=_FAIL_BG)

    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_pivot_full_sheet(wb: Workbook, results: list[dict]) -> None:
    """Flat table with all test-level data — ready for pivot / analysis."""
    ws = wb.create_sheet("Dane_pivot_FULL")
    headers = [
        "test_id", "label", "topic", "difficulty",
        "count_requested", "count_generated", "ok", "status",
        "duration_seconds", "avg_seconds_per_question",
        "n_batches", "n_rejected_attempts", "min_batch_size",
        "total_tokens", "avg_tokens_per_question", "error",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)
    _data_rows(ws, headers, results)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_batch_efficiency_sheet(wb: Workbook, batch_rows: list[dict]) -> None:
    """Per-batch timing, token, and prompt size data."""
    ws = wb.create_sheet("03_Batch_efficiency")
    headers = [
        "test_id", "batch_number", "accepted_batch_size", "accepted_questions",
        "total_attempts", "attempt_duration_seconds",
        "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
        "system_prompt_chars", "user_prompt_chars", "total_prompt_chars",
        "guardrail_question_count", "guardrail_chars",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)
    _data_rows(ws, headers, batch_rows)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_rejections_detail_sheet(wb: Workbook, rejection_rows: list[dict]) -> None:
    """Per-rejection attempt detail."""
    ws = wb.create_sheet("04_Rejections_detail")
    headers = [
        "test_id", "batch_number", "attempt_number", "attempted_batch_size",
        "decision", "error_type", "attempt_duration_seconds",
        "system_prompt_chars", "user_prompt_chars", "total_prompt_chars",
        "guardrail_question_count", "guardrail_chars", "provider_error_info",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)
    for ri, r in enumerate(rejection_rows, start=2):
        for col, h in enumerate(headers, 1):
            val = r.get(h, NA)
            if isinstance(val, dict):
                val = str(val)
            ws.cell(row=ri, column=col, value=val)
            if r.get("decision") == "halt":
                ws.cell(row=ri, column=col).fill = PatternFill("solid", fgColor=_FAIL_BG)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_rejection_categories_sheet(wb: Workbook, rejection_rows: list[dict]) -> None:
    """Aggregated rejection counts by decision and error_type."""
    ws = wb.create_sheet("05_Rejection_categories")
    headers = [
        "decision", "error_type", "n_attempts",
        "mean_duration_seconds", "mean_attempted_batch_size",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)

    groups: dict[tuple, list] = defaultdict(list)
    for r in rejection_rows:
        key = (r.get("decision", NA), r.get("error_type", NA))
        groups[key].append(r)

    for ri, ((decision, error_type), items) in enumerate(sorted(groups.items()), start=2):
        durations = [x.get("attempt_duration_seconds") for x in items if x.get("attempt_duration_seconds") is not None]
        sizes     = [x.get("attempted_batch_size") for x in items if x.get("attempted_batch_size") is not None]
        row_vals  = [
            decision, error_type, len(items),
            round(sum(durations) / len(durations), 3) if durations else NA,
            round(sum(sizes) / len(sizes), 1) if sizes else NA,
        ]
        for col, v in enumerate(row_vals, 1):
            ws.cell(row=ri, column=col, value=v)

    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_guardrail_stats_sheet(wb: Workbook, batch_rows: list[dict]) -> None:
    """Per-batch guardrail context size."""
    ws = wb.create_sheet("06_Guardrail_stats")
    headers = [
        "test_id", "batch_number",
        "guardrail_question_count", "guardrail_chars",
        "system_prompt_chars", "user_prompt_chars", "total_prompt_chars",
        "input_tokens",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)
    guardrail_rows = [r for r in batch_rows if r.get("guardrail_question_count")]
    _data_rows(ws, headers, guardrail_rows)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_quality_issues_sheet(wb: Workbook, quality_rows: list[dict]) -> None:
    """Quality issues detected across all tests."""
    ws = wb.create_sheet("07_Quality_issues")
    headers = [
        "test_id", "issue_type", "question_index", "question_text", "detail",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)
    _data_rows(ws, headers, quality_rows)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_column_dict_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Slownik_kolumn")
    _hdr(ws, 1, 1, "Kolumna")
    _hdr(ws, 1, 2, "Opis")
    for ri, (col, desc) in enumerate(COLUMN_DICT, start=2):
        ws.cell(row=ri, column=1, value=col)
        ws.cell(row=ri, column=2, value=desc)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 58
