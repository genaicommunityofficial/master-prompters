from __future__ import annotations

import csv
import io
import re
from typing import Any

from app.db import db

REST_PAGE = 1000

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


def _event_registration_lookup(competition_id: str) -> dict[str, dict[str, str]]:
    """Map event id / QR / VIT number -> registration number and name."""
    from app.services.admin_registration_service import (
        TEST_COMPETITION_ID,
        _event_id_for_competition,
        _load_event_registrations,
        _reg_name,
        _reg_number,
        normalize_reg,
    )

    if competition_id == TEST_COMPETITION_ID:
        return {}
    event_id = _event_id_for_competition(competition_id)
    out: dict[str, dict[str, str]] = {}
    for row in _load_event_registrations(event_id):
        info = {
            "registration_number": _reg_number(row),
            "display_name": _reg_name(row),
        }
        rid = str(row.get("id") or "")
        if rid:
            out[rid] = info
        qr = str(row.get("qr_token") or "").strip()
        if qr:
            out[qr] = info
        number = normalize_reg(info["registration_number"])
        if number:
            out[number.casefold()] = info
    return out


def _clean_display_name(name: str, registration_number: str | None) -> str:
    cleaned = (name or "").strip()
    number = (registration_number or "").strip()
    if number and cleaned.upper().endswith(number.upper()):
        cleaned = cleaned[: -len(number)].strip()
    return cleaned


def _event_for_participant(
    participant: dict, event_lookup: dict[str, dict[str, str]]
) -> dict[str, str]:
    from app.services.admin_registration_service import normalize_reg

    keys = [
        str(participant.get("registration_id") or ""),
        str(participant.get("qr_token") or "").strip(),
        normalize_reg(participant.get("registration_number")).casefold(),
    ]
    for key in keys:
        if key and key in event_lookup:
            return event_lookup[key]
    return {}


def _export_display_name(participant: dict, event_lookup: dict[str, dict[str, str]]) -> str:
    event = _event_for_participant(participant, event_lookup)
    event_name = (event.get("display_name") or "").strip()
    number = (event.get("registration_number") or participant.get("registration_number") or "")
    if event_name:
        return _clean_display_name(event_name, str(number))
    return _clean_display_name(str(participant.get("display_name") or ""), str(number))


def _export_registration_number(
    participant: dict,
    event_lookup: dict[str, dict[str, str]],
) -> str:
    """Registration number only — never name, email, or QR text."""
    from app.services.admin_registration_service import normalize_reg

    event = _event_for_participant(participant, event_lookup)
    event_number = normalize_reg(event.get("registration_number"))
    if event_number:
        return event_number
    return normalize_reg(participant.get("registration_number"))


def _fetch_eq(table: str, select: str, competition_id: str) -> list[dict]:
    """Range-paginate rows for one competition using this module's db()."""
    rows: list[dict] = []
    offset = 0
    while True:
        builder = (
            db()
            .table(table)
            .select(select)
            .eq("competition_id", competition_id)
            .range(offset, offset + REST_PAGE - 1)
        )
        page = builder.execute().data or []
        rows.extend(page)
        if len(page) < REST_PAGE:
            break
        offset += REST_PAGE
    return rows


def _fetch_in(table: str, select: str, column: str, values: list[str]) -> list[dict]:
    rows: list[dict] = []
    for i in range(0, len(values), 200):
        chunk = values[i : i + 200]
        offset = 0
        while True:
            page = (
                db()
                .table(table)
                .select(select)
                .in_(column, chunk)
                .range(offset, offset + REST_PAGE - 1)
                .execute()
                .data
                or []
            )
            rows.extend(page)
            if len(page) < REST_PAGE:
                break
            offset += REST_PAGE
    return rows


def _participant_details(competition_id: str) -> dict[str, dict]:
    """Map participant_id -> registration number and name for export."""
    from app.services.admin_registration_service import TEST_COMPETITION_ID, _is_manual, _is_tester

    select_full = (
        "id, competition_id, registration_id, registration_number, "
        "display_name, status, qr_token, is_pipeline_tester"
    )
    select_base = (
        "id, competition_id, registration_id, registration_number, "
        "display_name, status, qr_token"
    )
    try:
        parts = _fetch_eq("pc_participants", select_full, competition_id)
    except Exception:  # noqa: BLE001
        parts = _fetch_eq("pc_participants", select_base, competition_id)
    live = competition_id != TEST_COMPETITION_ID
    kept: list[dict] = []
    for p in parts:
        if str(p.get("status") or "").upper() == "DISQUALIFIED":
            continue
        if _is_tester(p):
            continue
        if live and _is_manual(p):
            continue
        kept.append(p)
    event_lookup = _event_registration_lookup(competition_id)
    out: dict[str, dict] = {}
    for p in kept:
        out[p["id"]] = {
            "registration_number": _export_registration_number(p, event_lookup),
            "display_name": _export_display_name(p, event_lookup),
        }
    return out


def _questions_for_competition(competition_id: str) -> dict[str, dict[str, Any]]:
    rows = (
        db()
        .table("pc_questions")
        .select("id, question_number, title")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        number = int(row.get("question_number") or 0)
        title = (row.get("title") or "").strip() or CATEGORY_TITLES.get(number, f"Category {number}")
        out[row["id"]] = {"number": number, "title": title}
    return out


def build_export_columns(competition_id: str) -> list[tuple[str, str]]:
    """Return (field, header) pairs for the prompt sheet."""
    return [
        ("registration_number", "Reg No"),
        ("display_name", "Name"),
        ("category_title", "Category"),
        ("prompt_text", "Prompt"),
    ]


def _natural_sort_key(value: str) -> tuple:
    parts = re.split(r"(\d+)", (value or "").strip().casefold())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def order_export_blocks(
    rows: list[dict], by_category: bool = False
) -> list[dict]:
    """Keep each person together, in natural reg-no order, then category 1..N."""
    if not rows:
        return []

    def sort_key(row: dict) -> tuple:
        number = int(row.get("category") or 0)
        return (
            _natural_sort_key(str(row.get("registration_number") or "")),
            (row.get("display_name") or "").strip().casefold(),
            number if number > 0 else 10_000,
        )

    return sorted(rows, key=sort_key)


def _export_filename(competition_id: str, category: int | None) -> str:
    scope = "test" if competition_id == "competition_test" else "live"
    if category:
        return f"prompts_{scope}_category_{category}.csv"
    return f"prompts_{scope}_all.csv"


def build_export(competition_id: str, category: int | None = None) -> tuple[list[dict], list[tuple[str, str]], str]:
    """One row per visible participant and category, with prompt text when saved."""
    colspec = build_export_columns(competition_id)
    filename = _export_filename(competition_id, category)
    questions = _questions_for_competition(competition_id)
    detail_map = _participant_details(competition_id)
    if not detail_map or not questions:
        return [], colspec, filename

    subs = _fetch_eq("pc_submissions", "id, participant_id", competition_id)
    subs = [s for s in subs if s.get("participant_id") in detail_map]
    sub_by_id = {s["id"]: s for s in subs}
    prompt_by_key: dict[tuple[str, str], str] = {}
    sub_ids = [s["id"] for s in subs]
    if sub_ids:
        for response in _fetch_in(
            "pc_responses",
            "submission_id, question_id, prompt_text",
            "submission_id",
            sub_ids,
        ):
            submission = sub_by_id.get(response.get("submission_id"))
            if not submission:
                continue
            participant_id = str(submission.get("participant_id") or "")
            question_id = str(response.get("question_id") or "")
            prompt_by_key[(participant_id, question_id)] = response.get("prompt_text") or ""

    question_items = sorted(
        questions.items(),
        key=lambda item: int(item[1].get("number") or 0),
    )
    rows: list[dict] = []
    for participant_id, details in detail_map.items():
        for question_id, question in question_items:
            number = int(question.get("number") or 0)
            if category is not None and number != category:
                continue
            title = question.get("title") or CATEGORY_TITLES.get(number, "")
            prompt_text = prompt_by_key.get((participant_id, question_id), "")
            if not str(prompt_text).strip():
                continue
            rows.append(
                {
                    "registration_number": details.get("registration_number") or "",
                    "display_name": details.get("display_name") or "",
                    "category": number,
                    "category_title": title,
                    "prompt_text": prompt_text,
                }
            )

    rows = order_export_blocks(rows)
    return rows, colspec, filename


def build_export_csv(competition_id: str, category: int | None = None) -> tuple[bytes, list[tuple[str, str]], str]:
    rows, colspec, filename = build_export(competition_id, category)
    headers = [header for _, header in colspec]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([row.get(field, "") or "" for field, _ in colspec])
    return buf.getvalue().encode("utf-8-sig"), colspec, filename