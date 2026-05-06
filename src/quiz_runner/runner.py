"""
Execute a single quiz generation test and save all output files.
"""
import json
import sys
import time
from contextlib import contextmanager
from io import StringIO
from pathlib import Path


def _setup_src_path() -> None:
    """Ensure src/ is on sys.path so llm imports resolve."""
    src = Path(__file__).resolve().parents[1]  # src/quiz_runner -> src/
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


@contextmanager
def _capture_stdout(log_path: Path):
    """Tee stdout to a log file while keeping terminal output."""
    buf = StringIO()
    old = sys.stdout

    class _Tee:
        def write(self, data: str) -> None:
            old.write(data)
            buf.write(data)

        def flush(self) -> None:
            old.flush()

        def __getattr__(self, name: str):
            return getattr(old, name)

    sys.stdout = _Tee()
    try:
        yield buf
    finally:
        sys.stdout = old
        log_path.write_text(buf.getvalue(), encoding="utf-8")


def _load_mock_quiz(mock_path: Path) -> dict | None:
    try:
        return json.loads(mock_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[ERROR] Could not load mock output: {exc}")
        return None


def _build_summary(config: dict, quiz_data: dict | None, duration: float, error: str | None) -> dict:
    questions = quiz_data.get("questions", []) if quiz_data else []
    n = len(questions)
    ok = n > 0
    return {
        "topic": config["topic"],
        "difficulty": config["difficulty"],
        "count_requested": config["count"],
        "count_generated": n,
        "ok": ok,
        "status": "completed" if ok else "failed",
        "duration_seconds": round(duration, 3),
        "avg_seconds_per_question": round(duration / n, 3) if n > 0 else None,
        "n_batches": None,
        "n_rejected_attempts": None,
        "min_batch_size": None,
        "total_tokens": None,
        "avg_tokens_per_question": None,
        "model": None,
        "error": error,
    }


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _save_stub(test_dir: Path, filename: str, note: str, extra: dict | None = None) -> None:
    data = {"note": note, **(extra or {})}
    _save_json(test_dir / filename, data)


def run_single_test(
    nr: int,
    config: dict,
    test_dir: Path,
    mock_quiz_path: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Run one quiz generation test. Returns result dict.
    config keys: topic, difficulty, count, label (optional)
    """
    test_dir.mkdir(parents=True, exist_ok=True)
    log_path = test_dir / "run.log"

    print(f"\n[{nr:03d}] {config['topic']} / {config['difficulty']} / {config['count']}q", flush=True)

    if dry_run:
        print("  [dry-run] skipping LLM call", flush=True)
        result = _build_summary(config, None, 0.0, "dry-run")
        result["status"] = "dry-run"
        log_path.write_text("[dry-run]\n", encoding="utf-8")
        _save_json(test_dir / "summary.json", result)
        _save_stub(test_dir, "batch_summary.json", "Batch data not available.", {"batches": []})
        _save_stub(test_dir, "token_summary.json", "Token data not available.", {"total_tokens": None})
        return result

    with _capture_stdout(log_path):
        start = time.monotonic()
        quiz_data: dict | None = None
        error: str | None = None

        if mock_quiz_path:
            print(f"[mock] loading from {mock_quiz_path}")
            quiz_data = _load_mock_quiz(mock_quiz_path)
            if quiz_data is None:
                error = "Failed to load mock output"
        else:
            _setup_src_path()
            try:
                from llm.llm import generate_quiz  # deferred — src/ must be on path
                quiz_data = generate_quiz(
                    topic=config["topic"],
                    difficulty=config["difficulty"],
                    num_questions=config["count"],
                )
                if quiz_data is None:
                    error = "generate_quiz returned None"
            except Exception as exc:
                error = str(exc)
                print(f"[ERROR] {exc}")

        duration = time.monotonic() - start

    result = _build_summary(config, quiz_data, duration, error)

    if quiz_data:
        _save_json(test_dir / "quiz.json", quiz_data)
    if error:
        _save_json(test_dir / "error.json", {"error": error})

    _save_json(test_dir / "summary.json", result)
    _save_stub(test_dir, "batch_summary.json", "Batch data not available in current generator version.", {"batches": []})
    _save_stub(test_dir, "token_summary.json", "Token data not available in current generator version.", {"total_tokens": None, "per_call": []})

    label = "OK" if result["ok"] else "FAIL"
    print(f"  [{label}] {result['duration_seconds']:.1f}s | {result['count_generated']}/{result['count_requested']}q", flush=True)
    return result
