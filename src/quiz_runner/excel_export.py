"""
Generate Excel analysis file for a test series.
Requires openpyxl. Import-guarded: if openpyxl is missing, caller catches ImportError.
"""
from collections import defaultdict
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

# ── Event type translations ───────────────────────────────────────────────────

_EVENT_TYPE_PL = {
    "accepted_batch":   "Zaakceptowany wsad",
    "rejected_attempt": "Odrzucona próba",
    "quality_issue":    "Problem jakości",
    "generation_error": "Błąd generacji",
}

_DECISION_PL = {
    "reduce": "Zmniejsz wsad",
    "retry":  "Ponów próbę",
    "halt":   "Zatrzymaj",
}

_REJECT_FAMILY = {
    "RateLimitError":               "rate_limit",
    "BadRequestError":              "provider",
    "LengthFinishReasonError":      "output",
    "APIConnectionError":           "network",
    "APITimeoutError":              "network",
    "ContentFilterFinishReasonError": "provider",
}


def _reject_family(error_type: str | None) -> str | None:
    if not error_type:
        return None
    for k, v in _REJECT_FAMILY.items():
        if k in error_type:
            return v
    return "unknown"


def _round(v, d: int = 3):
    try:
        return round(float(v), d) if v is not None else None
    except (TypeError, ValueError):
        return None


# ── Event warehouse builder ───────────────────────────────────────────────────

def _build_event_rows(
    results: list[dict],
    batch_rows: list[dict],
    rejection_rows: list[dict],
    quality_rows: list[dict],
    run_id: str = "",
    run_datetime: str | None = None,
    git_branch: str | None = None,
) -> list[dict]:
    """
    Build one row per event: accepted_batch, rejected_attempt, quality_issue,
    generation_error. Events are ordered chronologically within each test
    (rejections before their corresponding accepted batch, then quality issues).
    """
    # ── Index source data ─────────────────────────────────────────────────────
    test_meta: dict[str, dict] = {}
    for i, r in enumerate(results, 1):
        tid = r.get("test_id", "")
        test_meta[tid] = {**r, "_nr_global": i}

    batch_by_test: dict[str, list] = defaultdict(list)
    for b in batch_rows:
        batch_by_test[b.get("test_id", "")].append(b)

    rej_by_test: dict[str, list] = defaultdict(list)
    for r in rejection_rows:
        rej_by_test[r.get("test_id", "")].append(r)

    quality_by_test: dict[str, list] = defaultdict(list)
    for q in quality_rows:
        quality_by_test[q.get("test_id", "")].append(q)

    # Rejection overhead per (test_id, batch_number)
    rej_overhead_dur: dict[tuple, float] = defaultdict(float)
    rej_overhead_cnt: dict[tuple, int]   = defaultdict(int)
    for r in rejection_rows:
        key = (r.get("test_id", ""), r.get("batch_number"))
        rej_overhead_dur[key] += r.get("attempt_duration_seconds") or 0
        rej_overhead_cnt[key] += 1

    # Total rejection time per test
    rej_total_time: dict[str, float] = defaultdict(float)
    for r in rejection_rows:
        rej_total_time[r.get("test_id", "")] += r.get("attempt_duration_seconds") or 0

    # ── Build rows ────────────────────────────────────────────────────────────
    event_rows: list[dict] = []

    for result in results:
        tid    = result.get("test_id", "")
        nr     = test_meta[tid]["_nr_global"]
        tgt    = result.get("count_requested") or 0
        acc    = result.get("count_generated") or 0
        ttok   = result.get("total_tokens")
        has_r  = len(rej_by_test[tid]) > 0

        # Test-level context — denormalized onto every event row
        base = {
            "series_group":          run_id,
            "run_datetime":          run_datetime,
            "git_branch":            git_branch,
            "nr_global":             nr,
            "label":                 result.get("label") or None,
            "test_id":               tid,
            "topic":                 result.get("topic"),
            "difficulty":            result.get("difficulty"),
            "target_questions":      tgt,
            "accepted_questions":    acc,
            "missing_questions":     (tgt - acc) if tgt else None,
            "completion_pct":        _round(100 * acc / tgt, 1) if tgt else None,
            "status":                result.get("status"),
            "duration_seconds":      result.get("duration_seconds"),
            "n_batches":             result.get("n_batches"),
            "n_rejected_attempts":   result.get("n_rejected_attempts"),
            "min_batch_size":        result.get("min_batch_size"),
            "has_rejection":         has_r,
            "total_tokens_known":    (ttok is not None and ttok > 0) if ttok is not None else None,
            "tokens_per_target_q":   _round(ttok / tgt, 1) if (ttok and tgt) else None,
            "rejected_time_s_detailed": _round(rej_total_time[tid]) or None,
        }

        # ── Per-batch event stream (rejections → accepted, in batch_number order)
        batch_by_bn: dict[int, dict] = {
            b.get("batch_number"): b for b in batch_by_test[tid]
        }
        rej_by_bn: dict[int, list] = defaultdict(list)
        for r in rej_by_test[tid]:
            rej_by_bn[r.get("batch_number")].append(r)

        all_bns = sorted(set(list(batch_by_bn.keys()) + list(rej_by_bn.keys())))
        event_seq = 0

        for bn in all_bns:
            # Rejections first (sorted by attempt_number)
            for rej in sorted(rej_by_bn[bn], key=lambda x: x.get("attempt_number", 0)):
                event_seq += 1
                decision   = rej.get("decision")
                error_type = rej.get("error_type")
                dur        = rej.get("attempt_duration_seconds")
                bs         = rej.get("attempted_batch_size")
                pei        = rej.get("provider_error_info") or {}

                event_rows.append({
                    **base,
                    "event_type":             "rejected_attempt",
                    "event_type_pl":          _EVENT_TYPE_PL["rejected_attempt"],
                    "event_seq":              event_seq,
                    "batch_number":           bn,
                    "batch_duration_seconds": None,
                    "attempts_count":         None,
                    "rejected_attempts_count":None,
                    "accepted_questions_count":None,
                    "final_accepted_batch_size": None,
                    "accepted_attempt_batch_size": None,
                    "accepted_attempt_duration_seconds": None,
                    "gross_s_per_q":          None,
                    "clean_s_per_q":          None,
                    "rejection_overhead_s_total": None,
                    "rejection_overhead_s_per_q": None,
                    "rejection_overhead_pct": None,
                    "attempt_number":         rej.get("attempt_number"),
                    "attempted_batch_size":   bs,
                    "attempt_duration_seconds": dur,
                    "reject_reason":          decision,
                    "reject_reason_pl":       _DECISION_PL.get(decision),
                    "reject_family":          _reject_family(error_type),
                    "json_failure_kind":      None,
                    "json_failure_kind_pl":   None,
                    "provider_error_message_type": pei.get("message_type"),
                    "provider_http_status":   pei.get("http_status"),
                    "provider_error_code":    pei.get("error_code"),
                    "provider_error_type":    pei.get("error_type"),
                    "provider_error_message": pei.get("message"),
                    "provider_payload_present":         None,
                    "provider_failed_generation_present": None,
                    "provider_failed_generation_blank": None,
                    "token_usage_known":      None,
                    "output_tokens_wasted":   None,
                    "output_token_usage_pct": None,
                    "input_tokens_estimate":  None,
                    "input_tokens":           None,
                    "output_tokens":          None,
                    "reasoning_tokens":       None,
                    "total_tokens":           None,
                    "guardrail_question_count": rej.get("guardrail_question_count"),
                    "guardrail_chars":        rej.get("guardrail_chars"),
                    "total_prompt_chars":     rej.get("total_prompt_chars"),
                    "failed_generation_chars":None,
                    "event_duration_seconds": dur,
                    "event_batch_size":       bs,
                })

            # Then accepted batch
            if bn in batch_by_bn:
                event_seq += 1
                b      = batch_by_bn[bn]
                dur    = b.get("attempt_duration_seconds")
                bdur   = b.get("batch_duration_seconds")
                aq     = b.get("accepted_questions") or 0
                abs_   = b.get("accepted_batch_size")
                oh_dur = rej_overhead_dur.get((tid, bn), 0)
                oh_cnt = rej_overhead_cnt.get((tid, bn), 0)
                otok   = b.get("output_tokens")
                ttok_b = b.get("total_tokens")

                event_rows.append({
                    **base,
                    "event_type":             "accepted_batch",
                    "event_type_pl":          _EVENT_TYPE_PL["accepted_batch"],
                    "event_seq":              event_seq,
                    "batch_number":           bn,
                    "batch_duration_seconds": bdur,
                    "attempts_count":         b.get("total_attempts"),
                    "rejected_attempts_count":oh_cnt or None,
                    "accepted_questions_count": aq,
                    "final_accepted_batch_size": abs_,
                    "accepted_attempt_batch_size": abs_,
                    "accepted_attempt_duration_seconds": dur,
                    "gross_s_per_q":          _round(bdur / aq) if (bdur and aq) else None,
                    "clean_s_per_q":          _round(dur / aq) if (dur and aq) else None,
                    "rejection_overhead_s_total": _round(oh_dur) if oh_dur else None,
                    "rejection_overhead_s_per_q": _round(oh_dur / aq) if (oh_dur and aq) else None,
                    "rejection_overhead_pct": _round(100 * oh_dur / bdur, 1) if (oh_dur and bdur) else None,
                    "attempt_number":         None,
                    "attempted_batch_size":   None,
                    "attempt_duration_seconds": None,
                    "reject_reason":          None,
                    "reject_reason_pl":       None,
                    "reject_family":          None,
                    "json_failure_kind":      None,
                    "json_failure_kind_pl":   None,
                    "provider_error_message_type": None,
                    "provider_http_status":   None,
                    "provider_error_code":    None,
                    "provider_error_type":    None,
                    "provider_error_message": None,
                    "provider_payload_present":         None,
                    "provider_failed_generation_present": None,
                    "provider_failed_generation_blank": None,
                    "token_usage_known":      b.get("input_tokens") is not None,
                    "output_tokens_wasted":   None,
                    "output_token_usage_pct": _round(100 * otok / ttok_b, 1) if (otok and ttok_b) else None,
                    "input_tokens_estimate":  None,
                    "input_tokens":           b.get("input_tokens"),
                    "output_tokens":          otok,
                    "reasoning_tokens":       b.get("reasoning_tokens"),
                    "total_tokens":           ttok_b,
                    "guardrail_question_count": b.get("guardrail_question_count"),
                    "guardrail_chars":        b.get("guardrail_chars"),
                    "total_prompt_chars":     b.get("total_prompt_chars"),
                    "failed_generation_chars":None,
                    "event_duration_seconds": dur,
                    "event_batch_size":       abs_,
                })

        # Quality issues (after all batches)
        for issue in quality_by_test[tid]:
            event_seq += 1
            event_rows.append({
                **base,
                "event_type":    "quality_issue",
                "event_type_pl": _EVENT_TYPE_PL["quality_issue"],
                "event_seq":     event_seq,
                # all batch/rejection fields = None for quality events
                **{k: None for k in [
                    "batch_number", "batch_duration_seconds", "attempts_count",
                    "rejected_attempts_count", "accepted_questions_count",
                    "final_accepted_batch_size", "accepted_attempt_batch_size",
                    "accepted_attempt_duration_seconds", "gross_s_per_q", "clean_s_per_q",
                    "rejection_overhead_s_total", "rejection_overhead_s_per_q",
                    "rejection_overhead_pct", "attempt_number", "attempted_batch_size",
                    "attempt_duration_seconds", "reject_reason", "reject_reason_pl",
                    "reject_family", "json_failure_kind", "json_failure_kind_pl",
                    "provider_error_message_type", "provider_http_status",
                    "provider_error_code", "provider_error_type", "provider_error_message",
                    "provider_payload_present", "provider_failed_generation_present",
                    "provider_failed_generation_blank", "token_usage_known",
                    "output_tokens_wasted", "output_token_usage_pct", "input_tokens_estimate",
                    "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
                    "guardrail_question_count", "guardrail_chars", "total_prompt_chars",
                    "failed_generation_chars", "event_duration_seconds", "event_batch_size",
                ]},
            })

        # Generation error (when test failed with no events)
        if not result.get("ok") and result.get("error") and event_seq == 0:
            event_rows.append({
                **base,
                "event_type":    "generation_error",
                "event_type_pl": _EVENT_TYPE_PL["generation_error"],
                "event_seq":     1,
                **{k: None for k in [
                    "batch_number", "batch_duration_seconds", "attempts_count",
                    "rejected_attempts_count", "accepted_questions_count",
                    "final_accepted_batch_size", "accepted_attempt_batch_size",
                    "accepted_attempt_duration_seconds", "gross_s_per_q", "clean_s_per_q",
                    "rejection_overhead_s_total", "rejection_overhead_s_per_q",
                    "rejection_overhead_pct", "attempt_number", "attempted_batch_size",
                    "attempt_duration_seconds", "reject_reason", "reject_reason_pl",
                    "reject_family", "json_failure_kind", "json_failure_kind_pl",
                    "provider_error_message_type", "provider_http_status",
                    "provider_error_code", "provider_error_type", "provider_error_message",
                    "provider_payload_present", "provider_failed_generation_present",
                    "provider_failed_generation_blank", "token_usage_known",
                    "output_tokens_wasted", "output_token_usage_pct", "input_tokens_estimate",
                    "input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
                    "guardrail_question_count", "guardrail_chars", "total_prompt_chars",
                    "failed_generation_chars", "event_duration_seconds", "event_batch_size",
                ]},
            })

    return event_rows


def _enrich_results(
    results: list[dict],
    batch_rows: list[dict],
    rejection_rows: list[dict],
    quality_rows: list[dict],
) -> list[dict]:
    """Add per-test aggregated diagnostic fields to each result dict."""
    batch_by_test:  dict[str, list] = defaultdict(list)
    for b in batch_rows:
        batch_by_test[b.get("test_id", "")].append(b)

    rej_dur_by_test: dict[str, float] = defaultdict(float)
    for r in rejection_rows:
        dur = r.get("attempt_duration_seconds")
        if dur is not None:
            rej_dur_by_test[r.get("test_id", "")] += dur

    quality_cnt: dict[str, int] = defaultdict(int)
    for q in quality_rows:
        quality_cnt[q.get("test_id", "")] += 1

    enriched = []
    for r in results:
        tid     = r.get("test_id", "")
        batches = batch_by_test.get(tid, [])

        def _sum(key):
            vals = [b.get(key) for b in batches if b.get(key) is not None]
            return sum(vals) if vals else None

        copy = dict(r)
        copy["total_input_tokens"]         = _sum("input_tokens")
        copy["total_output_tokens"]        = _sum("output_tokens")
        copy["total_reasoning_tokens"]     = _sum("reasoning_tokens")
        copy["n_quality_issues"]           = quality_cnt.get(tid, 0)
        copy["total_rejection_duration_s"] = round(rej_dur_by_test.get(tid, 0.0), 3) or None
        enriched.append(copy)

    return enriched


# ── Main entry point ──────────────────────────────────────────────────────────

def build_excel(
    output_path: Path,
    results: list[dict],
    batch_rows: list[dict] | None = None,
    rejection_rows: list[dict] | None = None,
    quality_rows: list[dict] | None = None,
    run_id: str = "",
    run_datetime: str | None = None,
    git_branch: str | None = None,
) -> None:
    """Build analysis.xlsx with event warehouse table and derived view sheets."""
    batch_rows     = batch_rows     or []
    rejection_rows = rejection_rows or []
    quality_rows   = quality_rows   or []

    event_rows = _build_event_rows(
        results, batch_rows, rejection_rows, quality_rows,
        run_id=run_id, run_datetime=run_datetime, git_branch=git_branch,
    )
    enriched = _enrich_results(results, batch_rows, rejection_rows, quality_rows)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # Sheet order: fact table first, then derived views
    add_pivot_full_sheet(wb, event_rows)
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
