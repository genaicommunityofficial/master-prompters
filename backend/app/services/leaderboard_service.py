from __future__ import annotations

from app.db import db


def set_leaderboard_visible(competition_id: str, visible: bool) -> bool:
    """Set the leaderboard visibility flag on a competition."""
    result = (
        db()
        .table("pc_competitions")
        .update({"leaderboard_visible": visible})
        .eq("id", competition_id)
        .execute()
    )
    return bool(result.data)


def get_leaderboard(competition_id: str) -> dict:
    """Return the public leaderboard, or a hidden state if not published.

    Only COMPLETED submissions with a total_score are eligible. Only public
    fields (rank, display name, score) are returned. Emails/notes never leave.
    """
    comp = (
        db()
        .table("pc_competitions")
        .select("leaderboard_visible, status")
        .eq("id", competition_id)
        .limit(1)
        .execute()
    )
    comp_rows = comp.data or []
    if not comp_rows:
        return {"visible": False, "entries": []}

    visible = bool(comp_rows[0].get("leaderboard_visible"))
    if not visible:
        return {"visible": False, "entries": []}

    # Ranked submissions, joined with participant display names.
    subs = (
        db()
        .table("pc_submissions")
        .select("id, total_score, rank, participant_id")
        .eq("competition_id", competition_id)
        .eq("status", "COMPLETED")
        .not_.is_("total_score", "null")
        .order("total_score", desc=True)
        .execute()
    )
    subs_data = subs.data or []

    # Prefetch per-submission category scores so we don't hammer the DB per row.
    category_score_map = _category_scores_by_submission(subs_data)

    entries = []
    rank = 0
    prev_score = None
    for i, sub in enumerate(subs_data, start=1):
        score = float(sub["total_score"])
        if score != prev_score:
            rank = i
        prev_score = score

        participant = (
            db()
            .table("pc_participants")
            .select("display_name")
            .eq("id", sub["participant_id"])
            .limit(1)
            .execute()
        )
        name = "Participant"
        if participant.data:
            name = participant.data[0].get("display_name") or "Participant"

        category_scores = category_score_map.get(sub["id"], {})
        cat_values = [v for v in category_scores.values() if v is not None]
        average_score = (
            round(sum(cat_values) / len(cat_values), 2) if cat_values else None
        )
        entries.append(
            {
                "rank": rank,
                "display_name": name,
                "total_score": score,
                "category_scores": category_scores,
                "average_score": average_score,
            }
        )

    return {"visible": True, "entries": entries}


def _category_scores_by_submission(subs_data: list[dict]) -> dict[str, dict[int, float]]:
    """Map submission_id -> {question_number: score} for each COMPLETED submission.

    Each submission has up to 5 responses (one per question). We fetch the
    latest evaluation score for each response, keyed by its question number.
    """
    sub_ids = [s["id"] for s in subs_data]
    if not sub_ids:
        return {}

    result: dict[str, dict[int, float]] = {sid: {} for sid in sub_ids}

    # question_id -> question_number (from the competition's questions)
    qnum_by_qid: dict[str, int] = {}
    first_sub_id = sub_ids[0]
    comp = (
        db()
        .table("pc_submissions")
        .select("competition_id")
        .eq("id", first_sub_id)
        .limit(1)
        .execute()
    )
    comp_rows = comp.data or []
    if comp_rows:
        q_rows = (
            db()
            .table("pc_questions")
            .select("id, question_number")
            .eq("competition_id", comp_rows[0]["competition_id"])
            .execute()
            .data
            or []
        )
        qnum_by_qid = {q["id"]: int(q["question_number"]) for q in q_rows}

    # Fetch all responses for these submissions, chunked.
    responses_by_sub: dict[str, list[dict]] = {sid: [] for sid in sub_ids}
    for i in range(0, len(sub_ids), 50):
        chunk = sub_ids[i : i + 50]
        rows = (
            db()
            .table("pc_responses")
            .select("id, question_id, submission_id")
            .in_("submission_id", chunk)
            .execute()
            .data
            or []
        )
        for r in rows:
            responses_by_sub.setdefault(r["submission_id"], []).append(r)

    # Latest evaluation score per response.
    score_by_response: dict[str, float] = {}
    for group in responses_by_sub.values():
        resp_ids = [r["id"] for r in group]
        if not resp_ids:
            continue
        for i in range(0, len(resp_ids), 50):
            rchunk = resp_ids[i : i + 50]
            ev_rows = (
                db()
                .table("pc_evaluations")
                .select("response_id, score")
                .in_("response_id", rchunk)
                .execute()
                .data
                or []
            )
            for e in ev_rows:
                rid = e["response_id"]
                score = e.get("score")
                if score is not None:
                    score_by_response[rid] = float(score)

    for sid in sub_ids:
        for r in responses_by_sub.get(sid, []):
            qnum = qnum_by_qid.get(r["question_id"])
            score = score_by_response.get(r["id"])
            if qnum is not None and score is not None:
                result[sid][qnum] = round(score, 2)

    return result