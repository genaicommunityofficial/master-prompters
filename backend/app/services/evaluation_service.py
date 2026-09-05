from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from app.db import db
from app.services import submission_service

MAX_ATTEMPTS = 3


def _claim_job(job_id: str) -> dict | None:
    """Atomically claim a QUEUED job for processing."""
    current = (
        db()
        .table("pc_evaluation_jobs")
        .select("id, response_id, attempt_count, status")
        .eq("id", job_id)
        .eq("status", "QUEUED")
        .limit(1)
        .execute()
    )
    rows = current.data or []
    if not rows:
        return None
    attempt = int(rows[0].get("attempt_count") or 0)
    res = (
        db()
        .table("pc_evaluation_jobs")
        .update(
            {
                "status": "PROCESSING",
                "started_at": "now()",
                "locked_at": "now()",
                "attempt_count": attempt + 1,
            }
        )
        .eq("id", job_id)
        .eq("status", "QUEUED")
        .execute()
    )
    return res.data[0] if res.data else None


def _claim_jobs(job_ids: list[str]) -> list[dict]:
    """Claim a batch of QUEUED jobs with one update per attempt_count group."""
    if not job_ids:
        return []
    current = (
        db()
        .table("pc_evaluation_jobs")
        .select("id, response_id, attempt_count, status")
        .in_("id", job_ids)
        .eq("status", "QUEUED")
        .execute()
    )
    rows = current.data or []
    if not rows:
        return []
    by_attempt: dict[int, list[str]] = defaultdict(list)
    by_id = {row["id"]: row for row in rows}
    for row in rows:
        by_attempt[int(row.get("attempt_count") or 0)].append(row["id"])
    claimed: list[dict] = []
    for attempt, ids in by_attempt.items():
        res = (
            db()
            .table("pc_evaluation_jobs")
            .update(
                {
                    "status": "PROCESSING",
                    "started_at": "now()",
                    "locked_at": "now()",
                    "attempt_count": attempt + 1,
                }
            )
            .in_("id", ids)
            .eq("status", "QUEUED")
            .execute()
        )
        if res.data:
            claimed.extend(res.data)
            continue
        for job_id in ids:
            row = by_id[job_id]
            claimed.append(
                {
                    **row,
                    "status": "PROCESSING",
                    "attempt_count": attempt + 1,
                }
            )
    return claimed


def get_queued_job_ids(limit: int = 10) -> list[str]:
    res = (
        db()
        .table("pc_evaluation_jobs")
        .select("id")
        .eq("status", "QUEUED")
        .order("queued_at")
        .limit(limit)
        .execute()
    )
    return [row["id"] for row in (res.data or [])]


def get_queued_job_ids_for_competition(competition_id: str, limit: int = 10) -> list[str]:
    """QUEUED jobs whose responses belong to submissions in this competition."""
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
        return []
    response_ids: list[str] = []
    for i in range(0, len(sub_ids), 100):
        chunk = sub_ids[i : i + 100]
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
        return []
    ids: list[str] = []
    remaining = limit
    for i in range(0, len(response_ids), 100):
        if remaining <= 0:
            break
        chunk = response_ids[i : i + 100]
        rows = (
            db()
            .table("pc_evaluation_jobs")
            .select("id")
            .eq("status", "QUEUED")
            .in_("response_id", chunk)
            .order("queued_at")
            .limit(remaining)
            .execute()
            .data
            or []
        )
        ids.extend(r["id"] for r in rows)
        remaining = limit - len(ids)
    return ids[:limit]


def process_job(job_id: str) -> None:
    """Evaluate a single queued job end-to-end (worker body)."""
    job = _claim_job(job_id)
    if not job:
        return

    try:
        _process_claimed_job(job_id, job)
    except Exception as exc:  # noqa: BLE001
        _fail_or_retry(job_id, str(exc), int(job.get("attempt_count") or 1))


def _process_claimed_job(job_id: str, job: dict) -> None:
    response = (
        db()
        .table("pc_responses")
        .select("*")
        .eq("id", job["response_id"])
        .limit(1)
        .execute()
    )
    resp_rows = response.data or []
    if not resp_rows:
        _fail_or_retry(job_id, "response not found", int(job.get("attempt_count") or 1))
        return
    response = resp_rows[0]

    question = (
        db()
        .table("pc_questions")
        .select("*")
        .eq("id", response["question_id"])
        .limit(1)
        .execute()
    )
    q_rows = question.data or []
    question = q_rows[0] if q_rows else {}
    evaluation_version = _current_evaluation_version(response["id"])
    criteria_md = _criteria_for_response(response, question)

    try:
        result = submission_service.run_evaluator(
            response["prompt_text"], question, {}, criteria_md=criteria_md
        )
    except Exception as exc:  # noqa: BLE001
        _fail_or_retry(job_id, str(exc), int(job.get("attempt_count") or 1))
        return

    existing = (
        db()
        .table("pc_evaluations")
        .select("id")
        .eq("response_id", response["id"])
        .eq("evaluation_version", evaluation_version)
        .limit(1)
        .execute()
    )
    existing_rows = existing.data or []
    if existing_rows:
        _complete_job(job_id)
        _maybe_finalize_submission(response["submission_id"])
        return

    (
        db()
        .table("pc_evaluations")
        .insert(
            {
                "response_id": response["id"],
                "evaluation_job_id": job_id,
                "score": result.get("score", 0),
                "criteria_scores": result.get("criteria_scores"),
                "reasoning_summary": result.get("summary"),
                "model": result.get("model"),
                "input_tokens": result.get("input_tokens"),
                "output_tokens": result.get("output_tokens"),
                "thinking_tokens": result.get("thinking_tokens"),
                "latency_ms": result.get("latency_ms"),
                "estimated_cost_usd": result.get("estimated_cost_usd"),
                "evaluation_version": evaluation_version,
            }
        )
        .execute()
    )

    _complete_job(job_id)
    _maybe_finalize_submission(response["submission_id"])


def _complete_job(job_id: str) -> None:
    (
        db()
        .table("pc_evaluation_jobs")
        .update({"status": "COMPLETED", "completed_at": "now()"})
        .eq("id", job_id)
        .execute()
    )


def _fail_job(job_id: str, error: str) -> None:
    (
        db()
        .table("pc_evaluation_jobs")
        .update(
            {
                "status": "FAILED",
                "last_error": error[:1000],
                "completed_at": "now()",
            }
        )
        .eq("id", job_id)
        .execute()
    )


def _is_permanent_failure(error: str) -> bool:
    msg = (error or "").lower()
    return (
        "no longer available" in msg
        or ("404" in msg and "model" in msg)
        or "additionalproperties" in msg
        or "not in gemini developer api" in msg
    )


def _fail_or_retry(job_id: str, error: str, attempt_count: int) -> bool:
    """Requeue or fail a job. Returns True when the job is now FAILED."""
    if _is_permanent_failure(error):
        _fail_job(job_id, error)
        return True
    if attempt_count < MAX_ATTEMPTS:
        (
            db()
            .table("pc_evaluation_jobs")
            .update(
                {
                    "status": "QUEUED",
                    "last_error": error[:1000],
                }
            )
            .eq("id", job_id)
            .execute()
        )
        return False
    _fail_job(job_id, error)
    return True


def _criteria_for_response(response: dict, question: dict) -> str | None:
    """Load the uploaded markdown rubric for this response's category."""
    try:
        from app.services import eval_criteria_service as crit

        sub = (
            db()
            .table("pc_responses")
            .select("submission_id")
            .eq("id", response["id"])
            .limit(1)
            .execute()
        )
        sub_rows = sub.data or []
        if not sub_rows:
            return None
        inv = (
            db()
            .table("pc_submissions")
            .select("competition_id")
            .eq("id", sub_rows[0]["submission_id"])
            .limit(1)
            .execute()
        )
        comp_rows = inv.data or []
        if not comp_rows:
            return None
        competition_id = comp_rows[0].get("competition_id")
        qnum = question.get("question_number")
        return crit.get_criteria_map_for_eval(competition_id).get(qnum)
    except Exception:  # noqa: BLE001
        return None


def evaluation_version_for_competition(competition_id: str | None) -> str:
    """One lookup of pc_competitions.evaluation_version for a whole batch."""
    if not competition_id:
        return "v0.0.0"
    comp = (
        db()
        .table("pc_competitions")
        .select("evaluation_version")
        .eq("id", competition_id)
        .limit(1)
        .execute()
    )
    comp_rows = comp.data or []
    return (comp_rows[0].get("evaluation_version") if comp_rows else None) or "v0.0.0"


def _current_evaluation_version(response_id: str) -> str:
    sub = (
        db()
        .table("pc_responses")
        .select("submission_id")
        .eq("id", response_id)
        .limit(1)
        .execute()
    )
    sub_rows = sub.data or []
    if not sub_rows:
        return "v0.0.0"
    submission = (
        db()
        .table("pc_submissions")
        .select("competition_id")
        .eq("id", sub_rows[0]["submission_id"])
        .limit(1)
        .execute()
    )
    sub_rows = submission.data or []
    if not sub_rows:
        return "v0.0.0"
    return evaluation_version_for_competition(sub_rows[0].get("competition_id"))


def _maybe_finalize_submission(submission_id: str, *, recompute_ranks: bool = True) -> None:
    """Once all 5 responses for a submission are evaluated, aggregate the score,
    mark COMPLETED and optionally publish rank."""
    sub = (
        db()
        .table("pc_submissions")
        .select("id, competition_id")
        .eq("id", submission_id)
        .limit(1)
        .execute()
    )
    sub_rows = sub.data or []
    if not sub_rows:
        return
    sub = sub_rows[0]

    responses = (
        db()
        .table("pc_responses")
        .select("id")
        .eq("submission_id", submission_id)
        .execute()
        .data
        or []
    )

    scores = []
    for r in responses:
        ev = (
            db()
            .table("pc_evaluations")
            .select("score")
            .eq("response_id", r["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        ev_rows = ev.data or []
        if not ev_rows:
            return  # not all evaluated yet
        scores.append(float(ev_rows[0]["score"]))

    if len(scores) != 5:
        return

    total = round(sum(scores), 2)
    (
        db()
        .table("pc_submissions")
        .update(
            {
                "status": "COMPLETED",
                "completed_at": "now()",
                "total_score": total,
            }
        )
        .eq("id", submission_id)
        .execute()
    )
    if recompute_ranks:
        _recompute_ranks(sub["competition_id"])


def _recompute_ranks(competition_id: str) -> None:
    subs = (
        db()
        .table("pc_submissions")
        .select("id, total_score")
        .eq("competition_id", competition_id)
        .eq("status", "COMPLETED")
        .not_.is_("total_score", "null")
        .order("total_score", desc=True)
        .execute()
        .data
        or []
    )
    rank = 0
    prev_score = None
    for i, sub in enumerate(subs, start=1):
        score = float(sub["total_score"])
        if score != prev_score:
            rank = i
        (
            db()
            .table("pc_submissions")
            .update({"rank": rank})
            .eq("id", sub["id"])
            .execute()
        )
        prev_score = score


def process_queued_batch(
    limit: int = 10,
    competition_id: str | None = None,
    concurrency: int = 8,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> int:
    """Claim up to *limit* QUEUED jobs and score them with parallel Gemini calls.

    Each prompt is one API request (independent rubric judgment). Several
    requests run at once. Supabase writes stay on this thread and run as
    each Gemini call finishes. Ranks are recomputed once per batch.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if competition_id:
        jobs = get_queued_job_ids_for_competition(competition_id, limit)
    else:
        jobs = get_queued_job_ids(limit)
    if not jobs:
        return 0

    claimed = _claim_jobs(jobs)
    if not claimed:
        return 0

    response_ids = [r["response_id"] for r in claimed]
    resp_rows = (
        db()
        .table("pc_responses")
        .select("id, question_id, submission_id, prompt_text")
        .in_("id", response_ids)
        .execute()
        .data
        or []
    )
    resp_map = {r["id"]: r for r in resp_rows}

    groups: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for row in claimed:
        resp = resp_map.get(row["response_id"])
        if not resp:
            continue
        qid = resp.get("question_id", "unknown")
        groups[qid].append((row, resp))

    work: list[tuple[dict, dict, dict, str | None]] = []
    for question_id, group in groups.items():
        work.extend(_prepare_group(question_id, group))

    if not work:
        return 0

    if not competition_id:
        competition_id = _competition_id_for_response(work[0][1])
    eval_version = evaluation_version_for_competition(competition_id)

    workers = max(1, min(int(concurrency), len(work)))
    saved = 0

    def _score(item: tuple[dict, dict, dict, str | None]) -> dict:
        _job, resp, question, criteria_md = item
        return submission_service.run_evaluator(
            resp["prompt_text"],
            question,
            {},
            criteria_md=criteria_md,
        )

    def _progress(question: dict, **event: Any) -> None:
        if not on_progress:
            return
        title = str(question.get("title") or "").strip() or f"Q{question.get('question_number', '?')}"
        on_progress(
            {
                "title": title,
                "question_number": question.get("question_number"),
                **event,
            }
        )

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gemini-eval") as pool:
        futures = {pool.submit(_score, item): item for item in work}
        for fut in as_completed(futures):
            job_row, resp, question, _crit = futures[fut]
            try:
                result = fut.result()
                error = None
            except Exception as exc:  # noqa: BLE001
                result = None
                error = str(exc)
            if error or result is None:
                terminal = _fail_or_retry(
                    job_row["id"],
                    error or "evaluation failed",
                    int(job_row.get("attempt_count") or 1),
                )
                _progress(
                    question,
                    ok=False,
                    terminal=terminal,
                    error=(error or "evaluation failed")[:240],
                )
                continue
            _save_evaluation(
                job_row,
                resp,
                result,
                evaluation_version=eval_version,
                recompute_ranks=False,
            )
            saved += 1
            _progress(
                question,
                ok=True,
                score=result.get("score"),
                latency_ms=result.get("latency_ms"),
                input_tokens=result.get("input_tokens"),
                thinking_tokens=result.get("thinking_tokens"),
                estimated_cost_usd=result.get("estimated_cost_usd"),
            )

    if saved and competition_id:
        _recompute_ranks(competition_id)
    return saved


def _prepare_group(
    question_id: str,
    group: list[tuple[dict, dict]],
) -> list[tuple[dict, dict, dict, str | None]]:
    """Attach question + rubric to already-claimed jobs. No LLM calls."""
    from app.services import eval_criteria_service as crit

    q_rows = (
        db()
        .table("pc_questions")
        .select("*")
        .eq("id", question_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    question = q_rows[0] if q_rows else {}
    first_resp = group[0][1]
    comp_id = _competition_id_for_response(first_resp)
    criteria_map = crit.get_criteria_map_for_eval(comp_id) if comp_id else {}
    qnum = question.get("question_number")
    criteria_md = criteria_map.get(qnum) if qnum else None
    return [(job_row, resp, question, criteria_md) for job_row, resp in group]


def _save_evaluation(
    job_row: dict,
    resp: dict,
    result: dict,
    *,
    evaluation_version: str | None = None,
    recompute_ranks: bool = True,
) -> None:
    """Insert the evaluation row, complete the job, maybe finalize submission."""
    version = evaluation_version or _current_evaluation_version(resp["id"])

    existing = (
        db()
        .table("pc_evaluations")
        .select("id")
        .eq("response_id", resp["id"])
        .eq("evaluation_version", version)
        .limit(1)
        .execute()
    )
    if existing.data:
        _complete_job(job_row["id"])
        _maybe_finalize_submission(resp["submission_id"], recompute_ranks=recompute_ranks)
        return

    (
        db()
        .table("pc_evaluations")
        .insert(
            {
                "response_id": resp["id"],
                "evaluation_job_id": job_row["id"],
                "score": result.get("score", 0),
                "criteria_scores": result.get("criteria_scores"),
                "reasoning_summary": result.get("summary"),
                "model": result.get("model"),
                "input_tokens": result.get("input_tokens"),
                "output_tokens": result.get("output_tokens"),
                "thinking_tokens": result.get("thinking_tokens"),
                "latency_ms": result.get("latency_ms"),
                "estimated_cost_usd": result.get("estimated_cost_usd"),
                "evaluation_version": version,
            }
        )
        .execute()
    )

    _complete_job(job_row["id"])
    _maybe_finalize_submission(resp["submission_id"], recompute_ranks=recompute_ranks)


def _competition_id_for_response(resp: dict) -> str | None:
    """Walk response → submission → competition to get the competition_id."""
    sub_rows = (
        db()
        .table("pc_submissions")
        .select("competition_id")
        .eq("id", resp.get("submission_id", ""))
        .limit(1)
        .execute()
        .data
        or []
    )
    return sub_rows[0]["competition_id"] if sub_rows else None