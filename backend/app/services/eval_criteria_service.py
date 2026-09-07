"""Per-category markdown evaluation criteria.

Admins paste one markdown rubric per category. The content is stored in
`pc_eval_criteria` and injected into the evaluator prompt. Locked rubrics
cannot be edited until they are unlocked.
"""

from __future__ import annotations

import hashlib

from app.db import db


class CriteriaError(Exception):
    pass


class CriteriaLockedError(CriteriaError):
    pass


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_criteria(criteria_map: dict[int, str], prompt: str, question: dict) -> str:
    """Return the effective evaluation text (prompt + rubric when present).

    criteria_map maps question_number -> markdown. If the question has no
    rubric, the prompt is returned unchanged.
    """
    qn = question.get("question_number")
    rubric = criteria_map.get(qn)
    if not rubric:
        return prompt
    return f"{rubric}\n\n---\n\nPrompt to evaluate:\n{prompt}"


def _current_version(question: dict) -> str:
    return str(question.get("evaluation_config") or {}).strip() or "file"


def get_criteria_for_competition(competition_id: str) -> dict[int, dict]:
    """Map question_number -> stored criteria row for a competition."""
    try:
        rows = (
            db()
            .table("pc_eval_criteria")
            .select(
                "competition_id, question_number, file_name, content_md, "
                "content_hash, updated_at, locked"
            )
            .eq("competition_id", competition_id)
            .execute()
            .data
            or []
        )
    except Exception:  # noqa: BLE001
        rows = (
            db()
            .table("pc_eval_criteria")
            .select(
                "competition_id, question_number, file_name, content_md, "
                "content_hash, updated_at"
            )
            .eq("competition_id", competition_id)
            .execute()
            .data
            or []
        )
    out: dict[int, dict] = {}
    for r in rows:
        row = dict(r)
        row["locked"] = bool(r.get("locked"))
        out[int(r["question_number"])] = row
    return out


def _upsert_criteria(store, *, competition_id: str, question_number: int,
                     file_name: str, content_md: str) -> dict:
    store.table("pc_eval_criteria").upsert(
        {
            "competition_id": competition_id,
            "question_number": question_number,
            "file_name": file_name,
            "content_md": content_md,
            "content_hash": content_hash(content_md),
            "updated_at": "now()",
        }
    ).execute()
    return {"question_number": question_number, "file_name": file_name,
            "content_md": content_md, "content_hash": content_hash(content_md)}


def upsert_criteria(*, competition_id: str, question_number: int,
                    file_name: str, content_md: str) -> dict:
    text = (content_md or "").strip()
    if not text:
        raise CriteriaError("Criteria text is empty.")
    current = get_criteria_for_competition(competition_id).get(question_number)
    if current and current.get("locked"):
        raise CriteriaLockedError("This rubric is locked. Unlock it before editing.")
    saved = _upsert_criteria(
        db(),
        competition_id=competition_id,
        question_number=question_number,
        file_name=file_name,
        content_md=text,
    )
    saved["locked"] = False
    return saved


def set_criteria_locked(competition_id: str, question_number: int, locked: bool) -> dict:
    current = get_criteria_for_competition(competition_id).get(question_number)
    if not current or not str(current.get("content_md") or "").strip():
        raise CriteriaError("Save criteria before locking.")
    try:
        updated = (
            db()
            .table("pc_eval_criteria")
            .update({"locked": locked, "updated_at": "now()"})
            .eq("competition_id", competition_id)
            .eq("question_number", question_number)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise CriteriaError(
            "Locking needs migration 0013 (pc_eval_criteria.locked). "
            "Run supabase/migrations/0013_criteria_lock_top50_leaderboard.sql."
        ) from exc
    if not updated.data:
        raise CriteriaError("Could not update criteria lock.")
    return {
        "question_number": question_number,
        "locked": locked,
        "content_hash": current.get("content_hash"),
    }


def get_criteria_map_for_eval(competition_id: str) -> dict[int, str]:
    """question_number -> markdown, for the evaluator."""
    return {
        qn: r["content_md"]
        for qn, r in get_criteria_for_competition(competition_id).items()
    }


def copy_criteria(source_competition_id: str, dest_competition_id: str) -> int:
    """Copy every rubric from one competition onto another. Returns rows written."""
    if source_competition_id == dest_competition_id:
        return 0
    source = get_criteria_for_competition(source_competition_id)
    written = 0
    store = db()
    for qn, row in source.items():
        dest = get_criteria_for_competition(dest_competition_id).get(qn)
        if dest and dest.get("locked"):
            continue
        _upsert_criteria(
            store,
            competition_id=dest_competition_id,
            question_number=qn,
            file_name=row.get("file_name") or "criteria.md",
            content_md=row.get("content_md") or "",
        )
        written += 1
    return written
