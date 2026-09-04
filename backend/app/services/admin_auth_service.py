from __future__ import annotations

import time

import bcrypt

from app.config import settings
from app.security.auth import create_participant_token
from app.utils.logging_utils import log

# Simple per-IP sliding window rate limiter for login attempts (in-memory).
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300
_attempts: dict[str, list[float]] = {}


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _attempts.get(ip, []) if now - t < _WINDOW_SECONDS]
    _attempts[ip] = hits
    return len(hits) >= _MAX_ATTEMPTS


def record_failed(ip: str) -> None:
    _attempts.setdefault(ip, []).append(time.time())


def record_success(ip: str) -> None:
    _attempts.pop(ip, None)


def password_matches(password: str) -> bool:
    """Verify the plaintext password against the stored bcrypt hash."""
    if not settings.admin_password_hash:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            settings.admin_password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError) as exc:  # noqa: BLE001
        log.warning("admin_password_check_failed", error=str(exc)[:120])
        return False


def login_admin(username: str, password: str, ip: str) -> dict | None:
    """Validate admin credentials; return a signed admin JWT on success."""
    if not settings.admin_password_hash:
        log.warning("admin_login_disabled_no_hash")
        return None

    if username != settings.admin_username:
        record_failed(ip)
        return None

    if is_rate_limited(ip):
        log.warning("admin_login_rate_limited", ip=ip)
        raise RateLimitedError()

    if not password_matches(password):
        record_failed(ip)
        log.warning("admin_login_failed", ip=ip)
        return None

    record_success(ip)
    token = create_participant_token(
        competition_id="competition_2026",
        participant_id="admin",
        qr_token="",
        is_admin=True,
    )
    log.info("admin_login_success", ip=ip)
    return {"token": token, "username": username, "role": "admin"}


class RateLimitedError(Exception):
    pass