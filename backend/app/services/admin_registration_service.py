"""Manual participant registration and the admin participants roster.

Admin-added people are written to ``pc_participants`` only. The existing
``registrations`` table is read-only: we fetch registration number + name and
never insert, update, or delete rows there.
"""
from __future__ import annotations

import secrets
import uuid
from typing import Any

from app.config import settings
from app.db import db, fetch_all

TEST_COMPETITION_ID = "competition_test"
MANUAL_QR_PREFIX = "GENAI_QR_MANUAL_"
PIPELINE_TESTER_REG = "abhinavkumarsaksena"


class RegistrationError(Exception):
    pass


def _make_qr_token() -> str:
    return f"{MANUAL_QR_PREFIX}{secrets.token_urlsafe(12).upper().replace('-', '_').replace('=', '')}"


def normalize_reg(value: str | None) -> str:
    return (value or "").strip()


def _reg_number(row: dict[str, Any]) -> str:
    return normalize_reg(row.get("vit_registration_number") or row.get("registration_number"))


def _reg_name(row: dict[str, Any]) -> str:
    return (row.get("full_name") or row.get("name") or "").strip()


def _is_tester(row: dict[str, Any]) -> bool:
    if row.get("is_pipeline_tester"):
        return True
    return normalize_reg(row.get("registration_number")).casefold() == PIPELINE_TESTER_REG


def _is_manual(row: dict[str, Any]) -> bool:
    token = str(row.get("qr_token") or "")
    return token.startswith(MANUAL_QR_PREFIX)


_HAS_TESTER_COL: bool | None = None


def _participant_select() -> str:
    base = (
        "id, competition_id, registration_id, registration_number, qr_token, "
        "display_name, email, status, login_count, last_login_at, created_at"
    )
    if _HAS_TESTER_COL is False:
        return base
    return base + ", is_pipeline_tester"


def _load_participants(competition_id: str) -> list[dict[str, Any]]:
    global _HAS_TESTER_COL
    try:
        rows = fetch_all(
            "pc_participants",
            _participant_select(),
            eq={"competition_id": competition_id},
            order="created_at",
            descending=True,
        )
        _HAS_TESTER_COL = True
        return rows
    except Exception:  # noqa: BLE001
        _HAS_TESTER_COL = False
        return fetch_all(
            "pc_participants",
            _participant_select(),
            eq={"competition_id": competition_id},
            order="created_at",
            descending=True,
        )


def _load_submissions(competition_id: str) -> dict[str, dict[str, Any]]:
    rows = fetch_all(
        "pc_submissions",
        "id, participant_id, status, total_score",
        eq={"competition_id": competition_id},
    )
    by_participant: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_participant[row["participant_id"]] = row
    return by_participant


def _event_id_for_competition(competition_id: str) -> str:
    rows = (
        db()
        .table("pc_competitions")
        .select("qr_event_id")
        .eq("id", competition_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return str((rows[0].get("qr_event_id") if rows else None) or settings.qr_event_id or "")


def _load_event_registrations(event_id: str) -> list[dict[str, Any]]:
    """Read-only fetch of event registrations (number + name)."""
    select = "id, full_name, vit_registration_number"
    eq = {"event_id": event_id} if event_id else None
    try:
        return fetch_all("registrations", select, eq=eq)
    except Exception:  # noqa: BLE001
        return fetch_all("registrations", "id, full_name, vit_registration_number", eq=None)


def _row(
    *,
    id: str,
    registration_number: str | None,
    display_name: str | None,
    source: str,
    logged_in: bool | None,
    last_login_at: str | None,
    submitted: bool,
    submission_status: str | None,
) -> dict[str, Any]:
    return {
        "id": id,
        "registration_number": registration_number,
        "display_name": display_name,
        "source": source,
        "logged_in": logged_in,
        "last_login_at": last_login_at,
        "submitted": submitted,
        "submission_status": submission_status,
    }


def list_roster(competition_id: str) -> dict[str, Any]:
    """Merged participant list for the admin Participants page."""
    test_mode = competition_id == TEST_COMPETITION_ID
    parts = [p for p in _load_participants(competition_id) if not _is_tester(p)]
    subs = _load_submissions(competition_id)
    part_by_id = {p["id"]: p for p in parts}
    part_by_reg_id = {str(p.get("registration_id") or ""): p for p in parts if p.get("registration_id")}
    part_by_regnum: dict[str, dict[str, Any]] = {}
    for p in parts:
        key = normalize_reg(p.get("registration_number")).casefold()
        if key:
            part_by_regnum[key] = p

    matched_ids: set[str] = set()
    rows: list[dict[str, Any]] = []

    if test_mode:
        for p in parts:
            sub = subs.get(p["id"])
            rows.append(
                _row(
                    id=p["id"],
                    registration_number=p.get("registration_number"),
                    display_name=p.get("display_name"),
                    source="dataset",
                    logged_in=None,
                    last_login_at=None,
                    submitted=sub is not None,
                    submission_status=sub.get("status") if sub else None,
                )
            )
    else:
        event_id = _event_id_for_competition(competition_id)
        for reg in _load_event_registrations(event_id):
            number = _reg_number(reg)
            if not number:
                continue
            p = part_by_reg_id.get(str(reg.get("id") or "")) or part_by_regnum.get(number.casefold())
            if p:
                matched_ids.add(p["id"])
            sub = subs.get(p["id"]) if p else None
            login_count = int((p or {}).get("login_count") or 0)
            rows.append(
                _row(
                    id=(p["id"] if p else f"reg:{reg.get('id')}"),
                    registration_number=number,
                    display_name=_reg_name(reg) or (p.get("display_name") if p else None),
                    source="event",
                    logged_in=login_count > 0,
                    last_login_at=(p.get("last_login_at") if p else None),
                    submitted=sub is not None,
                    submission_status=sub.get("status") if sub else None,
                )
            )
        for p in parts:
            if p["id"] in matched_ids:
                continue
            sub = subs.get(p["id"])
            login_count = int(p.get("login_count") or 0)
            added = _is_manual(p) or bool(normalize_reg(p.get("registration_number")))
            rows.append(
                _row(
                    id=p["id"],
                    registration_number=p.get("registration_number"),
                    display_name=p.get("display_name"),
                    source="added" if added else "event",
                    logged_in=login_count > 0,
                    last_login_at=p.get("last_login_at"),
                    submitted=sub is not None,
                    submission_status=sub.get("status") if sub else None,
                )
            )

    logged_in = None if test_mode else sum(1 for r in rows if r.get("logged_in"))
    submitted = sum(1 for r in rows if r.get("submitted"))
    completed = sum(1 for r in rows if r.get("submission_status") == "COMPLETED")
    return {
        "competition_id": competition_id,
        "test_mode": test_mode,
        "show_login": not test_mode,
        "registered": len(rows),
        "logged_in": logged_in,
        "submitted": submitted,
        "completed": completed,
        "participants": rows,
        "visible_participants": len(part_by_id),
    }


def list_registrations(competition_id: str) -> list[dict[str, Any]]:
    """Back-compat: admin-added rows only (never testers)."""
    return [
        {
            "id": r["id"],
            "registration_number": r.get("registration_number"),
            "display_name": r.get("display_name"),
            "email": None,
            "status": r.get("submission_status"),
            "created_at": None,
        }
        for r in list_roster(competition_id)["participants"]
        if r.get("source") == "added"
    ]


def register_participant(
    competition_id: str,
    registration_number: str,
    display_name: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Insert a manually-registered participant keyed by registration_number.

    Writes ``pc_participants`` only. Never writes the ``registrations`` table.
    """
    reg = normalize_reg(registration_number)
    if not reg:
        raise RegistrationError("Registration number is required.")

    existing = (
        db()
        .table("pc_participants")
        .select("id")
        .eq("competition_id", competition_id)
        .eq("registration_number", reg)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise RegistrationError(f"Registration number {reg} is already registered for this competition.")

    row = {
        "competition_id": competition_id,
        "registration_id": str(uuid.uuid4()),
        "qr_token": _make_qr_token(),
        "registration_number": reg,
        "display_name": (display_name or "").strip() or None,
        "email": (email or "").strip() or None,
        "status": "REGISTERED",
        "is_pipeline_tester": False,
    }
    try:
        created = db().table("pc_participants").insert(row).execute()
    except Exception:  # noqa: BLE001
        row.pop("is_pipeline_tester", None)
        created = db().table("pc_participants").insert(row).execute()
    if not created.data:
        raise RegistrationError("Could not register participant.")
    return created.data[0]
