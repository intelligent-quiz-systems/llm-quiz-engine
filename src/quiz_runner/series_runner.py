"""
Run a series of tests from a matrix and coordinate report + Excel generation.
"""
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from quiz_runner.manifest import series_folder_name, test_folder_name, write_manifest, write_test_matrix
from quiz_runner.runner import run_single_test
from quiz_runner.report_builder import build_all_reports

try:
    from quiz_runner.excel_export import build_excel
    _EXCEL_AVAILABLE = True
except ImportError:
    _EXCEL_AVAILABLE = False


# ── Matrix loading ────────────────────────────────────────────────────────────

def load_matrix(matrix_path: Path) -> list[dict]:
    """Read test matrix CSV. Required columns: topic, difficulty, count."""
    if not matrix_path.exists():
        sys.exit(f"[ERROR] Matrix file not found: {matrix_path}")

    with matrix_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            sys.exit(f"[ERROR] Matrix file is empty: {matrix_path}")

        missing = [c for c in ("topic", "difficulty", "count") if c not in reader.fieldnames]
        if missing:
            sys.exit(f"[ERROR] Matrix missing required columns: {missing}")

        tests = []
        for i, row in enumerate(reader, start=1):
            try:
                count = int(row["count"].strip())
            except ValueError:
                sys.exit(f"[ERROR] Row {i}: 'count' must be an integer, got: {row['count']!r}")

            tests.append({
                "nr": i,
                "topic": row["topic"].strip(),
                "difficulty": row["difficulty"].strip(),
                "count": count,
                "label": row.get("label", "").strip(),
            })
    return tests


# ── Excel gating ──────────────────────────────────────────────────────────────

def _excel_enabled(n: int, mode: str) -> bool:
    if mode == "never":
        return False
    if mode == "always":
        return True
    return n >= 3  # auto: 3 or more tests


# ── Main series runner ────────────────────────────────────────────────────────

def run_series(
    tests: list[dict],
    output_root: Path,
    excel_mode: str = "auto",
    mock_quiz_path: Path | None = None,
    dry_run: bool = False,
) -> Path:
    """
    Run all tests sequentially. Creates a timestamped series folder.
    Returns the series folder path.
    """
    now = datetime.now()
    series_dir  = output_root / series_folder_name(now)
    tests_dir   = series_dir / "tests"
    reports_dir = series_dir / "reports"
    excel_dir   = series_dir / "excel"

    tests_dir.mkdir(parents=True, exist_ok=True)

    # Assign folder names before writing manifest/matrix
    for t in tests:
        t["folder"] = test_folder_name(
            t["nr"], t["topic"], t["difficulty"], t["count"], t.get("label", "")
        )

    write_manifest(series_dir, {
        "total_tests": len(tests),
        "excel_mode": excel_mode,
        "dry_run": dry_run,
        "mock_output": str(mock_quiz_path) if mock_quiz_path else None,
    })
    write_test_matrix(series_dir, tests)

    print(f"\nSeries : {series_dir.name}")
    print(f"Output : {series_dir}")
    print(f"Tests  : {len(tests)}")

    results: list[dict] = []
    for t in tests:
        result = run_single_test(
            nr=t["nr"],
            config=t,
            test_dir=tests_dir / t["folder"],
            mock_quiz_path=mock_quiz_path,
            dry_run=dry_run,
        )
        result["test_id"] = t["folder"]
        result["label"]   = t.get("label", "")
        results.append(result)

    # Collect per-test diagnostic data from saved JSON files
    batch_rows:     list[dict] = []
    rejection_rows: list[dict] = []
    quality_rows:   list[dict] = []

    for t, result in zip(tests, results):
        test_dir   = tests_dir / t["folder"]
        test_id    = t["folder"]

        batch_file = test_dir / "batch_summary.json"
        if batch_file.exists():
            try:
                data = json.loads(batch_file.read_text(encoding="utf-8"))
                for b in data.get("batches", []):
                    batch_rows.append({"test_id": test_id, **b})
            except Exception:
                pass

        rejection_file = test_dir / "rejections_detail.json"
        if rejection_file.exists():
            try:
                data = json.loads(rejection_file.read_text(encoding="utf-8"))
                for r in data.get("rejections", []):
                    rejection_rows.append({"test_id": test_id, **r})
            except Exception:
                pass

        quality_file = test_dir / "quality_issues.json"
        if quality_file.exists():
            try:
                data = json.loads(quality_file.read_text(encoding="utf-8"))
                for issue in data.get("issues", []):
                    quality_rows.append({"test_id": test_id, **issue})
            except Exception:
                pass

    build_all_reports(reports_dir, results)
    print(f"\nReports: {reports_dir}")

    if _excel_enabled(len(tests), excel_mode):
        if not _EXCEL_AVAILABLE:
            print("[WARN] openpyxl not installed — Excel skipped. Run: pip install openpyxl")
        else:
            try:
                git_branch = subprocess.check_output(
                    ["git", "branch", "--show-current"],
                    stderr=subprocess.DEVNULL, text=True,
                ).strip() or None
            except Exception:
                git_branch = None

            excel_path = excel_dir / "analysis.xlsx"
            build_excel(
                excel_path, results,
                batch_rows=batch_rows,
                rejection_rows=rejection_rows,
                quality_rows=quality_rows,
                run_id=series_dir.name,
                run_datetime=now.strftime("%Y-%m-%d %H:%M:%S"),
                git_branch=git_branch,
            )

    completed = sum(1 for r in results if r.get("ok"))
    print(f"\nDone: {completed}/{len(results)} completed.")
    return series_dir
