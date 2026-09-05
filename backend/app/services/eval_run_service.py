"""Admin-triggered evaluation pipeline with batching, retries, and live logs."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from app.db import db
from app.services import evaluation_service
from app.services.submission_service import ensure_gemini_configured, job_payloads_for_responses

MAX_BATCH = 50
MAX_CONCURRENCY = 16
MAX_RETRIES = 5
LOG_CAP = 1000
IN_CHUNK = 100
TEST_COMPETITION_ID = "competition_test"

_lock = threading.Lock()
_halt = threading.Event()
_logs: deque[dict[str, Any]] = deque(maxlen=LOG_CAP)
_seq = 0
_BUSY = {"running", "pausing"}
_state: dict[str, Any] = {
    "status": "idle",
    "accepted": True,
    "competition_id": None,
    "batch_size": 0,
    "concurrency": 0,
    "max_retries": 3,
    "enqueued": 0,
    "processed": 0,
    "completed": 0,
    "failed": 0,
    "started_at": None,
    "finished_at": None,
    "error_message": None,
}


def clamp_eval_params(
    batch_size: int = 16,
    concurrency: int = 8,
    max_retries: int = 3,
) -> tuple[int, int, int]:
    batch = max(1, min(int(batch_size), MAX_BATCH))
    conc = max(1, min(int(concurrency), MAX_CONCURRENCY, batch))
    retries = max(1, min(int(max_retries), MAX_RETRIES))
    return batch, conc, retries


def reset_for_tests() -> None:
    global _seq
    with _lock:
        _state.update(
            {
                "status": "idle",
                "accepted": True,
                "competition_id": None,
                "batch_size": 0,
                "concurrency": 0,
                "max_retries": 3,
                "enqueued": 0,
                "processed": 0,
                "completed": 0,
                "failed": 0,
                "started_at": None,
                "finished_at": None,
                "error_message": None,
            }
        )
        _logs.clear()
        _seq = 0
        _halt.clear()


def get_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def get_logs(*, since: int = 0, limit: int = 200) -> dict[str, Any]:
    since = max(0, int(since))
    limit = max(1, min(int(limit), LOG_CAP))
    with _lock:
        entries = [e for e in _logs if int(e.get("seq") or 0) > since]
        snapshot = dict(_state)
    return {"logs": entries[-limit:], "run": snapshot}


def _append_log(level: str, message: str, **extra: Any) -> None:
    global _seq
    with _lock:
        _seq += 1
        entry = {
            "seq": _seq,
            "ts": time.time(),
            "level": level,
            "message": message,
            **extra,
        }
        _logs.append(entry)


def _set(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def _chunks(values: list[str], size: int = IN_CHUNK) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def reset_test_eval_results(competition_id: str) -> int:
    """Wipe scores for the test dataset and requeue every job.

    Does not delete prompts, responses, submissions, or participants.
    Live competitions are rejected.
    """
    if competition_id != TEST_COMPETITION_ID:
        raise ValueError("Eval reset is only allowed for the test competition")

    subs = (
        db()
        .table("pc_submissions")
        .select("id")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    sub_ids = [s["id"] for s in subs]
    if not sub_ids:
        return 0

    responses: list[dict] = []
    for chunk in _chunks(sub_ids):
        rows = (
            db()
            .table("pc_responses")
            .select("id")
            .in_("submission_id", chunk)
            .execute()
            .data
            or []
        )
        responses.extend(rows)
    response_ids = [r["id"] for r in responses]
    if not response_ids:
        return 0

    job_reset = {
        "status": "QUEUED",
        "attempt_count": 0,
        "last_error": None,
        "started_at": None,
        "completed_at": None,
        "locked_at": None,
    }
    for chunk in _chunks(response_ids):
        db().table("pc_evaluations").delete().in_("response_id", chunk).execute()
        db().table("pc_evaluation_jobs").update(job_reset).in_("response_id", chunk).execute()

    submission_reset = {
        "status": "SUBMITTED",
        "total_score": None,
        "rank": None,
        "completed_at": None,
    }
    for chunk in _chunks(sub_ids):
        db().table("pc_submissions").update(submission_reset).in_("id", chunk).execute()
    return len(response_ids)


def requeue_failed_jobs(competition_id: str) -> int:
    """Set FAILED jobs for this competition back to QUEUED so they can be scored again."""
    subs = (
        db()
        .table("pc_submissions")
        .select("id")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    sub_ids = [s["id"] for s in subs]
    if not sub_ids:
        return 0
    response_ids: list[str] = []
    for chunk in _chunks(sub_ids):
        rows = (
            db()
            .table("pc_responses")
            .select("id")
            .in_("submission_id", chunk)
            .execute()
            .data
            or []
        )
        response_ids.extend(r["id"] for r in rows)
    if not response_ids:
        return 0

    reset_payload = {
        "status": "QUEUED",
        "attempt_count": 0,
        "last_error": None,
        "started_at": None,
        "completed_at": None,
        "locked_at": None,
    }
    requeued = 0
    for chunk in _chunks(response_ids):
        rows = (
            db()
            .table("pc_evaluation_jobs")
            .select("id, status")
            .in_("response_id", chunk)
            .execute()
            .data
            or []
        )
        failed_ids = [r["id"] for r in rows if r.get("status") == "FAILED"]
        if not failed_ids:
            continue
        db().table("pc_evaluation_jobs").update(reset_payload).in_("id", failed_ids).execute()
        requeued += len(failed_ids)
    return requeued


def enqueue_pending_jobs(competition_id: str) -> int:
    """Create or requeue jobs for responses that do not yet have an evaluation."""
    subs = (
        db()
        .table("pc_submissions")
        .select("id")
        .eq("competition_id", competition_id)
        .in_("status", ["SUBMITTED", "PROCESSING"])
        .execute()
        .data
        or []
    )
    sub_ids = [s["id"] for s in subs]
    if not sub_ids:
        return 0

    responses: list[dict] = []
    for chunk in _chunks(sub_ids):
        rows = (
            db()
            .table("pc_responses")
            .select("id")
            .in_("submission_id", chunk)
            .execute()
            .data
            or []
        )
        responses.extend(rows)
    if not responses:
        return 0

    response_ids = [r["id"] for r in responses]
    evaluated: set[str] = set()
    jobs_by_response: dict[str, dict] = {}
    for chunk in _chunks(response_ids):
        ev_rows = (
            db()
            .table("pc_evaluations")
            .select("response_id")
            .in_("response_id", chunk)
            .execute()
            .data
            or []
        )
        evaluated.update(e["response_id"] for e in ev_rows)
        job_rows = (
            db()
            .table("pc_evaluation_jobs")
            .select("id, response_id, status")
            .in_("response_id", chunk)
            .execute()
            .data
            or []
        )
        for job in job_rows:
            jobs_by_response[job["response_id"]] = job

    to_insert: list[dict] = []
    requeue_ids: list[str] = []
    for row in responses:
        rid = row["id"]
        if rid in evaluated:
            continue
        existing = jobs_by_response.get(rid)
        if existing is None:
            to_insert.append(row)
        elif existing.get("status") in ("FAILED", "PROCESSING"):
            requeue_ids.append(existing["id"])

    created = 0
    if to_insert:
        payloads = job_payloads_for_responses(to_insert)
        for chunk in _chunks([p["response_id"] for p in payloads], 50):
            batch = [p for p in payloads if p["response_id"] in set(chunk)]
            db().table("pc_evaluation_jobs").insert(batch).execute()
            created += len(batch)

    for job_id in requeue_ids:
        (
            db()
            .table("pc_evaluation_jobs")
            .update({"status": "QUEUED", "last_error": None})
            .eq("id", job_id)
            .execute()
        )
    return created + len(requeue_ids)


def start(
    *,
    competition_id: str,
    batch_size: int = 16,
    concurrency: int = 8,
    max_retries: int = 3,
    mode: str = "restart",
) -> dict[str, Any]:
    global _seq
    ensure_gemini_configured()
    batch_size, concurrency, max_retries = clamp_eval_params(
        batch_size=batch_size,
        concurrency=concurrency,
        max_retries=max_retries,
    )
    if mode not in ("restart", "resume", "retry_failed"):
        mode = "restart"
    reset_scores = mode == "restart"
    requeue_failed = mode == "retry_failed"
    with _lock:
        if _state["status"] in _BUSY:
            snapshot = dict(_state)
            snapshot["accepted"] = False
            return snapshot
        if reset_scores:
            _logs.clear()
            _seq = 0
        _halt.clear()
        keep = mode in ("resume", "retry_failed")
        _state.update(
            {
                "status": "running",
                "accepted": True,
                "competition_id": competition_id,
                "batch_size": batch_size,
                "concurrency": concurrency,
                "max_retries": max_retries,
                "enqueued": _state["enqueued"] if keep else 0,
                "processed": _state["processed"] if keep else 0,
                "completed": _state["completed"] if keep else 0,
                "failed": _state["failed"] if keep else 0,
                "started_at": _state["started_at"] if keep and _state["started_at"] else time.time(),
                "finished_at": None,
                "error_message": None,
            }
        )
        snapshot = dict(_state)
    _spawn(
        competition_id=competition_id,
        batch_size=batch_size,
        concurrency=concurrency,
        max_retries=max_retries,
        reset_scores=reset_scores,
        requeue_failed=requeue_failed,
    )
    return snapshot


def pause() -> dict[str, Any]:
    """Finish the current Gemini batch, then stop so the run can be resumed."""
    with _lock:
        if _state["status"] != "running":
            snapshot = dict(_state)
            snapshot["accepted"] = False
            return snapshot
        _state["status"] = "pausing"
        snapshot = dict(_state)
        snapshot["accepted"] = True
    _halt.set()
    _append_log("info", "Pause requested. Finishing the current batch, then stopping.")
    return snapshot


def _spawn(**kwargs: Any) -> None:
    thread = threading.Thread(
        target=_run_thread,
        kwargs=kwargs,
        daemon=True,
        name="eval-run",
    )
    thread.start()


def _job_counts(competition_id: str) -> tuple[int, int]:
    subs = (
        db()
        .table("pc_submissions")
        .select("id")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    sub_ids = [s["id"] for s in subs]
    response_ids: list[str] = []
    for chunk in _chunks(sub_ids):
        rows = (
            db()
            .table("pc_responses")
            .select("id")
            .in_("submission_id", chunk)
            .execute()
            .data
            or []
        )
        response_ids.extend(r["id"] for r in rows)
    completed = 0
    failed = 0
    for chunk in _chunks(response_ids):
        rows = (
            db()
            .table("pc_evaluation_jobs")
            .select("status")
            .in_("response_id", chunk)
            .execute()
            .data
            or []
        )
        completed += sum(1 for r in rows if r.get("status") == "COMPLETED")
        failed += sum(1 for r in rows if r.get("status") == "FAILED")
    return completed, failed


def _queued_job_count(competition_id: str) -> int:
    subs = (
        db()
        .table("pc_submissions")
        .select("id")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    sub_ids = [s["id"] for s in subs]
    if not sub_ids:
        return 0
    response_ids: list[str] = []
    for chunk in _chunks(sub_ids):
        rows = (
            db()
            .table("pc_responses")
            .select("id")
            .in_("submission_id", chunk)
            .execute()
            .data
            or []
        )
        response_ids.extend(r["id"] for r in rows)
    queued = 0
    for chunk in _chunks(response_ids):
        rows = (
            db()
            .table("pc_evaluation_jobs")
            .select("id")
            .eq("status", "QUEUED")
            .in_("response_id", chunk)
            .execute()
            .data
            or []
        )
        queued += len(rows)
    return queued


def _prompt_label(event: dict[str, Any]) -> str:
    qnum = event.get("question_number")
    title = str(event.get("title") or "prompt").strip() or "prompt"
    if qnum is None:
        return title
    return f"Q{qnum} {title}"


def _run_thread(
    *,
    competition_id: str,
    batch_size: int,
    concurrency: int,
    max_retries: int,
    reset_scores: bool = True,
    requeue_failed: bool = False,
) -> None:
    evaluation_service.MAX_ATTEMPTS = max_retries
    try:
        if reset_scores and competition_id == TEST_COMPETITION_ID:
            _append_log(
                "info",
                "Clearing previous test scores so evaluation starts from the beginning",
                competition_id=competition_id,
            )
            cleared = reset_test_eval_results(competition_id)
            _append_log("info", f"Cleared scores for {cleared} prompt(s)")
        elif reset_scores:
            _append_log(
                "info",
                f"Starting evaluation for {competition_id} (Gemini). Already-scored prompts are skipped.",
                competition_id=competition_id,
            )
        elif requeue_failed:
            n = requeue_failed_jobs(competition_id)
            _append_log("info", f"Requeued {n} failed job(s) to score again")
        else:
            _append_log("info", "Resuming evaluation from where it left off")

        created = enqueue_pending_jobs(competition_id)
        total = _queued_job_count(competition_id)
        _set(enqueued=total)
        if created:
            _append_log("info", f"Queued {created} new job(s). {total} prompt(s) ready to score.")
        else:
            _append_log("info", f"{total} prompt(s) ready to score.")
        if total == 0:
            completed, failed = _job_counts(competition_id)
            _set(
                status="completed",
                finished_at=time.time(),
                processed=0,
                completed=completed,
                failed=failed,
            )
            _append_log("info", "Nothing left to score")
            return

        processed = 0
        idle_rounds = 0

        def on_progress(event: dict[str, Any]) -> None:
            nonlocal processed
            processed += 1
            label = _prompt_label(event)
            if event.get("ok"):
                score = event.get("score")
                try:
                    score_s = f"{float(score):.1f}"
                except (TypeError, ValueError):
                    score_s = "-"
                _append_log("info", f"{processed}/{total}  {label}  score {score_s}")
            else:
                err = str(event.get("error") or "failed")[:240]
                _append_log("error", f"{processed}/{total}  {label}  failed: {err}")
            _set(processed=processed)

        while True:
            if _halt.is_set():
                completed, failed = _job_counts(competition_id)
                _set(
                    status="paused",
                    finished_at=time.time(),
                    processed=processed,
                    completed=completed,
                    failed=failed,
                )
                _append_log(
                    "info",
                    f"Paused · {completed} complete · {failed} failed · {max(0, total - processed)} left this run. Resume to continue.",
                )
                _halt.clear()
                return
            job_ids = evaluation_service.get_queued_job_ids_for_competition(
                competition_id, limit=batch_size
            )
            if not job_ids:
                idle_rounds += 1
                if idle_rounds >= 2:
                    break
                time.sleep(0.15)
                continue
            idle_rounds = 0
            remaining = max(0, total - processed)
            _append_log(
                "info",
                f"Scoring {len(job_ids)} prompt(s) now ({concurrency} parallel Gemini calls, {remaining} remaining)",
                batch=len(job_ids),
                concurrency=concurrency,
            )
            # Gemini HTTP runs in a thread pool. Supabase writes stay on this
            # thread — the shared client is not safe for concurrent use on Windows.
            try:
                evaluation_service.process_queued_batch(
                    limit=len(job_ids),
                    competition_id=competition_id,
                    concurrency=concurrency,
                    on_progress=on_progress,
                )
            except Exception as exc:  # noqa: BLE001
                _append_log("error", f"Job worker error: {exc}")
            completed, failed = _job_counts(competition_id)
            _set(processed=processed, completed=completed, failed=failed)
            _append_log(
                "info",
                f"{processed}/{total} scored so far · {completed} complete · {failed} failed",
                processed=processed,
                completed=completed,
                failed=failed,
            )

        completed, failed = _job_counts(competition_id)
        _set(
            status="completed",
            finished_at=time.time(),
            processed=processed,
            completed=completed,
            failed=failed,
        )
        _append_log("info", f"Evaluation finished · {completed} scored · {failed} failed")
    except Exception as exc:  # noqa: BLE001
        _append_log("error", str(exc)[:500])
        _set(status="failed", finished_at=time.time(), error_message=str(exc)[:400])
