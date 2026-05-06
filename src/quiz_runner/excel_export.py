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
    add_schema_sheet,
    add_pivot_full_sheet,
    add_column_dict_sheet,
)
from quiz_runner.report_builder import (
    BATCH_EFFICIENCY_FIELDS,
    REJECTIONS_DETAIL_FIELDS,
    REJECTION_CATEGORIES_FIELDS,
    GUARDRAIL_STATS_FIELDS,
)

_SCHEMA_NOTE = "Data not available in current generator version. Schema reserved for future diagnostics."


def build_excel(output_path: Path, results: list[dict]) -> None:
    """Build analysis.xlsx with all analytical sheets."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove default blank sheet

    add_pivot_full_sheet(wb, results)
    add_dashboard_sheet(wb, results)
    add_tests_sheet(wb, results)
    add_schema_sheet(wb, "03_Batch_efficiency",    BATCH_EFFICIENCY_FIELDS,    _SCHEMA_NOTE)
    add_schema_sheet(wb, "04_Rejections_detail",   REJECTIONS_DETAIL_FIELDS,   _SCHEMA_NOTE)
    add_schema_sheet(wb, "05_Rejection_categories", REJECTION_CATEGORIES_FIELDS, _SCHEMA_NOTE)
    add_schema_sheet(wb, "06_Guardrail_stats",     GUARDRAIL_STATS_FIELDS,     _SCHEMA_NOTE)
    add_column_dict_sheet(wb)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    print(f"[Excel] {output_path}")
