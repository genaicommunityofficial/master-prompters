from __future__ import annotations

from app.db import db


def get_competition(competition_id: str) -> dict | None:
    res = (
        db()
        .table("pc_competitions")
        .select("*")
        .eq("id", competition_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def get_competition_by_slug(slug: str) -> dict | None:
    res = (
        db()
        .table("pc_competitions")
        .select("*")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def get_questions(competition_id: str) -> list[dict]:
    res = (
        db()
        .table("pc_questions")
        .select("*")
        .eq("competition_id", competition_id)
        .order("question_number")
        .execute()
    )
    return res.data or []


def set_status(competition_id: str, status: str) -> dict | None:
    """Transition a competition to the given status (admin)."""
    allowed = {"DRAFT", "OPEN", "CLOSED", "RESULTS_PUBLISHED", "ARCHIVED", "TEST"}
    if status not in allowed:
        raise ValueError(f"Invalid status: {status}")
    (
        db()
        .table("pc_competitions")
        .update({"status": status, "updated_at": "now()"})
        .eq("id", competition_id)
        .execute()
    )
    return get_competition(competition_id)


def _iso(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def to_public_competition(comp: dict) -> dict:
    """Prune internal fields for the participant-facing API."""
    now_open = comp.get("status") == "OPEN"
    return {
        "id": comp["id"],
        "name": comp.get("name") or "Competition",
        "slug": comp.get("slug") or comp["id"],
        "description": comp.get("description"),
        "status": comp.get("status"),
        "start_at": _iso(comp.get("start_at")),
        "end_at": _iso(comp.get("end_at")),
        "leaderboard_visible": bool(comp.get("leaderboard_visible")),
        "competition_status_open": now_open,
    }


def to_public_question(q: dict) -> dict:
    number = q.get("question_number") or 0
    return {
        "id": q["id"],
        "question_number": int(number),
        "title": q.get("title") or f"Question {number}",
        "description": q.get("description"),
        "max_length": int(q.get("max_length") or 500),
        "min_length": int(q.get("min_length") or 20),
    }