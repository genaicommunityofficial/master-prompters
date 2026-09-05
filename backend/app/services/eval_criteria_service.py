"""Per-category markdown evaluation criteria.

Admin uploads one markdown rubric per category (question). The content is
stored in `pc_eval_criteria`. It is injected into the evaluator prompt for
that category so prompts are judged against the uploaded rubric.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.db import db


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
    rows = (
        db()
        .table("pc_eval_criteria")
        .select("competition_id, question_number, file_name, content_md, content_hash, updated_at")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    return {int(r["question_number"]): r for r in rows}


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
    return _upsert_criteria(db(), competition_id=competition_id,
                            question_number=question_number, file_name=file_name,
                            content_md=content_md)


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
        _upsert_criteria(
            store,
            competition_id=dest_competition_id,
            question_number=qn,
            file_name=row.get("file_name") or "criteria.md",
            content_md=row.get("content_md") or "",
        )
        written += 1
    return written