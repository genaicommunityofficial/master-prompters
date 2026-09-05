from __future__ import annotations

import csv
import io
from typing import Any

from app.db import db

# Categories 1-5 in display order (matches pc_questions for the real competition).
CATEGORY_TITLES = {
    1: "Meme Generation",
    2: "AI Visual Art Creation",
    3: "AI Digital Storytelling / Creative Writing",
    4: "AI Song Factory",
    5: "AI-Generated Poetry in Local Languages",
}


def get_evaluation_cost_summary(competition_id: str) -> dict[str, Any]:
    """Return token/USD cost aggregates, scoped to the given competition.

    Cost is derived per evaluation from the model's lookup price when the
    stored ``estimated_cost_usd`` is null, so totals are accurate for old rows
    and grow live with evaluation progress.
    """
    from app.services.eval_cost import summarize_cost
    from app.services.eval_status_service import competition_eval_rows

    evals = competition_eval_rows(competition_id)
    return summarize_cost(evals)


def get_analytics(competition_id: str) -> dict[str, Any]:
    from app.services.admin_service import dashboard_from_progress
    from app.services.eval_status_service import get_eval_progress

    progress = get_eval_progress(competition_id)
    per_category: dict[str, dict[str, Any]] = {}
    for qid, cat in (progress.get("per_category") or {}).items():
        per_category[qid] = {
            "question_number": cat.get("question_number"),
            "title": cat.get("title"),
            "stored": cat.get("stored", 0),
            "evaluated": cat.get("evaluated", 0),
            "avg_score": cat.get("avg_score"),
            "min_score": cat.get("min_score"),
            "max_score": cat.get("max_score"),
        }
    return {
        "competition_id": competition_id,
        "dashboard": dashboard_from_progress(progress),
        "cost": progress["cost"],
        "per_category": per_category,
    }


def _resolve_registrations(registration_ids: list[str]) -> dict[str, dict]:
    """Batch-load registration rows by id (chunked to respect URL limits)."""
    out: dict[str, dict] = {}
    ids = [rid for rid in registration_ids if rid]
    for i in range(0, len(ids), 100):
        chunk = ids[i : i + 100]
        try:
            rows = (
                db()
                .table("registrations")
                .select("id, name, full_name, email, phone, college, registration_number")
                .in_("id", chunk)
                .execute()
                .data
                or []
            )
        except Exception:  # noqa: BLE001
            continue
        for row in rows:
            out[row["id"]] = row
    return out


def _participant_details(competition_id: str) -> dict[str, dict]:
    """Map participant_id -> participant + registration details."""
    parts = (
        db()
        .table("pc_participants")
        .select("id, competition_id, registration_id, qr_token, display_name, email")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    regs = _resolve_registrations([p.get("registration_id") or "" for p in parts])
    out: dict[str, dict] = {}
    for p in parts:
        reg = regs.get(p.get("registration_id") or "", {})
        out[p["id"]] = {
            "display_name": p.get("display_name"),
            "participant_email": p.get("email"),
            "qr_token": p.get("qr_token"),
            "registration_number": reg.get("registration_number")
            or reg.get("registration_no") or "",
            "full_name": reg.get("full_name") or reg.get("name") or "",
            "email": reg.get("email") or "",
            "phone": reg.get("phone") or "",
            "college": reg.get("college") or "",
        }
    return out


def build_export_columns(competition_id: str) -> list[tuple[str, str]]:
    """Return (select postgres stamp, header) pairs."""
    return [
        ("registration_number", "Registration Number"),
        ("full_name", "Full Name"),
        ("email", "Email"),
        ("phone", "Phone"),
        ("college", "College"),
        ("prompt_text", "Prompt"),
    ]


def order_export_blocks(
    rows: list[dict], by_category: bool = False
) -> list[dict]:
    """Return rows in strict category 1..N order, grouped per category.

    All rows for category 1 first, then category 2, etc. This produces a clean
    sequential category-wise export instead of interleaved data.
    """
    if not rows:
        return []
    max_cat = max((int(r.get("category") or 0) for r in rows), default=5)
    ordered: list[dict] = []
    for cat in range(1, max_cat + 1):
        ordered.extend(r for r in rows if int(r.get("category") or 0) == cat)
    return ordered


def build_export(competition_id: str, category: int | None = None) -> tuple[list[dict], list[tuple[str, str]], str]:
    """Return (rows, column_specs, filename) for JSON/structured use."""
    detail_map = _participant_details(competition_id)

    subs = (
        db()
        .table("pc_submissions")
        .select("id, participant_id")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    sub_ids = [s["id"] for s in subs]
    rows: list[dict] = []
    colspec = [("registration_number", "Registration Number"), ("full_name", "Full Name"),
               ("email", "Email"), ("phone", "Phone"), ("college", "College"), ("prompt_text", "Prompt")]

    if not sub_ids:
        filename = "prompts__all_categories.csv"
        if category:
            filename = f"prompts__category_{category}.csv"
        return [], colspec, filename

    # Gather per-submission responses with question number + evaluation score.
    responses: list[dict] = []
    for i in range(0, len(sub_ids), 100):
        chunk = sub_ids[i : i + 100]
        resp_rows = (
            db()
            .table("pc_responses")
            .select(
                "submission_id, question_id, prompt_text, "
                "pc_evaluations(score), pc_questions(question_number)"
            )
            .in_("submission_id", chunk)
            .execute()
            .data
            or []
        )
        responses.extend(resp_rows)
    # Index submissions by id.
    sub_by_id = {s["id"]: s for s in subs}

    qnum_by_qid: dict[str, int] = {}
    for r in responses:
        q = r.get("pc_questions") or {}
        qn = q.get("question_number")
        if qn is not None:
            qnum_by_qid[r["question_id"]] = int(qn)

    for r in responses:
        s = sub_by_id.get(r.get("submission_id"))
        if not s:
            continue
        pid = s.get("participant_id")
        qn = qnum_by_qid.get(r.get("question_id"))
        if category is not None and qn != category:
            continue
        details = detail_map.get(pid, {})
        evs = r.get("pc_evaluations") or []
        score = None
        if evs:
            score = evs[0].get("score")
        rows.append(
            {
                "registration_number": details.get("registration_number"),
                "full_name": details.get("full_name"),
                "email": details.get("email"),
                "phone": details.get("phone"),
                "college": details.get("college"),
                "prompt_text": r.get("prompt_text", ""),
                "category": qn,
                "category_title": CATEGORY_TITLES.get(qn, ""),
                "score": score,
            }
        )

    filename = "prompts__all_categories.csv"
    if category:
        filename = f"prompts__category_{category}.csv"
    # Group into a clean, sequential category-wise list.
    rows = order_export_blocks(rows)
    return rows, colspec, filename


def build_export_csv(competition_id: str, category: int | None = None) -> tuple[bytes, list[tuple[str, str]], str]:
    rows, _, filename = build_export(competition_id, category)
    headers = [
        "Registration Number",
        "Full Name",
        "Email",
        "Phone",
        "College",
        "Category",
        "Category Title",
        "Score",
        "Prompt",
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(
            [
                r.get("registration_number", ""),
                r.get("full_name", ""),
                r.get("email", ""),
                r.get("phone", ""),
                r.get("college", ""),
                r.get("category", ""),
                r.get("category_title", ""),
                r.get("score", ""),
                r.get("prompt_text", ""),
            ]
        )
    return buf.getvalue().encode("utf-8-sig"), headers, filename