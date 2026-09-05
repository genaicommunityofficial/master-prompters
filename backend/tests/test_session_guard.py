from datetime import datetime, timezone

from app.services.session_guard import (
    frozen_prompt_action,
    session_blocks_new_login,
)


def _participant(**overrides):
    row = {
        "is_pipeline_tester": False,
        "status": "REGISTERED",
        "session_token_hash": "abc",
        "session_expires_at": "2099-01-01T00:00:00+00:00",
    }
    row.update(overrides)
    return row


def test_blocks_second_login_while_session_is_live():
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert session_blocks_new_login(_participant(), None, now=now) is True


def test_allows_login_after_session_expires():
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert (
        session_blocks_new_login(
            _participant(session_expires_at="2020-01-01T00:00:00+00:00"),
            None,
            now=now,
        )
        is False
    )


def test_allows_login_when_already_submitted():
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert session_blocks_new_login(_participant(), "SUBMITTED", now=now) is False


def test_pipeline_tester_can_always_relogin():
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert (
        session_blocks_new_login(_participant(is_pipeline_tester=True), None, now=now)
        is False
    )


def test_legacy_row_without_expiry_is_not_locked():
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert (
        session_blocks_new_login(_participant(session_expires_at=None), None, now=now)
        is False
    )


def test_frozen_prompt_insert_keep_reject():
    assert frozen_prompt_action(None, "hello") == "insert"
    assert frozen_prompt_action("hello", "hello") == "keep"
    assert frozen_prompt_action("  hello  ", "hello") == "keep"
    assert frozen_prompt_action("hello", "other") == "reject"
