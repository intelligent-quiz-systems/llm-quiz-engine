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


class _Tee:
    def __init__(self, original, buffer: StringIO) -> None:
        self._original = original
        self._buffer = buffer

    def write(self, data: str) -> None:
        try:
            self._original.write(data)
        except UnicodeEncodeError:
            self._original.write(data.encode("ascii", errors="replace").decode("ascii"))
        self._buffer.write(data)

    def flush(self) -> None:
        self._original.flush()

    def __getattr__(self, name: str):
        return getattr(self._original, name)


@contextmanager
def _capture_stdout(log_path: Path):
    """Tee stdout to a log file while keeping terminal output."""
    buf = StringIO()
    old = sys.stdout

    sys.stdout = _Tee(old, buf)
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


def _build_summary(
    config: dict,
    quiz_data: dict | None,
    duration: float,
    error: str | None,
    diagnostics: dict | None = None,
) -> dict:
    questions = quiz_data.get("questions", []) if quiz_data else []
    n = len(questions)
    ok = n > 0

    batch_log    = (diagnostics or {}).get("batch_log", [])
    total_tokens = sum(b.get("total_tokens") or 0 for b in batch_log) or None
    n_batches    = (diagnostics or {}).get("total_batches")
    n_rejected   = (diagnostics or {}).get("rejected_attempts")
    min_batch    = (diagnostics or {}).get("final_locked_batch_size")
    avg_tokens   = round(total_tokens / n, 3) if (total_tokens and n > 0) else None

    return {
        "topic": config["topic"],
        "difficulty": config["difficulty"],
        "count_requested": config["count"],
        "count_generated": n,
        "ok": ok,
        "status": "completed" if ok else "failed",
        "duration_seconds": round(duration, 3),
        "avg_seconds_per_question": round(duration / n, 3) if n > 0 else None,
        "n_batches": n_batches,
        "n_rejected_attempts": n_rejected,
        "min_batch_size": min_batch,
        "total_tokens": total_tokens,
        "avg_tokens_per_question": avg_tokens,
        "model": None,
        "error": error,
    }


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _save_stub(test_dir: Path, filename: str, note: str, extra: dict | None = None) -> None:
    data = {"note": note, **(extra or {})}
    _save_json(test_dir / filename, data)


def _save_diagnostics(test_dir: Path, diagnostics: dict) -> None:
    """Write per-test diagnostic JSON files from the diagnostics_out dict."""
    batch_log     = diagnostics.get("batch_log", [])
    rejection_log = diagnostics.get("rejection_log", [])
    gen_error     = diagnostics.get("generation_error")

    # generation_state.json — full state snapshot
    state_snapshot = {k: v for k, v in diagnostics.items() if k != "generation_error"}
    _save_json(test_dir / "generation_state.json", state_snapshot)

    # batch_summary.json — batch counts and per-batch log
    _save_json(test_dir / "batch_summary.json", {
        "total_batches":           diagnostics.get("total_batches", 0),
        "rejected_attempts":       diagnostics.get("rejected_attempts", 0),
        "initial_batch_size":      diagnostics.get("initial_batch_size"),
        "final_locked_batch_size": diagnostics.get("final_locked_batch_size"),
        "batches":                 batch_log,
    })

    # token_summary.json — aggregated totals + per-batch breakdown
    total_input     = sum(b.get("input_tokens")     or 0 for b in batch_log) or None
    total_output    = sum(b.get("output_tokens")    or 0 for b in batch_log) or None
    total_reasoning = sum(b.get("reasoning_tokens") or 0 for b in batch_log) or None
    total_all       = sum(b.get("total_tokens")     or 0 for b in batch_log) or None
    _save_json(test_dir / "token_summary.json", {
        "token_usage_known":      total_all is not None and total_all > 0,
        "total_input_tokens":     total_input,
        "total_output_tokens":    total_output,
        "total_reasoning_tokens": total_reasoning,
        "total_tokens":           total_all,
        "per_batch": [
            {
                "batch_number":       b.get("batch_number"),
                "accepted_questions": b.get("accepted_questions"),
                "input_tokens":       b.get("input_tokens"),
                "output_tokens":      b.get("output_tokens"),
                "reasoning_tokens":   b.get("reasoning_tokens"),
                "total_tokens":       b.get("total_tokens"),
                "attempt_duration_s": b.get("attempt_duration_seconds"),
                "system_prompt_chars": b.get("system_prompt_chars", 0),
                "user_prompt_chars":  b.get("user_prompt_chars", 0),
                "total_prompt_chars": b.get("total_prompt_chars", 0),
            }
            for b in batch_log
        ],
    })

    # rejections_detail.json — only written when there were rejections
    if rejection_log:
        _save_json(test_dir / "rejections_detail.json", {"rejections": rejection_log})

    # provider_error.json — only written when generation raised an exception
    if gen_error:
        data = gen_error if isinstance(gen_error, dict) else {"error": str(gen_error)}
        _save_json(test_dir / "provider_error.json", data)

    # quality_issues.json — only written when quality checks flagged issues
    quality_issues = diagnostics.get("quality_issues", [])
    if quality_issues:
        _save_json(test_dir / "quality_issues.json", {"issues": quality_issues})


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

    diagnostics: dict = {}

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
                    diagnostics_out=diagnostics,
                )
                if quiz_data is None:
                    error = "generate_quiz returned None"
            except Exception as exc:
                error = str(exc)
                print(f"[ERROR] {exc}")

        duration = time.monotonic() - start

    result = _build_summary(config, quiz_data, duration, error, diagnostics=diagnostics or None)

    if quiz_data:
        _save_json(test_dir / "quiz.json", quiz_data)
    if error:
        _save_json(test_dir / "error.json", {"error": error})

    _save_json(test_dir / "summary.json", result)

    if diagnostics.get("batch_log") is not None:
        _save_diagnostics(test_dir, diagnostics)
    else:
        # mock run or dry-run path — write minimal stubs
        _save_stub(test_dir, "batch_summary.json", "No LLM call — mock or dry-run.", {"batches": []})
        _save_stub(test_dir, "token_summary.json", "No LLM call — mock or dry-run.", {"total_tokens": None})

    label = "OK" if result["ok"] else "FAIL"
    print(f"  [{label}] {result['duration_seconds']:.1f}s | {result['count_generated']}/{result['count_requested']}q", flush=True)
    return result
