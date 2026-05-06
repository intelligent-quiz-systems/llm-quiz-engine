"""
Write run_manifest.json and test_matrix.csv for a test series.
"""
import csv
import json
import re
from datetime import datetime
from pathlib import Path


def slug(topic: str, difficulty: str, count: int) -> str:
    """Build a safe filesystem slug from test parameters."""
    safe = re.sub(r"[^\w]+", "_", topic.strip().lower()).strip("_")
    return f"{safe}_{difficulty}_{count}"


def test_folder_name(nr: int, topic: str, difficulty: str, count: int, label: str = "") -> str:
    """Return zero-padded subfolder name for one test."""
    base = label.strip() if label and label.strip() else slug(topic, difficulty, count)
    return f"{nr:03d}_{base}"


def series_folder_name(ts: datetime | None = None) -> str:
    """Return timestamped top-level folder name for a series."""
    t = ts or datetime.now()
    return t.strftime("quiz_test_run_%Y%m%d_%H%M%S")


def write_manifest(series_dir: Path, config: dict) -> None:
    """Write run_manifest.json to series_dir."""
    data = {
        "series_folder": series_dir.name,
        "created_at": datetime.now().isoformat(),
        "total_tests": config.get("total_tests", 0),
        "output_root": str(series_dir.parent),
        "excel_mode": config.get("excel_mode", "auto"),
        "dry_run": config.get("dry_run", False),
        "mock_output": config.get("mock_output"),
    }
    (series_dir / "run_manifest.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def write_test_matrix(series_dir: Path, tests: list[dict]) -> None:
    """Write test_matrix.csv to series_dir."""
    path = series_dir / "test_matrix.csv"
    fieldnames = ["nr", "topic", "difficulty", "count", "label", "folder"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for t in tests:
            w.writerow({
                "nr": t.get("nr", ""),
                "topic": t.get("topic", ""),
                "difficulty": t.get("difficulty", ""),
                "count": t.get("count", ""),
                "label": t.get("label", ""),
                "folder": t.get("folder", ""),
            })
