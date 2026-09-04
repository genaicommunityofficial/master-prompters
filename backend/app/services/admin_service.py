from __future__ import annotations

import statistics

from app.db import db


def _in_chunks(values: list[str], size: int = 100) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def get_dashboard(competition_id: str) -> dict:
    comp = (
        db()
        .table("pc_competitions")
        .select("status")
        .eq("id", competition_id)
        .limit(1)
        .execute()
    )
    comp_rows = comp.data or []
    comp_status = comp_rows[0].get("status") if comp_rows else None

    participants = (
        db()
        .table("pc_participants")
        .select("id, status")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    submissions = (
        db()
        .table("pc_submissions")
        .select("id, status, total_score")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )

    total_participants = len(participants)
    submitted = sum(1 for s in submissions if s["status"] not in ("DRAFT",))
    completed = sum(1 for s in submissions if s["status"] == "COMPLETED")
    failed = sum(1 for s in submissions if s["status"] == "FAILED")

    questions = (
        db()
        .table("pc_questions")
        .select("id, question_number, title")
        .eq("competition_id", competition_id)
        .order("question_number")
        .execute()
        .data
        or []
    )

    sub_ids = [s["id"] for s in submissions]
    responses: list[dict] = []
    for chunk in _in_chunks(sub_ids):
        rows = (
            db()
            .table("pc_responses")
            .select("id, question_id")
            .in_("submission_id", chunk)
            .execute()
            .data
            or []
        )
        responses.extend(rows)

    response_ids = [r["id"] for r in responses]
    evaluated_ids: set[str] = set()
    jobs: list[dict] = []
    for chunk in _in_chunks(response_ids):
        ev_rows = (
            db()
            .table("pc_evaluations")
            .select("response_id")
            .in_("response_id", chunk)
            .execute()
            .data
            or []
        )
        evaluated_ids.update(e["response_id"] for e in ev_rows)
        job_rows = (
            db()
            .table("pc_evaluation_jobs")
            .select("status, response_id")
            .in_("response_id", chunk)
            .execute()
            .data
            or []
        )
        jobs.extend(job_rows)

    total_prompts = len(responses)
    evaluated = len(evaluated_ids)
    queued = sum(1 for j in jobs if j["status"] == "QUEUED")
    retrying = sum(1 for j in jobs if j["status"] in ("RETRY", "PROCESSING"))
    evaluation_failed = sum(1 for j in jobs if j["status"] == "FAILED")
    awaiting_eval = max(0, total_prompts - evaluated)

    per_category: dict[str, dict] = {}
    stored_by_q: dict[str, int] = {}
    eval_by_q: dict[str, int] = {}
    for r in responses:
        qid = r.get("question_id")
        stored_by_q[qid] = stored_by_q.get(qid, 0) + 1
        if r["id"] in evaluated_ids:
            eval_by_q[qid] = eval_by_q.get(qid, 0) + 1
    for q in questions:
        qid = q["id"]
        per_category[qid] = {
            "question_number": q.get("question_number"),
            "title": q.get("title"),
            "stored": stored_by_q.get(qid, 0),
            "evaluated": eval_by_q.get(qid, 0),
        }

    scores = [float(s["total_score"]) for s in submissions if s.get("total_score") is not None]

    def median(lst):
        if not lst:
            return None
        return statistics.median(lst)

    return {
        "competition_id": competition_id,
        "competition_status": comp_status,
        "total_participants": total_participants,
        "submitted": submitted,
        "completed": completed,
        "failed": failed,
        "total_prompts": total_prompts,
        "evaluated": evaluated,
        "awaiting_eval": awaiting_eval,
        "queued": queued,
        "retrying": retrying,
        "evaluation_failed": evaluation_failed,
        "avg_score": round(statistics.mean(scores), 2) if scores else None,
        "median_score": round(median(scores), 2) if scores else None,
        "highest_score": round(max(scores), 2) if scores else None,
        "lowest_score": round(min(scores), 2) if scores else None,
        "per_category": per_category,
    }


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
    jobs = (
        db()
        .table("pc_evaluation_jobs")
        .select(
            "id, status, model, attempt_count, queued_at, last_error, "
            "pc_responses(id, prompt_text, question_id, pc_submissions(competition_id))"
        )
        .eq("pc_responses.pc_submissions.competition_id", competition_id)
        .order("queued_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    if status_filter:
        jobs = [j for j in jobs if j.get("status") == status_filter]
    return jobs