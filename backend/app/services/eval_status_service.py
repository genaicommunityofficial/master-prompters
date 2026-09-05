"""Optimized evaluation-progress + participation-funnel aggregation for admin.

Child tables (responses / evaluations / jobs) are scoped to a competition by
chunked ``in_`` lookups through submissions, avoiding PostgREST embedded-resource
filters (which are applied inconsistently when combined with ordering/pagination)
and staying well under the 1000-row per-request cap.
"""

from __future__ import annotations

import statistics
import time
from collections import Counter
from typing import Any

from app.db import db, fetch_in
from app.services import eval_run_service as run_svc
from app.services.eval_cost import summarize_cost

FAILED_SAMPLE_LIMIT = 20


def competition_eval_rows(competition_id: str) -> list[dict]:
    """Every evaluation row for a competition (submissions -> responses -> evals)."""
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
    responses = fetch_in("pc_responses", "id", "submission_id", sub_ids, order="id")
    response_ids = [r["id"] for r in responses]
    if not response_ids:
        return []
    return fetch_in(
        "pc_evaluations",
        "response_id, score, model, input_tokens, output_tokens, thinking_tokens, "
        "estimated_cost_usd, evaluation_version",
        "response_id",
        response_ids,
        order="id",
    )


class FunnelMigrationError(Exception):
    """Raised when the participation funnel needs migration 0003 to be applied."""


def _questions_by_id(competition_id: str) -> dict[str, dict]:
    rows = (
        db()
        .table("pc_questions")
        .select("id, question_number, title")
        .eq("competition_id", competition_id)
        .order("question_number")
        .execute()
        .data
        or []
    )
    return {q["id"]: q for q in rows}


def get_eval_progress(competition_id: str) -> dict[str, Any]:
    """Aggregate eval pipeline state for one competition in ~7 queries."""
    store = db()

    comp = (
        store.table("pc_competitions")
        .select("status, leaderboard_visible")
        .eq("id", competition_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    comp_status = comp[0].get("status") if comp else None
    leaderboard_visible = bool(comp[0].get("leaderboard_visible")) if comp else False

    participants = (
        store.table("pc_participants")
        .select("id", head=True, count="exact")
        .eq("competition_id", competition_id)
        .execute()
    )
    total_participants = participants.count if hasattr(participants, "count") and participants.count is not None else 0

    submissions = (
        store.table("pc_submissions")
        .select("id, status, total_score, participant_id")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )

    sub_ids = [s["id"] for s in submissions]
    responses: list[dict] = []
    if sub_ids:
        responses = fetch_in(
            "pc_responses", "id, question_id", "submission_id", sub_ids, order="id"
        )
    response_ids = [r["id"] for r in responses]

    jobs: list[dict] = []
    evals: list[dict] = []
    if response_ids:
        jobs = fetch_in(
            "pc_evaluation_jobs",
            "status, last_error, attempt_count, response_id, queued_at",
            "response_id",
            response_ids,
            order="queued_at",
            descending=True,
        )
        evals = fetch_in(
            "pc_evaluations",
            "response_id, score, model, input_tokens, output_tokens, thinking_tokens, "
            "estimated_cost_usd",
            "response_id",
            response_ids,
            order="id",
        )

    questions = _questions_by_id(competition_id)

    # --- Totals ------------------------------------------------------------
    submitted = sum(1 for s in submissions if s["status"] not in ("DRAFT",))
    completed_subs = sum(1 for s in submissions if s["status"] == "COMPLETED")
    failed_subs = sum(1 for s in submissions if s["status"] == "FAILED")
    responses_total = len(responses)
    evaluated_ids = {e["response_id"] for e in evals}
    evaluated = len(evaluated_ids)
    pending = max(0, responses_total - evaluated)
    progress_pct = round(evaluated / responses_total * 100, 1) if responses_total else 0.0

    # --- Job breakdown ------------------------------------------------------
    job_counts: dict[str, int] = Counter(j.get("status") or "UNKNOWN" for j in jobs)
    breakdown = {
        "QUEUED": job_counts.get("QUEUED", 0),
        "PROCESSING": job_counts.get("PROCESSING", 0),
        "RETRY": job_counts.get("RETRY", 0),
        "COMPLETED": job_counts.get("COMPLETED", 0),
        "FAILED": job_counts.get("FAILED", 0),
        "total": len(jobs),
    }

    # --- Failed jobs (recent sample + top error messages) -------------------
    failed_jobs = sorted(
        (j for j in jobs if j.get("status") == "FAILED"),
        key=lambda j: j.get("queued_at") or "",
        reverse=True,
    )
    failed_sample: list[dict[str, Any]] = []
    for j in failed_jobs[:FAILED_SAMPLE_LIMIT]:
        failed_sample.append(
            {
                "response_id": j.get("response_id"),
                "attempt_count": j.get("attempt_count"),
                "error": (j.get("last_error") or "")[:400],
                "question_number": _question_number_for_response(
                    j.get("response_id"), responses, questions
                ),
            }
        )
    error_buckets = Counter((j.get("last_error") or "unknown error")[:120] for j in failed_jobs)
    top_errors = [
        {"message": message, "count": count}
        for message, count in error_buckets.most_common(5)
    ]

    # --- Per-category progress ----------------------------------------------
    response_q = {r["id"]: r.get("question_id") for r in responses}
    per_category: dict[str, dict[str, Any]] = {}
    for q in questions.values():
        qid = q["id"]
        q_scores = [
            float(e["score"])
            for e in evals
            if response_q.get(e["response_id"]) == qid and e.get("score") is not None
        ]
        q_stored = sum(1 for r in responses if r.get("question_id") == qid)
        q_evaluated = sum(
            1 for r in responses if r.get("question_id") == qid and r["id"] in evaluated_ids
        )
        per_category[qid] = {
            "question_number": q.get("question_number"),
            "title": q.get("title"),
            "stored": q_stored,
            "evaluated": q_evaluated,
            "progress_pct": round(q_evaluated / q_stored * 100, 1) if q_stored else 0.0,
            "avg_score": round(statistics.mean(q_scores), 2) if q_scores else None,
            "min_score": round(min(q_scores), 2) if q_scores else None,
            "max_score": round(max(q_scores), 2) if q_scores else None,
        }

    # --- Cost (derived live from tokens x lookup prices) --------------------
    cost = summarize_cost(evals)

    # --- Active run snapshot (rate + ETA when running this competition) -----
    run = run_svc.get_status()
    run_info: dict[str, Any] | None = None
    if run.get("competition_id") == competition_id and run.get("status") in ("running", "completed", "failed"):
        run_info = {
            "status": run.get("status"),
            "accepted": run.get("accepted"),
            "enqueued": run.get("enqueued"),
            "processed": run.get("processed"),
            "completed": run.get("completed"),
            "failed": run.get("failed"),
            "started_at": run.get("started_at"),
            "finished_at": run.get("finished_at"),
            "error_message": run.get("error_message"),
            "elapsed_seconds": _elapsed(run),
            "rate_per_second": _rate(run),
            "eta_seconds": _eta(run, pending),
        }

    scores = [
        float(s["total_score"]) for s in submissions if s.get("total_score") is not None
    ]

    return {
        "competition_id": competition_id,
        "competition_status": comp_status,
        "leaderboard_visible": leaderboard_visible,
        "totals": {
            "participants": total_participants,
            "submissions": len(submissions),
            "submitted": submitted,
            "completed": completed_subs,
            "failed": failed_subs,
            "job_failed": breakdown["FAILED"],
            "responses": responses_total,
            "evaluated": evaluated,
            "pending": pending,
            "progress_pct": progress_pct,
            "avg_score": round(statistics.mean(scores), 2) if scores else None,
            "median_score": round(statistics.median(scores), 2) if scores else None,
            "highest_score": round(max(scores), 2) if scores else None,
            "lowest_score": round(min(scores), 2) if scores else None,
        },
        "jobs": breakdown,
        "failed_sample": failed_sample,
        "top_errors": top_errors,
        "per_category": per_category,
        "cost": cost,
        "run": run_info,
    }


def _question_number_for_response(
    response_id: Any, responses: list[dict], questions: dict[str, dict]
) -> Any:
    for r in responses:
        if r["id"] == response_id:
            q = questions.get(r.get("question_id"))
            return q.get("question_number") if q else None
    return None


def _elapsed(run: dict[str, Any]) -> float | None:
    started = run.get("started_at")
    if not started:
        return None
    return max(0.0, (run.get("finished_at") or time.time()) - started)


def _rate(run: dict[str, Any]) -> float | None:
    elapsed = _elapsed(run)
    completed = run.get("completed") or 0
    if not elapsed or elapsed <= 0:
        return None
    return round(completed / elapsed, 3)


def _eta(run: dict[str, Any], pending: int) -> float | None:
    rate = _rate(run)
    if run.get("status") != "running" or not rate or rate <= 0 or pending <= 0:
        return None
    return round(pending / rate, 0)


def get_participation_funnel(competition_id: str) -> dict[str, Any]:
    """Registered -> logged in -> submitted funnel for a competition.

    Requires migration 0003 (login_count / last_login_at). If the columns are
    missing, raises FunnelMigrationError so the API can guide the admin.
    """
    store = db()
    try:
        participants = (
            store.table("pc_participants")
            .select(
                "id, status, registration_id, registration_number, qr_token, "
                "display_name, email, login_count, last_login_at"
            )
            .eq("competition_id", competition_id)
            .execute()
            .data
            or []
        )
    except Exception as exc:  # noqa: BLE001
        raise FunnelMigrationError(
            "Participation funnel needs migration 0003 (login_count / last_login_at) "
            "applied to the database. Run supabase/migrations/0003_participant_login_tracking.sql "
            f"in the Supabase SQL editor. ({exc})"
        ) from exc

    submissions = (
        store.table("pc_submissions")
        .select("id, participant_id, status, total_score")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )

    sub_by_participant: dict[str, dict] = {}
    for s in submissions:
        sub_by_participant.setdefault(s["participant_id"], s)

    registered = len(participants)
    logged_in = sum(
        1 for p in participants if int(p.get("login_count") or 0) > 0
    )
    submitted = sum(1 for p in participants if p["id"] in sub_by_participant)
    with_registration_number = sum(
        1 for p in participants if p.get("registration_number")
    )
    completed = sum(
        1
        for s in submissions
        if s.get("status") == "COMPLETED" and s.get("total_score") is not None
    )
    logged_in_not_submitted = sum(
        1
        for p in participants
        if int(p.get("login_count") or 0) > 0 and p["id"] not in sub_by_participant
    )

    def pct(part: int, whole: int) -> float | None:
        return round(part / whole * 100, 1) if whole else None

    rows: list[dict[str, Any]] = []
    for p in participants:
        sub = sub_by_participant.get(p["id"])
        rows.append(
            {
                "participant_id": p["id"],
                "display_name": p.get("display_name"),
                "email": p.get("email"),
                "registration_number": p.get("registration_number"),
                "status": p.get("status"),
                "login_count": int(p.get("login_count") or 0),
                "last_login_at": p.get("last_login_at"),
                "submitted": sub is not None,
                "submission_status": (sub.get("status") if sub else None),
                "total_score": (sub.get("total_score") if sub else None),
            }
        )

    return {
        "competition_id": competition_id,
        "registered": registered,
        "logged_in": logged_in,
        "logged_in_not_submitted": logged_in_not_submitted,
        "submitted": submitted,
        "completed": completed,
        "funnel": {
            "registered": registered,
            "logged_in": {
                "count": logged_in,
                "pct_of_registered": pct(logged_in, registered),
            },
            "submitted": {
                "count": submitted,
                "pct_of_logged_in": pct(submitted, logged_in) if logged_in else None,
            },
            "completed": {
                "count": completed,
                "pct_of_submitted": pct(completed, submitted) if submitted else None,
            },
        },
        "sources": {
            "with_registration_number": with_registration_number,
            "qr_only": registered - with_registration_number,
        },
        "participants": rows,
    }