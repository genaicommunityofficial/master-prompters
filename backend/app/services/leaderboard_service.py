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
        entries.append(
            {
                "rank": rank,
                "display_name": name,
                "total_score": score,
            }
        )

    return {"visible": True, "entries": entries}