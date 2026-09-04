from __future__ import annotations

import re
import secrets
import uuid

from fastapi import HTTPException, status

from app.config import settings
from app.db import db
from app.security.auth import create_participant_token


class AuthError(Exception):
    pass


def synthetic_participant_row(competition_id: str, identifier: str) -> dict:
    """Row for a development-only participant that is not tied to a real registration."""
    token = secrets.token_urlsafe(12).upper().replace("-", "_").replace("=", "")
    return {
        "competition_id": competition_id,
        "registration_id": str(uuid.uuid4()),
        "qr_token": f"GENAI_QR_{token}",
        "display_name": identifier,
        "email": f"{identifier}@test.local",
        "status": "REGISTERED",
    }


# Existing DB: registrations rows carry the QR token, full name and emails.
# We read this table READ-ONLY; we never write to it.
_REGISTRATION_TABLE = "registrations"


def normalize_qr_message(message: str) -> str:
    """Normalize a QR payload, falling back to text-only extraction if needed.

    Some QR generators embed URLs/query params; we accept the raw GENAI_QR_...
    token as-is or extracted from a query string.
    """
    msg = message.strip()
    for prefix in ("GENAI_QR_",):
        idx = msg.find(prefix)
        if idx != -1:
            candidate = msg[idx:]
            # Token is a run of uppercase/digits. Cut at first non-token char
            # or whitespace beyond the token.
            return re.match(r"[A-Za-z0-9_]+", candidate).group(0)
    return msg


def resolve_registration(qr_token: str, competition_id: str) -> dict:
    """Find the existing registration whose qr_token matches, and which belongs
    to the acceptable event for this competition.

    Reads only from the existing `registrations` table.
    """
    competition = (
        db()
        .table("pc_competitions")
        .select("id, qr_event_id, status")
        .eq("id", competition_id)
        .limit(1)
        .execute()
    )
    comp_rows = competition.data or []
    if not comp_rows:
        raise AuthError("Competition not found")
    comp = comp_rows[0]

    if comp.get("status") not in ("OPEN", "RESULTS_PUBLISHED"):
        raise AuthError("Competition is not accepting logins right now")

    reg = (
        db()
        .table(_REGISTRATION_TABLE)
        .select("*")
        .eq("qr_token", qr_token)
        .limit(1)
        .execute()
    )
    reg_rows = reg.data or []
    if not reg_rows:
        raise AuthError(
            "That QR code is not recognised. Please check your QR code and try again."
        )
    reg_data = reg_rows[0]

    # Optional event scoping: if the competition declares a qr_event_id, the
    # registration must belong to that event.
    event_id = comp.get("qr_event_id") or settings.qr_event_id
    if event_id and str(reg_data.get("event_id")) != event_id:
        raise AuthError("QR code is not registered for this event")

    if reg_data.get("registration_status", "").lower() not in ("verified", "confirmed", "approved"):
        raise AuthError("Registration is not verified yet")

    return reg_data


def ensure_participant(competition_id: str, reg: dict) -> dict:
    """Get or create a pc_participants row for this QR registration."""
    participant = (
        db()
        .table("pc_participants")
        .select("*")
        .eq("competition_id", competition_id)
        .eq("qr_token", reg["qr_token"])
        .limit(1)
        .execute()
    )
    rows = participant.data or []
    if rows:
        return rows[0]

    created = (
        db()
        .table("pc_participants")
        .insert(
            {
                "competition_id": competition_id,
                "registration_id": reg["id"],
                "qr_token": reg["qr_token"],
                "display_name": reg.get("full_name"),
                "email": reg.get("personal_email") or reg.get("college_email"),
                "status": "REGISTERED",
            }
        )
        .execute()
    )
    if not created.data:
        raise AuthError("Could not register participant")
    return created.data[0]


def has_submission(participant_id: str, competition_id: str) -> bool:
    sub = (
        db()
        .table("pc_submissions")
        .select("id")
        .eq("participant_id", participant_id)
        .eq("competition_id", competition_id)
        .limit(1)
        .execute()
    )
    return bool(sub.data)


def login_with_qr_message(qr_message: str, competition_id: str) -> dict:
    try:
        token_in = normalize_qr_message(qr_message)
        reg = resolve_registration(token_in, competition_id)
        participant = ensure_participant(competition_id, reg)
        already_submitted = has_submission(participant["id"], competition_id)
        jwt_token = create_participant_token(
            competition_id=competition_id,
            participant_id=participant["id"],
            qr_token=participant["qr_token"],
        )
        return {
            "token": jwt_token,
            "participant": {
                "competition_id": competition_id,
                "participant_id": participant["id"],
                "display_name": participant.get("display_name") or reg.get("full_name"),
                "email": participant.get("email"),
                "vit_registration_number": reg.get("vit_registration_number"),
                "already_submitted": already_submitted,
            },
        }
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc


def login_with_test(identifier: str, competition_id: str) -> dict:
    """Dev-only login: accepts email, reg number, or display name.

    Falls back to registrations table for test participants, or pc_participants
    for already-registered ones.
    """
    if settings.environment.lower() != "development":
        raise AuthError("Test login is only available in development mode")

    identifier = identifier.strip()

    # 1. Try to find participant by email OR by display_name OR by qr_token in
    # pc_participants first. Use individual .eq() calls so we don't have to
    # build a fragile `or_()` filter (Supabase's PostgREST or-filter has
    # issues with certain characters like commas in identifiers).
    for column in ("email", "display_name"):
        try:
            participant = (
                db()
                .table("pc_participants")
                .select("*")
                .eq("competition_id", competition_id)
                .eq(column, identifier)
                .limit(1)
                .execute()
            )
        except Exception:
            participant = None
        if participant and participant.data:
            p = participant.data[0]
            already_submitted = has_submission(p["id"], competition_id)
            jwt_token = create_participant_token(
                competition_id=competition_id,
                participant_id=p["id"],
                qr_token=p["qr_token"],
            )
            return {
                "token": jwt_token,
                "participant": {
                    "competition_id": competition_id,
                    "participant_id": p["id"],
                    "display_name": p.get("display_name"),
                    "email": p.get("email"),
                    "vit_registration_number": None,
                    "already_submitted": already_submitted,
                },
            }

    # 2. Fallback: look in registrations table. Try each column separately.
    reg = None
    for column in ("personal_email", "college_email", "full_name", "vit_registration_number"):
        try:
            result = (
                db()
                .table(_REGISTRATION_TABLE)
                .select("*")
                .eq(column, identifier)
                .limit(1)
                .execute()
            )
        except Exception:
            continue
        if result and result.data:
            reg = result
            break

    if not reg or not reg.data:
        # Development shortcut: if no participant/registration exists, create a
        # synthetic one on the fly so devs can test without seeding the DB.
        # This only works in development mode.
        created = (
            db()
            .table("pc_participants")
            .insert(synthetic_participant_row(competition_id, identifier))
            .execute()
        )
        if not created.data:
            raise AuthError(f"Could not create test participant for: {identifier}")
        p = created.data[0]
        jwt_token = create_participant_token(
            competition_id=competition_id,
            participant_id=p["id"],
            qr_token=p["qr_token"],
        )
        return {
            "token": jwt_token,
            "participant": {
                "competition_id": competition_id,
                "participant_id": p["id"],
                "display_name": p["display_name"],
                "email": p["email"],
                "vit_registration_number": None,
                "already_submitted": False,
            },
        }

    reg_data = reg.data[0]
    authed_participant = ensure_participant(competition_id, reg_data)
    already_submitted = has_submission(authed_participant["id"], competition_id)
    jwt_token = create_participant_token(
        competition_id=competition_id,
        participant_id=authed_participant["id"],
        qr_token=authed_participant["qr_token"],
    )
    return {
        "token": jwt_token,
        "participant": {
            "competition_id": competition_id,
            "participant_id": authed_participant["id"],
            "display_name": authed_participant.get("display_name") or reg_data.get("full_name"),
            "email": authed_participant.get("email"),
            "vit_registration_number": reg_data.get("vit_registration_number"),
            "already_submitted": already_submitted,
        },
    }
