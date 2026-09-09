"""Single-device login window and immutable saved prompts."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

SESSION_TTL_HOURS = 8
ALREADY_SIGNED_IN_MSG = (
    "This registration is already signed in on another device. "
    "Continue there, or sign out first."
)
PROMPT_FROZEN_MSG = "This prompt is already saved and cannot be changed."


def hash_session_token(token: str) -> str:
    raw = token.encode("utf-8")
    return hashlib.md5(raw).hexdigest() + hashlib.md5(b"pc-session|" + raw).hexdigest()


def parse_timestamptz(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value
    else:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def session_is_active(participant: dict | None, *, now: datetime | None = None) -> bool:
    """True while a participant has a live session (cleared on sign-out or expiry)."""
    if not participant or not participant.get("session_token_hash"):
        return False
    expires = parse_timestamptz(participant.get("session_expires_at"))
    if expires is None:
        return False
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    return expires > clock.astimezone(timezone.utc)


def session_blocks_new_login(
    participant: dict,
    submission_status: str | None,
    *,
    now: datetime | None = None,
) -> bool:
    """True when a second login should be refused."""
    if participant.get("is_pipeline_tester"):
        return False
    if submission_status in ("SUBMITTED", "COMPLETED"):
        return False
    if participant.get("status") == "SUBMITTED":
        return False
    return session_is_active(participant, now=now)


def session_expiry_iso(*, now: datetime | None = None) -> str:
    clock = now or datetime.now(timezone.utc)
    return (clock.astimezone(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)).isoformat()


def frozen_prompt_action(existing_text: str | None, new_text: str) -> str:
    """insert | keep | reject — saved prompts cannot change."""
    if existing_text is None:
        return "insert"
    if existing_text.strip() == new_text.strip():
        return "keep"
    return "reject"
