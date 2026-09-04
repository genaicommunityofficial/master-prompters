"""Admin-triggered evaluation pipeline with batching, retries, and live logs."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from app.db import db
from app.services import evaluation_service
from app.services.submission_service import job_payloads_for_responses

MAX_BATCH = 50
MAX_CONCURRENCY = 16
MAX_RETRIES = 5
LOG_CAP = 500
IN_CHUNK = 100

_lock = threading.Lock()
_logs: deque[dict[str, Any]] = deque(maxlen=LOG_CAP)
_seq = 0
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
    "llm_mode": None,
    "started_at": None,
    "finished_at": None,
    "error_message": None,
}


def clamp_eval_params(
    batch_size: int = 8,
    concurrency: int = 4,
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
                "llm_mode": None,
                "started_at": None,
                "finished_at": None,
                "error_message": None,
            }
        )
        _logs.clear()
        _seq = 0


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
    batch_size: int = 8,
    concurrency: int = 4,
    max_retries: int = 3,
    llm_mode: str | None = None,
) -> dict[str, Any]:
    batch_size, concurrency, max_retries = clamp_eval_params(
        batch_size=batch_size,
        concurrency=concurrency,
        max_retries=max_retries,
    )
    with _lock:
        if _state["status"] == "running":
            snapshot = dict(_state)
            snapshot["accepted"] = False
            return snapshot
        _state.update(
            {
                "status": "running",
                "accepted": True,
                "competition_id": competition_id,
                "batch_size": batch_size,
                "concurrency": concurrency,
                "max_retries": max_retries,
                "enqueued": 0,
                "processed": 0,
                "completed": 0,
                "failed": 0,
                "llm_mode": llm_mode,
                "started_at": time.time(),
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
        llm_mode=llm_mode,
    )
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


def _run_thread(
    *,
    competition_id: str,
    batch_size: int,
    concurrency: int,
    max_retries: int,
    llm_mode: str | None = None,
) -> None:
    evaluation_service.MAX_ATTEMPTS = max_retries
    try:
        _append_log(
            "info",
            f"Starting evaluation for {competition_id} (llm_mode={llm_mode or 'env'})",
            competition_id=competition_id,
            llm_mode=llm_mode,
        )
        enqueued = enqueue_pending_jobs(competition_id)
        _set(enqueued=enqueued)
        _append_log("info", f"Enqueued {enqueued} job(s)", enqueued=enqueued)
        if enqueued == 0:
            completed, failed = _job_counts(competition_id)
            _set(
                status="completed",
                finished_at=time.time(),
                processed=0,
                completed=completed,
                failed=failed,
            )
            _append_log("info", "No unevaluated responses to queue")
            return

        processed = 0
        idle_rounds = 0
        while True:
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
            _append_log(
                "info",
                f"Processing batch of {len(job_ids)} (serialized; concurrency={concurrency})",
                batch=len(job_ids),
            )
            # Shared Supabase HTTP client is not thread-safe on Windows.
            # Batch by question group; evaluate with the selected LLM mode.
            try:
                evaluation_service.process_queued_batch(
                    limit=len(job_ids), llm_mode=llm_mode, competition_id=competition_id
                )
            except Exception as exc:  # noqa: BLE001
                _append_log("error", f"Job worker error: {exc}")
            processed += len(job_ids)
            completed, failed = _job_counts(competition_id)
            _set(processed=processed, completed=completed, failed=failed)
            _append_log(
                "info",
                f"Progress: processed={processed} completed={completed} failed={failed}",
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
        _append_log("info", "Evaluation run finished")
    except Exception as exc:  # noqa: BLE001
        _append_log("error", str(exc)[:500])
        _set(status="failed", finished_at=time.time(), error_message=str(exc)[:400])
