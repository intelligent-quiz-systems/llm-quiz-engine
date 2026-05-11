"""
Excel sheet builders for quiz test series analysis.
Each function adds one sheet to the given Workbook.
"""
from collections import Counter, defaultdict
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# ── Common header style ───────────────────────────────────────────────────────
_HDR_FG   = "000000"   # black text on coloured group backgrounds
_OK_BG    = "E2EFDA"
_FAIL_BG  = "FCE4D6"
_WARN_BG  = "FFF2CC"
_BLUE_HDR = "2F5496"   # used for helper sheets
_WHT      = "FFFFFF"

NA = "n/a"


# ── Pivot column group colours ────────────────────────────────────────────────
_GRP = {
    "run":       "B4C7E7",   # blue-gray  — run/series context
    "test_id":   "9DC3E6",   # blue       — test identification
    "test_ok":   "C6E0B4",   # green      — test results
    "event":     "D9C9E8",   # purple     — event core
    "batch":     "BDD7EE",   # light blue — batch efficiency
    "rejection": "F8CBAD",   # orange     — rejection detail
    "provider":  "FFCCCC",   # red        — provider errors
    "tokens":    "FFE699",   # yellow     — token data
    "guardrail": "C6EFCE",   # teal       — guardrail / prompt
    "summary":   "D9D9D9",   # gray       — test-level summary
    "ev_key":    "BDD7EE",   # same blue  — event key metrics
}

# ── Pivot column specification ────────────────────────────────────────────────
# (en_name, pl_short, rotate_90, group_key, col_width)
# rotate_90=True  → textRotation=90 (short numeric/bool cols)
# rotate_90=False → textRotation=0, wrap_text=True (text cols)
_PIVOT_COLUMNS: list[tuple] = [
    # Run context ─────────────────────────────────────────────────────────────
    ("series_group",           "seria testów",              False, "run",       22),
    ("run_datetime",           "data i czas serii",         False, "run",       20),
    ("git_branch",             "gałąź git",                 False, "run",       16),
    # Test identification ──────────────────────────────────────────────────────
    ("nr_global",              "nr globalny testu",         True,  "test_id",    8),
    ("label",                  "opis testu",                False, "test_id",   18),
    ("test_id",                "identyfikator testu / folder testu", False, "test_id", 28),
    ("topic",                  "temat",                     False, "test_id",   22),
    ("difficulty",             "poziom trudności",          False, "test_id",   12),
    # Test results ─────────────────────────────────────────────────────────────
    ("target_questions",       "cel pytań",                 True,  "test_ok",    8),
    ("accepted_questions",     "przyjęte pytania w całym teście", True, "test_ok", 8),
    ("missing_questions",      "brakujące pytania",         True,  "test_ok",    8),
    ("completion_pct",         "wykonanie testu [%]",       True,  "test_ok",    8),
    ("status",                 "status testu",              False, "test_ok",   12),
    ("duration_seconds",       "czas testu [s]",            True,  "test_ok",    8),
    # Event core ───────────────────────────────────────────────────────────────
    ("event_type",             "typ wiersza techniczny",    False, "event",     18),
    ("event_type_pl",          "typ wiersza po polsku",     False, "event",     20),
    ("event_seq",              "nr zdarzenia w teście",     True,  "event",      8),
    ("has_rejection",          "czy ten wiersz dotyczy odrzucenia", True, "event", 8),
    ("batch_number",           "nr wsadu",                  True,  "event",      8),
    # Batch efficiency ─────────────────────────────────────────────────────────
    ("batch_duration_seconds", "czas wsadu [s]",            True,  "batch",      8),
    ("attempts_count",         "próby w wsadzie",           True,  "batch",      8),
    ("rejected_attempts_count","odrzucone w wsadzie",       True,  "batch",      8),
    ("accepted_questions_count","pyt. zaakc. w wsadzie",   True,  "batch",      8),
    ("final_accepted_batch_size","ostateczny rozmiar wsadu",True,  "batch",      8),
    ("accepted_attempt_batch_size","rozmiar zaakc. próby", True,  "batch",      8),
    ("accepted_attempt_duration_seconds","czas zaakc. próby [s]",True,"batch",  8),
    ("gross_s_per_q",          "brutto [s/pyt]",            True,  "batch",      8),
    ("clean_s_per_q",          "netto [s/pyt]",             True,  "batch",      8),
    ("rejection_overhead_s_total","narzut odrzuceń [s]",    True,  "batch",      8),
    ("rejection_overhead_s_per_q","narzut/pyt [s]",         True,  "batch",      8),
    ("rejection_overhead_pct", "narzut odrzuceń [%]",       True,  "batch",      8),
    # Rejection detail ─────────────────────────────────────────────────────────
    ("attempt_number",         "nr próby",                  True,  "rejection",  8),
    ("attempted_batch_size",   "rozmiar próby",             True,  "rejection",  8),
    ("attempt_duration_seconds","czas próby [s]",           True,  "rejection",  8),
    ("reject_reason",          "powód odrzucenia EN",       False, "rejection", 14),
    ("reject_reason_pl",       "powód odrzucenia PL",       False, "rejection", 16),
    ("reject_family",          "rodzina błędu",             False, "rejection", 14),
    ("json_failure_kind",      "rodzaj błędu JSON",         False, "rejection", 16),
    ("json_failure_kind_pl",   "rodzaj błędu JSON PL",      False, "rejection", 16),
    # Provider errors ──────────────────────────────────────────────────────────
    ("provider_error_message_type","typ komunikatu błędu",  False, "provider",  18),
    ("provider_http_status",   "HTTP status",               True,  "provider",   8),
    ("provider_error_code",    "kod błędu prov.",           True,  "provider",   8),
    ("provider_error_type",    "typ błędu prov.",           False, "provider",  16),
    ("provider_error_message", "komunikat błędu prov.",     False, "provider",  22),
    ("provider_payload_present","payload obecny",           True,  "provider",   8),
    ("provider_failed_generation_present","nieudana gen. obecna",True,"provider",8),
    ("provider_failed_generation_blank","generacja pusta",  True,  "provider",   8),
    # Tokens ───────────────────────────────────────────────────────────────────
    ("token_usage_known",      "tokeny znane",              True,  "tokens",     8),
    ("output_tokens_wasted",   "tokeny zmarnowane",         True,  "tokens",     8),
    ("output_token_usage_pct", "tokeny wyj. [%]",           True,  "tokens",     8),
    ("input_tokens_estimate",  "tokeny wej. (est.)",        True,  "tokens",     8),
    ("input_tokens",           "tokeny wejściowe",          True,  "tokens",     8),
    ("output_tokens",          "tokeny wyjściowe",          True,  "tokens",     8),
    ("reasoning_tokens",       "tokeny reasoning",          True,  "tokens",     8),
    ("total_tokens",           "tokeny łącznie",            True,  "tokens",     8),
    # Guardrail / prompt ───────────────────────────────────────────────────────
    ("guardrail_question_count","pytania guardrail",        True,  "guardrail",  8),
    ("guardrail_chars",        "znaki guardrail",           True,  "guardrail",  8),
    ("total_prompt_chars",     "znaki promptu łącznie",     True,  "guardrail",  8),
    ("failed_generation_chars","znaki nieudanej gen.",      True,  "guardrail",  8),
    # Test-level summary ───────────────────────────────────────────────────────
    ("n_batches",              "batche łącznie (test)",     True,  "summary",    8),
    ("n_rejected_attempts",    "odrzucone próby (test)",    True,  "summary",    8),
    ("min_batch_size",         "min. rozmiar wsadu",        True,  "summary",    8),
    ("total_tokens_known",     "tokeny znane (test)",       True,  "summary",    8),
    ("tokens_per_target_q",    "tokeny / cel. pytanie",     True,  "summary",    8),
    ("rejected_time_s_detailed","czas odrzuceń szczeg. [s]",True, "summary",    8),
    # Event key metrics ────────────────────────────────────────────────────────
    ("event_duration_seconds", "czas zdarzenia [s]",        True,  "ev_key",     8),
    ("event_batch_size",       "rozmiar zdarzenia (wsad)",  True,  "ev_key",     8),
]

# Event row colours by event_type
_EVENT_FILL = {
    "accepted_batch":   "E2EFDA",
    "rejected_attempt": "FCE4D6",
    "quality_issue":    "FFF2CC",
    "generation_error": "FFCCCC",
}


# ── Style helpers ─────────────────────────────────────────────────────────────

def _hdr(ws, row: int, col: int, value: str):
    """Standard helper sheet header cell (blue bg, white text)."""
    c = ws.cell(row=row, column=col, value=value)
    c.font      = Font(bold=True, color=_WHT, size=10)
    c.fill      = PatternFill("solid", fgColor=_BLUE_HDR)
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


def _write_rows(ws, headers: list[str], rows: list[dict], start_row: int = 2) -> None:
    for ri, r in enumerate(rows, start=start_row):
        for col, h in enumerate(headers, 1):
            val = r.get(h, NA)
            if isinstance(val, dict):
                val = str(val)
            ws.cell(row=ri, column=col, value=val)


def _round(v, d: int = 3):
    try:
        return round(float(v), d) if v is not None else NA
    except (TypeError, ValueError):
        return NA


def _pct(num, den, d: int = 1):
    try:
        return round(100.0 * num / den, d) if den else NA
    except (TypeError, ValueError):
        return NA


# ── Pivot fact table ──────────────────────────────────────────────────────────

def add_pivot_full_sheet(wb: Workbook, event_rows: list[dict]) -> None:
    """
    Event warehouse fact table. Single bilingual header row:
      top line: Polish description
      bottom line: EN snake_case field name
    Columns use group-specific background colours.
    Numeric/short columns rotate 90°; text columns stay horizontal.
    """
    ws = wb.create_sheet("Dane_pivot_FULL")

    # ── Header row ────────────────────────────────────────────────────────────
    for col, (en, pl, rotate, grp, width) in enumerate(_PIVOT_COLUMNS, 1):
        cell_val = f"{pl}\n{en}"
        c = ws.cell(row=1, column=col, value=cell_val)
        c.font = Font(bold=True, color=_HDR_FG, size=9)
        c.fill = PatternFill("solid", fgColor=_GRP[grp])
        if rotate:
            c.alignment = Alignment(
                textRotation=90, wrap_text=False,
                vertical="bottom", horizontal="center",
            )
        else:
            c.alignment = Alignment(
                textRotation=0, wrap_text=True,
                vertical="bottom", horizontal="left",
            )
        ws.column_dimensions[get_column_letter(col)].width = width

    ws.row_dimensions[1].height = 130   # tall header for rotated text

    # ── Data rows ─────────────────────────────────────────────────────────────
    cols = [en for en, *_ in _PIVOT_COLUMNS]
    for ri, row in enumerate(event_rows, start=2):
        ev_type    = row.get("event_type", "")
        fill_color = _EVENT_FILL.get(ev_type)
        fill       = PatternFill("solid", fgColor=fill_color) if fill_color else None
        for col, key in enumerate(cols, 1):
            val = row.get(key)
            if isinstance(val, dict):
                val = str(val)
            cell = ws.cell(row=ri, column=col, value=val)
            if fill:
                cell.fill = fill

    # ── Freeze & filter ───────────────────────────────────────────────────────
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}1"


# ── Derived view sheets ───────────────────────────────────────────────────────

def add_dashboard_sheet(
    wb: Workbook,
    results: list[dict],
    enriched_results: list[dict],
    batch_rows: list[dict],
    rejection_rows: list[dict],
) -> None:
    ws = wb.create_sheet("01_Dashboard")
    completed  = sum(1 for r in results if r.get("ok"))
    failed     = len(results) - completed
    total_dur  = sum(r.get("duration_seconds") or 0 for r in results)
    total_tok  = sum(r.get("total_tokens") or 0 for r in results) or None
    total_rej  = sum(r.get("n_rejected_attempts") or 0 for r in results)
    total_rej_dur = sum((r.get("total_rejection_duration_s") or 0) for r in enriched_results)
    has_diag   = any(r.get("n_batches") is not None for r in results)
    n_bat_all  = sum(r.get("n_batches") or 0 for r in results)

    ws.cell(row=1, column=1, value="LLM Quiz — Test Series Summary").font = Font(bold=True, size=12)
    rows_data = [
        ("Generated at",              datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Total tests",               len(results)),
        ("Completed",                 completed),
        ("Failed",                    failed),
        ("Success rate [%]",          _pct(completed, len(results)) if results else NA),
        ("Total duration [s]",        _round(total_dur, 1)),
        ("Total tokens (all batches)", total_tok if total_tok else NA),
        ("Total API batches",         n_bat_all if has_diag else NA),
        ("Total rejected attempts",   total_rej if has_diag else NA),
        ("Rejection overhead [s]",    _round(total_rej_dur, 1) if has_diag else NA),
        ("Diagnostics available",     "yes" if has_diag else "no"),
    ]
    for i, (lbl, val) in enumerate(rows_data, start=3):
        ws.cell(row=i, column=1, value=lbl).font = Font(bold=True)
        ws.cell(row=i, column=2, value=val)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 30


def add_testy_sheet(wb: Workbook, enriched_results: list[dict]) -> None:
    ws = wb.create_sheet("02_Testy")
    headers = [
        "test_id", "topic", "difficulty",
        "count_requested", "count_generated", "status",
        "duration_seconds", "avg_seconds_per_question",
        "n_batches", "n_rejected_attempts", "min_batch_size",
        "total_tokens", "avg_tokens_per_question",
        "n_quality_issues", "total_rejection_duration_s", "error",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)
    for ri, r in enumerate(enriched_results, start=2):
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=ri, column=col, value=r.get(h, NA))
            if r.get("ok"):
                cell.fill = PatternFill("solid", fgColor=_OK_BG)
            elif r.get("status") == "failed":
                cell.fill = PatternFill("solid", fgColor=_FAIL_BG)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_podsumowania_sheet(wb: Workbook, results: list[dict]) -> None:
    ws = wb.create_sheet("03_Podsumowania")

    def _agg(rows, group_key):
        groups = defaultdict(list)
        for r in rows:
            groups[r.get(group_key, NA)].append(r)
        out = []
        for key, items in sorted(groups.items()):
            n   = len(items)
            ok  = sum(1 for r in items if r.get("ok"))
            dur = [r.get("duration_seconds") for r in items if r.get("duration_seconds") is not None]
            tok = [r.get("total_tokens") for r in items if r.get("total_tokens") is not None]
            rej = [r.get("n_rejected_attempts") or 0 for r in items]
            bat = [r.get("n_batches") or 0 for r in items]
            out.append({
                group_key:          key,
                "n_tests":          n,
                "n_completed":      ok,
                "success_rate_pct": _pct(ok, n),
                "avg_duration_s":   _round(sum(dur) / len(dur)) if dur else NA,
                "avg_tokens":       _round(sum(tok) / len(tok)) if tok else NA,
                "avg_n_rejected":   _round(sum(rej) / n),
                "avg_n_batches":    _round(sum(bat) / n),
            })
        return out

    ws.cell(row=1, column=1, value="Per topic").font = Font(bold=True, size=11)
    th = ["topic", "n_tests", "n_completed", "success_rate_pct",
          "avg_duration_s", "avg_tokens", "avg_n_rejected", "avg_n_batches"]
    for col, h in enumerate(th, 1):
        _hdr(ws, 2, col, h)
    tr = _agg(results, "topic")
    _write_rows(ws, th, tr, start_row=3)

    gap = 3 + len(tr) + 2
    ws.cell(row=gap, column=1, value="Per difficulty").font = Font(bold=True, size=11)
    dh = ["difficulty", "n_tests", "n_completed", "success_rate_pct",
          "avg_duration_s", "avg_tokens", "avg_n_rejected", "avg_n_batches"]
    for col, h in enumerate(dh, 1):
        _hdr(ws, gap + 1, col, h)
    dr = _agg(results, "difficulty")
    _write_rows(ws, dh, dr, start_row=gap + 2)
    _auto_width(ws)


def add_bledy_per_test_sheet(wb: Workbook, rejection_rows: list[dict], results: list[dict]) -> None:
    ws = wb.create_sheet("04_Bledy_per_test")
    headers = [
        "test_id", "topic", "difficulty",
        "n_rejections", "dominant_decision", "dominant_error_type",
        "total_rejection_duration_s", "mean_rejection_duration_s",
        "n_halt", "n_reduce", "n_retry",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)

    meta = {r.get("test_id", ""): r for r in results}
    groups: dict[str, list] = defaultdict(list)
    for r in rejection_rows:
        groups[r.get("test_id", NA)].append(r)

    rows_out = []
    for tid, items in sorted(groups.items()):
        decisions   = Counter(r.get("decision", NA) for r in items)
        error_types = Counter(r.get("error_type", NA) for r in items)
        durs = [r.get("attempt_duration_seconds") for r in items if r.get("attempt_duration_seconds") is not None]
        rm   = meta.get(tid, {})
        rows_out.append({
            "test_id":                    tid,
            "topic":                      rm.get("topic", NA),
            "difficulty":                 rm.get("difficulty", NA),
            "n_rejections":               len(items),
            "dominant_decision":          decisions.most_common(1)[0][0] if decisions else NA,
            "dominant_error_type":        error_types.most_common(1)[0][0] if error_types else NA,
            "total_rejection_duration_s": _round(sum(durs)),
            "mean_rejection_duration_s":  _round(sum(durs) / len(durs)) if durs else NA,
            "n_halt":                     decisions.get("halt", 0),
            "n_reduce":                   decisions.get("reduce", 0),
            "n_retry":                    decisions.get("retry", 0),
        })
    for ri, r in enumerate(rows_out, start=2):
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=ri, column=col, value=r.get(h, NA))
            if r.get("n_halt", 0) > 0:
                cell.fill = PatternFill("solid", fgColor=_FAIL_BG)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_kategorie_bledow_sheet(wb: Workbook, rejection_rows: list[dict]) -> None:
    ws = wb.create_sheet("05_Kategorie_bledow")
    headers = [
        "decision", "error_type", "n_attempts",
        "mean_duration_s", "mean_batch_size", "pct_of_all_rejections",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)

    groups: dict[tuple, list] = defaultdict(list)
    for r in rejection_rows:
        groups[(r.get("decision", NA), r.get("error_type", NA))].append(r)

    total = len(rejection_rows)
    rows_out = []
    for (decision, error_type), items in sorted(groups.items()):
        durs  = [x.get("attempt_duration_seconds") for x in items if x.get("attempt_duration_seconds") is not None]
        sizes = [x.get("attempted_batch_size") for x in items if x.get("attempted_batch_size") is not None]
        rows_out.append({
            "decision":              decision,
            "error_type":            error_type,
            "n_attempts":            len(items),
            "mean_duration_s":       _round(sum(durs) / len(durs)) if durs else NA,
            "mean_batch_size":       _round(sum(sizes) / len(sizes), 1) if sizes else NA,
            "pct_of_all_rejections": _pct(len(items), total) if total else NA,
        })
    _write_rows(ws, headers, rows_out)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_batche_srednie_sheet(wb: Workbook, batch_rows: list[dict], results: list[dict]) -> None:
    ws = wb.create_sheet("06_Batche_srednie")
    headers = [
        "test_id", "topic", "difficulty",
        "n_batches", "avg_batch_size", "avg_duration_s",
        "avg_input_tokens", "avg_output_tokens",
        "avg_reasoning_tokens", "avg_total_tokens",
        "avg_prompt_chars", "avg_guardrail_chars",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)

    meta   = {r.get("test_id", ""): r for r in results}
    groups: dict[str, list] = defaultdict(list)
    for b in batch_rows:
        groups[b.get("test_id", NA)].append(b)

    rows_out = []
    for tid, items in sorted(groups.items()):
        def _avg(key):
            vals = [x.get(key) for x in items if x.get(key) is not None]
            return _round(sum(vals) / len(vals)) if vals else NA

        rm = meta.get(tid, {})
        rows_out.append({
            "test_id":              tid,
            "topic":                rm.get("topic", NA),
            "difficulty":           rm.get("difficulty", NA),
            "n_batches":            len(items),
            "avg_batch_size":       _avg("accepted_batch_size"),
            "avg_duration_s":       _avg("attempt_duration_seconds"),
            "avg_input_tokens":     _avg("input_tokens"),
            "avg_output_tokens":    _avg("output_tokens"),
            "avg_reasoning_tokens": _avg("reasoning_tokens"),
            "avg_total_tokens":     _avg("total_tokens"),
            "avg_prompt_chars":     _avg("total_prompt_chars"),
            "avg_guardrail_chars":  _avg("guardrail_chars"),
        })
    _write_rows(ws, headers, rows_out)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_guardrail_sheet(wb: Workbook, batch_rows: list[dict]) -> None:
    ws = wb.create_sheet("07_Guardrail")
    headers = [
        "test_id", "batch_number",
        "guardrail_question_count", "guardrail_chars",
        "system_prompt_chars", "user_prompt_chars", "total_prompt_chars",
        "input_tokens",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)
    active = [r for r in batch_rows if r.get("guardrail_question_count")]
    _write_rows(ws, headers, active)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_raw_rejections_sheet(wb: Workbook, rejection_rows: list[dict]) -> None:
    ws = wb.create_sheet("08_Raw_rejections")
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
            cell = ws.cell(row=ri, column=col, value=val)
            if r.get("decision") == "halt":
                cell.fill = PatternFill("solid", fgColor=_FAIL_BG)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_raw_batches_sheet(wb: Workbook, batch_rows: list[dict]) -> None:
    ws = wb.create_sheet("09_Raw_batches")
    headers = [
        "test_id", "batch_number", "accepted_batch_size", "accepted_questions",
        "total_attempts", "attempt_duration_seconds",
        "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
        "system_prompt_chars", "user_prompt_chars", "total_prompt_chars",
        "guardrail_question_count", "guardrail_chars",
    ]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)
    _write_rows(ws, headers, batch_rows)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_quality_issues_sheet(wb: Workbook, quality_rows: list[dict]) -> None:
    ws = wb.create_sheet("10_Quality_issues")
    headers = ["test_id", "issue_type", "question_index", "question_text", "detail"]
    for col, h in enumerate(headers, 1):
        _hdr(ws, 1, col, h)
    _write_rows(ws, headers, quality_rows)
    ws.freeze_panes = "A2"
    _auto_width(ws)


def add_slownik_kolumn_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("11_Slownik_kolumn")
    _hdr(ws, 1, 1, "Kolumna (EN snake_case)")
    _hdr(ws, 1, 2, "Opis PL")
    _hdr(ws, 1, 3, "Grupa")
    for ri, (en, pl, _, grp, _w) in enumerate(_PIVOT_COLUMNS, start=2):
        ws.cell(row=ri, column=1, value=en)
        ws.cell(row=ri, column=2, value=pl)
        c = ws.cell(row=ri, column=3, value=grp)
        c.fill = PatternFill("solid", fgColor=_GRP[grp])
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 12
    ws.freeze_panes = "A2"
