"""Manual participant registration for the admin panel.

Admin registers a participant by official registration number (plus name/email).
These are written straight into ``pc_participants`` so the participant can then
sign in via their registration number, without needing a QR code.
"""
from __future__ import annotations

import secrets
import uuid
from typing import Any

from app.db import db


class RegistrationError(Exception):
    pass


def _make_qr_token() -> str:
    return f"GENAI_QR_MANUAL_{secrets.token_urlsafe(12).upper().replace('-', '_').replace('=', '')}"


def list_registrations(competition_id: str) -> list[dict[str, Any]]:
    rows = (
        db()
        .table("pc_participants")
        .select("*")
        .eq("competition_id", competition_id)
        .not_.is_("registration_number", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return [
        {
            "id": r["id"],
            "registration_number": r.get("registration_number"),
            "display_name": r.get("display_name"),
            "email": r.get("email"),
            "status": r.get("status"),
            "created_at": r.get("created_at"),
        }
        for r in rows.data or []
    ]


def register_participant(
    competition_id: str,
    registration_number: str,
    display_name: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """Insert a manually-registered participant keyed by registration_number."""
    reg = (registration_number or "").strip()
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
    }
    created = db().table("pc_participants").insert(row).execute()
    if not created.data:
        raise RegistrationError("Could not register participant.")
    return created.data[0]
