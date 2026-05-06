#!/usr/bin/env python3
"""
Quiz test runner — CLI entry point.

Usage examples:
  python scripts/run_quiz_tests.py --topic "Python" --difficulty easy --count 20 --output-root /path/to/results
  python scripts/run_quiz_tests.py --matrix tests/fixtures/test_matrix_sample.csv --output-root /path/to/results
  python scripts/run_quiz_tests.py --matrix tests/fixtures/test_matrix_sample.csv --output-root /path/to/results --dry-run
  python scripts/run_quiz_tests.py --topic "Python" --difficulty easy --count 5 --output-root /path --excel always
  python scripts/run_quiz_tests.py --matrix tests/fixtures/test_matrix_sample.csv --output-root /path --no-excel
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

# Make src/ importable regardless of working directory
_PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

from quiz_runner.series_runner import load_matrix, run_series


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run quiz generation tests and produce reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--topic",  help="Single test: quiz topic")
    mode.add_argument("--matrix", help="Series: path to test matrix CSV file")

    p.add_argument("--difficulty", choices=["easy", "medium", "hard"],
                   help="Difficulty level (required for --topic)")
    p.add_argument("--count", type=int,
                   help="Number of questions (required for --topic)")
    p.add_argument("--label", default="",
                   help="Optional label for a single test run")

    p.add_argument("--output-root",
                   help="Root folder for test output. Also accepts QUIZ_OUTPUT_ROOT env var.")
    p.add_argument("--dry-run", action="store_true",
                   help="Create folder structure and skip LLM calls.")
    p.add_argument("--mock-output",
                   help="Path to a quiz JSON file used instead of calling the LLM.")

    excel_group = p.add_mutually_exclusive_group()
    excel_group.add_argument("--excel",
                             choices=["auto", "always", "never"], default="auto",
                             help="Excel mode: auto (>=3 tests), always, never. Default: auto.")
    excel_group.add_argument("--no-excel", action="store_true",
                             help="Shorthand for --excel never.")

    return p.parse_args()


def _resolve_output_root(args: argparse.Namespace) -> Path:
    root = args.output_root or os.environ.get("QUIZ_OUTPUT_ROOT")
    if root:
        return Path(root)
    if args.dry_run:
        tmp = Path(tempfile.mkdtemp(prefix="quiz_dry_run_"))
        print(f"[dry-run] No output-root set — using temp folder: {tmp}")
        return tmp
    sys.exit(
        "[ERROR] Output folder not specified.\n"
        "        Provide --output-root <path> or set the QUIZ_OUTPUT_ROOT environment variable."
    )


def main() -> None:
    args = _parse_args()

    if args.topic and not (args.difficulty and args.count):
        sys.exit("[ERROR] --topic requires both --difficulty and --count.")

    output_root = _resolve_output_root(args)
    output_root.mkdir(parents=True, exist_ok=True)

    mock_path: Path | None = None
    if args.mock_output:
        mock_path = Path(args.mock_output)
        if not mock_path.exists():
            sys.exit(f"[ERROR] Mock output file not found: {mock_path}")

    excel_mode = "never" if args.no_excel else args.excel

    if args.topic:
        tests = [{
            "nr": 1,
            "topic": args.topic,
            "difficulty": args.difficulty,
            "count": args.count,
            "label": args.label,
        }]
    else:
        tests = load_matrix(Path(args.matrix))

    series_dir = run_series(
        tests=tests,
        output_root=output_root,
        excel_mode=excel_mode,
        mock_quiz_path=mock_path,
        dry_run=args.dry_run,
    )
    print(f"\nSeries folder: {series_dir}")


if __name__ == "__main__":
    main()
