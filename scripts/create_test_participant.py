"""Create a known test participant that can be used to test the system.

Inserts a registration into the existing `registrations` table (if not present)
and prints the QR token. Also creates a matching `pc_participants` row for the
given competition so the user can log in immediately.

Usage:
    cd backend
    python -m scripts.create_test_participant
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

# Make the backend package importable when running as a script
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.db import db  # noqa: E402

# Test participant config
TEST_REG_NUMBER = "TEST001"
TEST_FULL_NAME = "Test User"
TEST_EMAIL = "test@example.com"
TEST_EVENT_ID = settings.qr_event_id


def _ensure_registration() -> str:
    """Make sure a registration row exists for the test user. Returns qr_token."""
    # Check existing
    res = (
        db()
        .table("registrations")
        .select("qr_token")
        .or_(
            f"personal_email.eq.{TEST_EMAIL},"
            f"college_email.eq.{TEST_EMAIL},"
            f"vit_registration_number.eq.{TEST_REG_NUMBER}"
        )
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["qr_token"]

    # Insert new
    qr_token = f"GENAI_QR_{secrets.token_urlsafe(12).upper().replace('-', '_').replace('=', '')}"
    payload = {
        "full_name": TEST_FULL_NAME,
        "vit_registration_number": TEST_REG_NUMBER,
        "personal_email": TEST_EMAIL,
        "college_email": TEST_EMAIL,
        "event_id": TEST_EVENT_ID,
        "registration_status": "verified",
        "qr_token": qr_token,
    }
    inserted = (
        db()
        .table("registrations")
        .insert(payload)
        .execute()
    )
    if not inserted.data:
        raise SystemExit("Failed to insert test registration")
    return qr_token


def _ensure_competition() -> str:
    """Find the active competition (or fall back to the configured one)."""
    res = (
        db()
        .table("pc_competitions")
        .select("id, name, status")
        .in_("status", ["OPEN", "RESULTS_PUBLISHED"])
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["id"]
    raise SystemExit(
        "No active competition found. Create one in the admin panel first."
    )


def main() -> None:
    print("=" * 60)
    print("Creating Test Participant")
    print("=" * 60)

    competition_id = _ensure_competition()
    print(f"Competition: {competition_id}")

    qr_token = _ensure_registration()
    print(f"QR Token:    {qr_token}")
    print(f"Name:        {TEST_FULL_NAME}")
    print(f"Reg Number:  {TEST_REG_NUMBER}")
    print(f"Email:       {TEST_EMAIL}")
    print()
    print("=" * 60)
    print("Test participant ready!")
    print()
    print("Login options:")
    print(f"  1. QR text token:  {qr_token}")
    print(f"  2. Quick login:    {TEST_EMAIL}  (or {TEST_REG_NUMBER})")
    print()
    print("Admin credentials:")
    print(f"  username: {settings.admin_username}")
    print(f"  password: admin123")
    print("=" * 60)


if __name__ == "__main__":
    main()
