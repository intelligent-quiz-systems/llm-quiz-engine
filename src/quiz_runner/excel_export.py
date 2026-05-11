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
    add_dashboard_sheet,
    add_tests_sheet,
    add_pivot_full_sheet,
    add_batch_efficiency_sheet,
    add_rejections_detail_sheet,
    add_rejection_categories_sheet,
    add_guardrail_stats_sheet,
    add_quality_issues_sheet,
    add_column_dict_sheet,
)


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

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default blank sheet

    add_pivot_full_sheet(wb, results)
    add_dashboard_sheet(wb, results, batch_rows=batch_rows, rejection_rows=rejection_rows)
    add_tests_sheet(wb, results)
    add_batch_efficiency_sheet(wb, batch_rows)
    add_rejections_detail_sheet(wb, rejection_rows)
    add_rejection_categories_sheet(wb, rejection_rows)
    add_guardrail_stats_sheet(wb, batch_rows)
    add_quality_issues_sheet(wb, quality_rows)
    add_column_dict_sheet(wb)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    print(f"[Excel] {output_path}")
