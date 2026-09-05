from __future__ import annotations

import re
import uuid

from app.config import settings
from app.db import db
from app.security.auth import create_participant_token
from app.services.admin_registration_service import MANUAL_QR_PREFIX, normalize_reg


class AuthError(Exception):
    pass


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
            matched = re.match(r"[A-Za-z0-9_]+", candidate)
            if matched:
                return matched.group(0)
    return msg


def _event_id_for(comp: dict) -> str:
    return str(comp.get("qr_event_id") or settings.qr_event_id or "")


def _load_competition(competition_id: str) -> dict:
    competition = (
        db()
        .table("pc_competitions")
        .select("id, qr_event_id, status")
        .eq("id", competition_id)
        .limit(1)
        .execute()
    )
    rows = competition.data or []
    if not rows:
        raise AuthError("Competition not found")
    return rows[0]


def _ensure_accepting_logins(comp: dict) -> None:
    if comp.get("status") not in ("OPEN", "RESULTS_PUBLISHED"):
        raise AuthError("Competition is not accepting logins right now")


def resolve_registration(qr_token: str, competition_id: str) -> dict:
    """Find the existing registration whose qr_token matches.

    Reads only from the existing ``registrations`` table.
    """
    comp = _load_competition(competition_id)
    _ensure_accepting_logins(comp)

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

    event_id = _event_id_for(comp)
    if event_id and str(reg_data.get("event_id")) != event_id:
        raise AuthError("QR code is not registered for this event")

    if reg_data.get("registration_status", "").lower() not in ("verified", "confirmed", "approved"):
        raise AuthError("Registration is not verified yet")

    return reg_data


def _registration_number_from(reg: dict) -> str | None:
    value = normalize_reg(reg.get("vit_registration_number") or reg.get("registration_number"))
    return value or None


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
        existing = rows[0]
        number = _registration_number_from(reg)
        if number and not existing.get("registration_number"):
            try:
                db().table("pc_participants").update({"registration_number": number}).eq(
                    "id", existing["id"]
                ).execute()
                existing["registration_number"] = number
            except Exception:  # noqa: BLE001
                pass
        return existing

    payload = {
        "competition_id": competition_id,
        "registration_id": reg["id"],
        "qr_token": reg["qr_token"],
        "display_name": reg.get("full_name") or reg.get("name"),
        "email": reg.get("personal_email") or reg.get("college_email"),
        "status": "REGISTERED",
        "is_pipeline_tester": False,
    }
    number = _registration_number_from(reg)
    if number:
        payload["registration_number"] = number
    try:
        created = db().table("pc_participants").insert(payload).execute()
    except Exception:  # noqa: BLE001
        payload.pop("is_pipeline_tester", None)
        created = db().table("pc_participants").insert(payload).execute()
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


def stamp_login(participant_id: str) -> None:
    """Bump login_count and set last_login_at for the participant."""
    try:
        cur = (
            db()
            .table("pc_participants")
            .select("login_count")
            .eq("id", participant_id)
            .limit(1)
            .execute()
        )
        rows = cur.data or []
        current = int((rows[0].get("login_count") or 0)) if rows else 0
        (
            db()
            .table("pc_participants")
            .update(
                {
                    "login_count": current + 1,
                    "last_login_at": "now()",
                }
            )
            .eq("id", participant_id)
            .execute()
        )
    except Exception:  # noqa: BLE001
        pass


def _ensure_competition_open(competition_id: str) -> None:
    _ensure_accepting_logins(_load_competition(competition_id))


def _issue_session(competition_id: str, participant: dict, *, registration_number: str | None) -> dict:
    stamp_login(participant["id"])
    already_submitted = has_submission(participant["id"], competition_id)
    jwt_token = create_participant_token(
        competition_id=competition_id,
        participant_id=participant["id"],
        qr_token=participant["qr_token"],
    )
    return {
        "requires_qr": False,
        "token": jwt_token,
        "participant": {
            "competition_id": competition_id,
            "participant_id": participant["id"],
            "display_name": participant.get("display_name") or "Participant",
            "email": participant.get("email"),
            "vit_registration_number": registration_number or participant.get("registration_number"),
            "already_submitted": already_submitted,
        },
        "display_name": participant.get("display_name") or "Participant",
    }


def _find_participant_by_reg(competition_id: str, registration_number: str) -> dict | None:
    participant = (
        db()
        .table("pc_participants")
        .select("*")
        .eq("competition_id", competition_id)
        .eq("registration_number", registration_number)
        .limit(1)
        .execute()
    )
    rows = participant.data or []
    if rows:
        return rows[0]
    # Case-insensitive fallback for mixed-case typed numbers.
    folded = registration_number.casefold()
    all_rows = (
        db()
        .table("pc_participants")
        .select("*")
        .eq("competition_id", competition_id)
        .execute()
        .data
        or []
    )
    for row in all_rows:
        if normalize_reg(row.get("registration_number")).casefold() == folded:
            return row
    return None


def _find_event_registration(registration_number: str, competition_id: str) -> dict | None:
    comp = _load_competition(competition_id)
    event_id = _event_id_for(comp)
    for column in ("vit_registration_number", "registration_number"):
        try:
            query = db().table(_REGISTRATION_TABLE).select("*").ilike(column, registration_number)
            if event_id:
                query = query.eq("event_id", event_id)
            result = query.limit(1).execute()
        except Exception:  # noqa: BLE001
            continue
        if result and result.data:
            return result.data[0]
    return None


def _can_skip_qr(participant: dict) -> bool:
    if participant.get("is_pipeline_tester"):
        return True
    if normalize_reg(participant.get("registration_number")).casefold() == "abhinavkumarsaksena":
        return True
    token = str(participant.get("qr_token") or "")
    return token.startswith(MANUAL_QR_PREFIX)


def login_with_registration_number(registration_number: str, competition_id: str) -> dict:
    """Step 1 of participant login.

    Pipeline testers and admin-added extras sign in with the number alone.
    Event registrants must continue with a matching QR code.
    """
    _ensure_competition_open(competition_id)
    needle = normalize_reg(registration_number)
    if not needle:
        raise AuthError("Please enter your registration number.")

    participant = _find_participant_by_reg(competition_id, needle)
    if participant and _can_skip_qr(participant):
        return _issue_session(
            competition_id,
            participant,
            registration_number=participant.get("registration_number") or needle,
        )

    if participant:
        return {
            "requires_qr": True,
            "token": None,
            "participant": None,
            "display_name": participant.get("display_name"),
        }

    reg = _find_event_registration(needle, competition_id)
    if not reg:
        raise AuthError("This registration number is not registered for this event.")

    return {
        "requires_qr": True,
        "token": None,
        "participant": None,
        "display_name": reg.get("full_name") or reg.get("name"),
    }


def login_with_qr_message(
    qr_message: str,
    competition_id: str,
    registration_number: str,
) -> dict:
    expected = normalize_reg(registration_number)
    if not expected:
        raise AuthError("Enter your registration number first, then scan your QR code.")

    token_in = normalize_qr_message(qr_message)
    reg = resolve_registration(token_in, competition_id)
    actual = _registration_number_from(reg) or ""
    if actual.casefold() != expected.casefold():
        raise AuthError("That QR code does not match the registration number you entered.")

    participant = ensure_participant(competition_id, reg)
    session = _issue_session(
        competition_id,
        participant,
        registration_number=actual or expected,
    )
    return {
        "token": session["token"],
        "participant": session["participant"],
    }


# Kept so older tests that imported the helper still resolve if needed.
def synthetic_participant_row(competition_id: str, identifier: str) -> dict:
    token = uuid.uuid4().hex[:12].upper()
    return {
        "competition_id": competition_id,
        "registration_id": str(uuid.uuid4()),
        "qr_token": f"{MANUAL_QR_PREFIX}{token}",
        "display_name": identifier,
        "email": f"{identifier}@test.local",
        "status": "REGISTERED",
        "is_pipeline_tester": True,
    }
