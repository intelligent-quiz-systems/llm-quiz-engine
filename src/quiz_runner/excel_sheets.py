"""
Excel sheet builders for quiz test series analysis.
Each function adds one sheet to the given Workbook.
"""
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# ── Colours ───────────────────────────────────────────────────────────────────
_HDR_BG   = "2F5496"
_HDR_FG   = "FFFFFF"
_OK_BG    = "E2EFDA"
_FAIL_BG  = "FCE4D6"
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
    ("n_batches",                "Liczba wsadów — n/a w obecnej wersji generatora"),
    ("n_rejected_attempts",      "Liczba odrzuconych prób — n/a w obecnej wersji"),
    ("min_batch_size",           "Minimalny rozmiar wsadu — n/a w obecnej wersji"),
    ("total_tokens",             "Łączna liczba tokenów — n/a w obecnej wersji"),
    ("avg_tokens_per_question",  "Średnia tokenów na pytanie — n/a w obecnej wersji"),
    ("error",                    "Komunikat błędu jeśli status != completed"),
    ("batch_number",             "Numer wsadu (zarezerwowane)"),
    ("reject_reason",            "Powód odrzucenia próby (zarezerwowane)"),
    ("reject_family",            "Rodzina błędu: output / quality / rate_limit (zarezerwowane)"),
    ("json_failure_kind",        "Szczegółowy typ błędu JSON (zarezerwowane)"),
    ("provider_error_message_type", "Typ komunikatu błędu providera (zarezerwowane)"),
    ("guardrail_chars",          "Długość guardraila w znakach (zarezerwowane)"),
    ("total_prompt_chars",       "Łączna długość promptu w znakach (zarezerwowane)"),
    ("input_tokens_estimate",    "Szacunkowe tokeny wejściowe (zarezerwowane)"),
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


# ── Sheet builders ────────────────────────────────────────────────────────────

def add_dashboard_sheet(wb: Workbook, results: list[dict]) -> None:
    ws = wb.create_sheet("00_Dashboard")
    completed = sum(1 for r in results if r.get("ok"))
    failed    = len(results) - completed
    total_dur = sum(r.get("duration_seconds") or 0 for r in results)

    ws.cell(row=1, column=1, value="Quiz Test Series — Summary").font = Font(bold=True, size=12)
    rows = [
        ("Generated at",    datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Total tests",     len(results)),
        ("Completed",       completed),
        ("Failed",          failed),
        ("Total duration (s)", round(total_dur, 1)),
        ("", ""),
        ("Note", "Batch / rejection / token data not available in current generator version."),
    ]
    for i, (lbl, val) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=lbl).font = Font(bold=True)
        ws.cell(row=i, column=2, value=val)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 55


def add_tests_sheet(wb: Workbook, results: list[dict]) -> None:
    ws = wb.create_sheet("01_Testy")
    headers = [
        "test_id", "topic", "difficulty",
        "count_requested", "count_generated", "status",
        "duration_seconds", "avg_seconds_per_question", "error",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)

    for ri, r in enumerate(results, start=2):
        vals = [
            r.get("test_id", NA), r.get("topic", NA), r.get("difficulty", NA),
            r.get("count_requested", NA), r.get("count_generated", NA),
            r.get("status", NA), r.get("duration_seconds", NA),
            r.get("avg_seconds_per_question", NA), r.get("error") or "",
        ]
        for col, v in enumerate(vals, 1):
            cell = ws.cell(row=ri, column=col, value=v)
            if r.get("ok"):
                cell.fill = PatternFill("solid", fgColor=_OK_BG)
            elif r.get("status") == "failed":
                cell.fill = PatternFill("solid", fgColor=_FAIL_BG)

    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_schema_sheet(wb: Workbook, name: str, headers: list[str], note: str = "") -> None:
    """Empty sheet with column headers — schema reserved for future data."""
    ws = wb.create_sheet(name)
    if note:
        c = ws.cell(row=1, column=1, value=f"[Note] {note}")
        c.font = Font(italic=True, color=_NOTE_FG)
    for col, h in enumerate(headers, 1):
        _hdr(ws, 2, col, h)
    _auto_width(ws)


def add_pivot_full_sheet(wb: Workbook, results: list[dict]) -> None:
    """Flat table with all test-level data — use for custom pivot / analysis."""
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
    for ri, r in enumerate(results, start=2):
        for col, h in enumerate(headers, 1):
            ws.cell(row=ri, column=col, value=r.get(h, NA))
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
