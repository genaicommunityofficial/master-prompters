from __future__ import annotations

from app.db import db, fetch_in
from app.services.eval_status_service import get_eval_progress


def dashboard_from_progress(progress: dict) -> dict:
    """Map eval-progress (source of truth) onto the dashboard metrics shape."""
    totals = progress["totals"]
    jobs = progress["jobs"]
    return {
        "competition_id": progress["competition_id"],
        "competition_status": progress["competition_status"],
        "total_participants": totals["participants"],
        "submitted": totals["submitted"],
        "completed": totals["completed"],
        "failed": totals["failed"],
        "total_prompts": totals["responses"],
        "evaluated": totals["evaluated"],
        "awaiting_eval": totals["pending"],
        "queued": jobs["QUEUED"],
        "retrying": jobs["PROCESSING"] + jobs["RETRY"],
        "evaluation_failed": jobs["FAILED"],
        "avg_score": totals.get("avg_score"),
        "median_score": totals.get("median_score"),
        "highest_score": totals.get("highest_score"),
        "lowest_score": totals.get("lowest_score"),
        "per_category": {
            qid: {
                "question_number": cat.get("question_number"),
                "title": cat.get("title"),
                "stored": cat.get("stored", 0),
                "evaluated": cat.get("evaluated", 0),
            }
            for qid, cat in (progress.get("per_category") or {}).items()
        },
    }


def get_dashboard(competition_id: str) -> dict:
    return dashboard_from_progress(get_eval_progress(competition_id))


def get_admin_submissions(competition_id: str) -> list[dict]:
    subs = (
        db()
        .table("pc_submissions")
        .select(
            "id, status, total_score, rank, submitted_at, "
            "pc_participants(id, display_name, email, qr_token)"
        )
        .eq("competition_id", competition_id)
        .order("submitted_at", desc=True)
        .execute()
        .data
        or []
    )
    return subs


def get_admin_evaluations(competition_id: str, status_filter: str | None = None, limit: int = 500) -> list[dict]:
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

    responses = fetch_in(
        "pc_responses", "id, prompt_text, question_id", "submission_id", sub_ids, order="id"
    )
    response_by_id = {r["id"]: r for r in responses}
    response_ids = list(response_by_id)
    if not response_ids:
        return []

    jobs = fetch_in(
        "pc_evaluation_jobs",
        "id, status, model, attempt_count, queued_at, last_error, response_id",
        "response_id",
        response_ids,
        order="queued_at",
        descending=True,
    )
    rows = []
    for j in jobs:
        row = dict(j)
        row["pc_responses"] = response_by_id.get(j.get("response_id")) or {}
        rows.append(row)
    rows.sort(key=lambda j: j.get("queued_at") or "", reverse=True)
    rows = rows[:limit]
    if status_filter:
        rows = [j for j in rows if j.get("status") == status_filter]
    return rows
