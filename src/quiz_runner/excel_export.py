"""
Generate Excel analysis file for a test series.
Requires openpyxl. Import-guarded: if openpyxl is missing, caller catches ImportError.
"""
from pathlib import Path

try:
    import openpyxl
except ImportError as exc:
    raise ImportError(
        "openpyxl is required for Excel export. Run: pip install openpyxl"
    ) from exc

from quiz_runner.excel_sheets import (
    add_pivot_full_sheet,
    add_dashboard_sheet,
    add_testy_sheet,
    add_podsumowania_sheet,
    add_bledy_per_test_sheet,
    add_kategorie_bledow_sheet,
    add_batche_srednie_sheet,
    add_guardrail_sheet,
    add_raw_rejections_sheet,
    add_raw_batches_sheet,
    add_quality_issues_sheet,
    add_slownik_kolumn_sheet,
)


def _enrich_results(
    results: list[dict],
    batch_rows: list[dict],
    rejection_rows: list[dict],
    quality_rows: list[dict],
) -> list[dict]:
    """Add per-test aggregated diagnostic fields to each result dict."""
    from collections import defaultdict

    # Token totals per test_id from batch_rows
    batch_by_test: dict[str, list] = defaultdict(list)
    for b in batch_rows:
        batch_by_test[b.get("test_id", "")].append(b)

    # Rejection duration totals per test_id
    rej_dur_by_test: dict[str, float] = defaultdict(float)
    for r in rejection_rows:
        dur = r.get("attempt_duration_seconds")
        if dur is not None:
            rej_dur_by_test[r.get("test_id", "")] += dur

    # Quality issue counts per test_id
    quality_by_test: dict[str, int] = defaultdict(int)
    for q in quality_rows:
        quality_by_test[q.get("test_id", "")] += 1

    enriched = []
    for r in results:
        test_id  = r.get("test_id", "")
        batches  = batch_by_test.get(test_id, [])

        def _sum(key):
            vals = [b.get(key) for b in batches if b.get(key) is not None]
            return sum(vals) if vals else None

        copy = dict(r)
        copy["total_input_tokens"]         = _sum("input_tokens")
        copy["total_output_tokens"]        = _sum("output_tokens")
        copy["total_reasoning_tokens"]     = _sum("reasoning_tokens")
        copy["n_quality_issues"]           = quality_by_test.get(test_id, 0)
        copy["total_rejection_duration_s"] = round(rej_dur_by_test.get(test_id, 0.0), 3) or None
        enriched.append(copy)

    return enriched


def build_excel(
    output_path: Path,
    results: list[dict],
    batch_rows: list[dict] | None = None,
    rejection_rows: list[dict] | None = None,
    quality_rows: list[dict] | None = None,
) -> None:
    """Build analysis.xlsx with all analytical sheets."""
    batch_rows     = batch_rows     or []
    rejection_rows = rejection_rows or []
    quality_rows   = quality_rows   or []

    enriched = _enrich_results(results, batch_rows, rejection_rows, quality_rows)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default blank sheet

    # Sheet order: Dane_pivot_FULL first (no prefix), then 01_..11_
    add_pivot_full_sheet(wb, enriched)
    add_dashboard_sheet(wb, results, enriched, batch_rows, rejection_rows)
    add_testy_sheet(wb, enriched)
    add_podsumowania_sheet(wb, results)
    add_bledy_per_test_sheet(wb, rejection_rows, results)
    add_kategorie_bledow_sheet(wb, rejection_rows)
    add_batche_srednie_sheet(wb, batch_rows, results)
    add_guardrail_sheet(wb, batch_rows)
    add_raw_rejections_sheet(wb, rejection_rows)
    add_raw_batches_sheet(wb, batch_rows)
    add_quality_issues_sheet(wb, quality_rows)
    add_slownik_kolumn_sheet(wb)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    print(f"[Excel] {output_path}")
