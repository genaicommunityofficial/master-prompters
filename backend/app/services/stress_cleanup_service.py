from __future__ import annotations

from app.config import settings
from app.db import db

TEST_COMPETITION_ID = "competition_test"


def cleanup_test_data() -> dict[str, int]:
    """Wipe all data created by the stress test against the TEST competition.

    Explicitly removes evaluation jobs and evaluations (which reference responses
    by FK but are not guaranteed to cascade once the response row is gone),
    then participants, questions, request logs and the TEST competition row.
    """
    competition_id = settings.stress_competition_id or TEST_COMPETITION_ID

    # 0. Evaluation jobs + evaluations for TEST submissions (before responses
    #    are removed, so any FK reference is gone cleanly).
    sub_ids = [
        r["id"]
        for r in (
            db()
            .table("pc_submissions")
            .select("id")
            .eq("competition_id", competition_id)
            .execute()
            .data
            or []
        )
    ]
    resp_ids: list[dict] = []
    for sid in sub_ids:
        resp_ids += (
            db().table("pc_responses").select("id").eq("submission_id", sid).execute().data or []
        )
    rid_list = [r["id"] for r in resp_ids]

    n_jobs = n_evals = 0
    for rid in rid_list:
        n_evals += len(
            db().table("pc_evaluations").delete().eq("response_id", rid).execute().data or []
        )
        n_jobs += len(
            db().table("pc_evaluation_jobs").delete().eq("response_id", rid).execute().data or []
        )

    # 1. Participants (cascades -> submissions -> responses).
    participants = (
        db()
        .table("pc_participants")
        .delete()
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    n_participants = len(participants)

    # 2. Request logs written by stress-test load (paths hitting the API).
    log_res = (
        db()
        .table("pc_request_logs")
        .delete()
        .like("path", "/api%")
        .execute()
        .data
        or []
    )
    n_logs = len(log_res)

    # 3. TEST competition questions + the TEST competition row, once refs are gone.
    q_res = db().table("pc_questions").delete().eq("competition_id", competition_id).execute().data or []
    n_questions = len(q_res)
    comp_res = (
        db()
        .table("pc_competitions")
        .delete()
        .eq("id", competition_id)
        .execute()
        .data
        or []
    )
    n_comps = len(comp_res)

    return {
        "deleted_participants": n_participants,
        "deleted_questions": n_questions,
        "deleted_competitions": n_comps,
        "deleted_logs": n_logs,
        "deleted_submissions": len(sub_ids),
        "deleted_responses": len(rid_list),
        "deleted_jobs": n_jobs,
        "deleted_evaluations": n_evals,
    }